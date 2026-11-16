"""HTTP host for JSON API, uploaded images and the built web application."""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg

from backend.app import ApiError, Application
from backend.db import ROOT, connect, initialize, load_env

MAX_BODY = 2_900_000
LOGGER = logging.getLogger('donnih')


def create_server(database: str | Path, host: str = '127.0.0.1', port: int = 8000,
                  allowed_origins: set[str] | None = None, secure_cookie: bool = False,
                  session_hours: int = 168) -> ThreadingHTTPServer:
    app = Application(database, session_hours)
    origins = allowed_origins or {'http://localhost:5173', 'http://127.0.0.1:5173',
                                  f'http://localhost:{port}', f'http://127.0.0.1:{port}'}
    dist = ROOT / 'frontend' / 'dist'

    class Handler(BaseHTTPRequestHandler):
        server_version = 'Donnih'
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, format, *args):
            # Do not log passwords, cookies, request bodies or query strings.
            LOGGER.info('%s %s %s', self.address_string(), self.command, urlsplit(self.path).path)

        def send_security_headers(self, content_type, size, *, cache='no-store', cookie=None):
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(size))
            self.send_header('Cache-Control', cache)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
            if cookie is not None:
                value = SimpleCookie()
                value['donnih_session'] = cookie
                value['donnih_session']['httponly'] = True
                value['donnih_session']['samesite'] = 'Lax'
                value['donnih_session']['path'] = '/'
                value['donnih_session']['max-age'] = str(session_hours * 3600 if cookie else 0)
                if secure_cookie:
                    value['donnih_session']['secure'] = True
                self.send_header('Set-Cookie', value.output(header='').strip())
            self.end_headers()

        def send_json(self, status, data, cookie=None):
            encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_security_headers('application/json; charset=utf-8', len(encoded), cookie=cookie)
            if self.command != 'HEAD':
                self.wfile.write(encoded)

        def handle_request(self):
            try:
                if len(self.path) > 2048:
                    raise ApiError(414, 'URL terlalu panjang.')
                path = urlsplit(self.path).path
                if path.startswith('/api/'):
                    body = {}
                    if self.command not in ('GET', 'HEAD'):
                        # Custom header + JSON + no CORS block cross-origin simple requests.
                        if self.headers.get('X-Requested-With') != 'donnih-web':
                            raise ApiError(403, 'Header keamanan permintaan tidak valid.')
                        origin = self.headers.get('Origin')
                        if origin and origin not in origins:
                            raise ApiError(403, 'Origin permintaan tidak diizinkan.')
                        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                            raise ApiError(403, 'Permintaan lintas situs tidak diizinkan.')
                        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                            raise ApiError(415, 'Gunakan Content-Type application/json.')
                        if self.headers.get('Transfer-Encoding'):
                            raise ApiError(400, 'Transfer-Encoding tidak didukung.')
                        try:
                            length = int(self.headers.get('Content-Length', '0'))
                        except ValueError as exc:
                            raise ApiError(400, 'Content-Length tidak valid.') from exc
                        if not 0 <= length <= MAX_BODY:
                            raise ApiError(413, 'Body permintaan terlalu besar.')
                        try:
                            raw = self.rfile.read(length)
                            if len(raw) != length:
                                raise ApiError(400, 'Body permintaan tidak lengkap.')
                            body = json.loads(raw) if raw else {}
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise ApiError(400, 'JSON tidak valid.') from exc
                    cookies = SimpleCookie()
                    try:
                        cookies.load(self.headers.get('Cookie', ''))
                        token = cookies['donnih_session'].value if 'donnih_session' in cookies else ''
                    except CookieError:
                        token = ''
                    response = app.request(self.command, self.path, body, token, self.client_address[0])
                    self.send_json(response.status, response.data, response.session)
                elif self.command in ('GET', 'HEAD'):
                    self.serve_static(path)
                else:
                    raise ApiError(405, 'Metode tidak didukung.')
            except ApiError as exc:
                self.send_json(exc.status, {'error': str(exc)})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except psycopg.OperationalError:
                LOGGER.exception('Database tidak tersedia')
                self.send_json(503, {'error': 'Penyimpanan sedang sibuk. Coba kembali.'})
            except Exception:
                LOGGER.exception('Kesalahan internal')
                self.send_json(500, {'error': 'Terjadi kesalahan pada server. Silakan coba kembali.'})

        def serve_static(self, raw_path):
            path = unquote(raw_path)
            if path.startswith('/uploads/'):
                db = connect(database)
                try:
                    image = db.execute('SELECT content_type,content FROM uploads WHERE path=%s', (path,)).fetchone()
                finally:
                    db.close()
                if not image:
                    raise ApiError(404, 'Gambar tidak ditemukan.')
                raw_bytes = bytes(image['content'])
                self.send_response(200)
                self.send_security_headers(image['content_type'], len(raw_bytes), cache='public, max-age=3600')
                if self.command != 'HEAD':
                    self.wfile.write(raw_bytes)
                return
            target = (dist / path.lstrip('/')).resolve()
            if not target.is_relative_to(dist.resolve()) or any(part.startswith('.') for part in Path(path).parts):
                raise ApiError(404, 'Berkas tidak ditemukan.')
            if not target.is_file():
                if Path(path).suffix:
                    raise ApiError(404, 'Berkas tidak ditemukan.')
                target = dist / 'index.html'
            if not target.exists():
                raise ApiError(503, 'Frontend belum dibangun. Jalankan npm --prefix frontend run build, atau buka Vite port 5173.')
            content = target.read_bytes()
            mime = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html'}.get(target.suffix,
                       mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            self.send_response(200)
            self.send_security_headers(mime, len(content))
            if self.command != 'HEAD':
                self.wfile.write(content)

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request
        do_HEAD = handle_request
        do_OPTIONS = handle_request

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    load_env()
    parser = argparse.ArgumentParser(description='API dan web Kedai Don.Nih!')
    parser.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8000')))
    parser.add_argument(
        '--database',
        default=os.environ.get('DATABASE_URL', ''),
        help='PostgreSQL connection URI (default: DATABASE_URL)',
    )
    args = parser.parse_args()
    if not args.database:
        parser.exit(1, 'Gagal: DATABASE_URL belum diatur di environment atau .env.\n')
    initialize(args.database)
    origins = {item.strip().rstrip('/') for item in os.environ.get('WEB_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000').split(',') if item.strip()}
    hours = int(os.environ.get('SESSION_HOURS', '168'))
    if not 1 <= hours <= 720:
        parser.error('SESSION_HOURS harus 1–720.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    server = create_server(args.database, args.host, args.port, origins,
                           os.environ.get('COOKIE_SECURE', 'false').lower() == 'true', hours)
    print(f'Don.Nih! berjalan di http://{args.host}:{args.port} (Supabase PostgreSQL).', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()