from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, Response as FlaskResponse, jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.serving import make_server

from backend.app import ApiError, Application
from backend.db import DEFAULT_DB_NAME, ROOT, connect, initialize, load_env

MAX_BODY = 2_900_000
LOGGER = logging.getLogger('donnih')
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


def create_app(
    database: str | Path,
    allowed_origins: set[str] | None = None,
    secure_cookie: bool = False,
    session_hours: int = 168,
    db_name: str = DEFAULT_DB_NAME,
) -> Flask:
    """Create the Flask application without starting a listener."""
    api = Application(database, session_hours, db_name=db_name)
    origins = allowed_origins or {
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    }
    dist = ROOT / 'frontend' / 'dist'
    flask_app = Flask(__name__)
    flask_app.config['MAX_CONTENT_LENGTH'] = MAX_BODY

    @flask_app.after_request
    def add_security_headers(response):
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY
        return response

    @flask_app.after_request
    def log_request_without_sensitive_data(response):
        # Do not log passwords, cookies, request bodies or query strings.
        LOGGER.info('%s %s %s', request.remote_addr or '-', request.method, request.path)
        return response

    @flask_app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify({'error': str(error)}), error.status

    @flask_app.errorhandler(PyMongoError)
    def handle_database_error(error: PyMongoError):
        LOGGER.exception('Database MongoDB tidak tersedia')
        return jsonify({'error': 'Penyimpanan sedang sibuk. Coba kembali.'}), 503

    @flask_app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        if error.code == 413:
            return jsonify({'error': 'Body permintaan terlalu besar.'}), 413
        return jsonify({'error': error.description}), error.code or 500

    @flask_app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        LOGGER.exception('Kesalahan internal', exc_info=error)
        return jsonify({'error': 'Terjadi kesalahan pada server. Silakan coba kembali.'}), 500

    def set_session_cookie(response: FlaskResponse, token: str | None):
        if token is not None:
            response.set_cookie(
                'donnih_session',
                token,
                max_age=session_hours * 3600 if token else 0,
                httponly=True,
                secure=secure_cookie,
                samesite='Lax',
                path='/',
            )
        return response

    def json_response(data: object, status: int = 200, cookie: str | None = None):
        response = FlaskResponse(
            json.dumps(data, ensure_ascii=False),
            status=status,
            content_type='application/json; charset=utf-8',
        )
        return set_session_cookie(response, cookie)

    def serve_static(raw_path: str):
        path = unquote(raw_path)
        if path.startswith('/uploads/'):
            image = connect(database, db_name=db_name)['uploads'].find_one({'path': path})
            if not image:
                raise ApiError(404, 'Gambar tidak ditemukan.')
            content = bytes(image.get('content', b''))
            content_type = image.get('mime_type') or image.get('content_type') or 'application/octet-stream'
            response = FlaskResponse(content, content_type=content_type)
            response.headers['Cache-Control'] = 'public, max-age=3600'
            return response

        target = (dist / path.lstrip('/')).resolve()
        if not target.is_relative_to(dist.resolve()) or any(part.startswith('.') for part in Path(path).parts):
            raise ApiError(404, 'Berkas tidak ditemukan.')
        if not target.is_file():
            if Path(path).suffix:
                raise ApiError(404, 'Berkas tidak ditemukan.')
            target = dist / 'index.html'
        if not target.exists():
            raise ApiError(
                503,
                'Frontend belum dibangun. Jalankan npm --prefix frontend run build, atau buka Vite port 5173.',
            )
        content_type = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html'}.get(
            target.suffix, mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        )
        return FlaskResponse(target.read_bytes(), content_type=content_type)

    @flask_app.route('/', defaults={'path': ''}, methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    @flask_app.route('/<path:path>', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    def dispatch(path: str):
        if len(request.full_path) > 2048:
            raise ApiError(414, 'URL terlalu panjang.')
        full_path = request.path
        if full_path.startswith('/api/'):
            body = {}
            if request.method not in ('GET', 'HEAD'):
                if request.headers.get('X-Requested-With') != 'donnih-web':
                    raise ApiError(403, 'Header keamanan permintaan tidak valid.')
                origin = request.headers.get('Origin')
                if origin and origin.rstrip('/') not in origins:
                    raise ApiError(403, 'Origin permintaan tidak diizinkan.')
                if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                    raise ApiError(403, 'Permintaan lintas situs tidak diizinkan.')
                if request.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    raise ApiError(415, 'Gunakan Content-Type application/json.')
                if request.headers.get('Transfer-Encoding'):
                    raise ApiError(400, 'Transfer-Encoding tidak didukung.')
                length = request.content_length
                if length is None:
                    length = 0
                if not 0 <= length <= MAX_BODY:
                    raise ApiError(413, 'Body permintaan terlalu besar.')
                try:
                    body = json.loads(request.get_data(cache=False) or b'{}')
                except (ValueError, UnicodeDecodeError) as error:
                    raise ApiError(400, 'JSON tidak valid.') from error
            token = request.cookies.get('donnih_session', '')
            result = api.request(request.method, request.full_path, body, token, request.remote_addr or 'local')
            return json_response(result.data, result.status, result.session)
        if request.method in ('GET', 'HEAD'):
            return serve_static(full_path)
        raise ApiError(405, 'Metode tidak didukung.')

    return flask_app


def create_server(
    database: str | Path,
    host: str = '127.0.0.1',
    port: int = 8000,
    allowed_origins: set[str] | None = None,
    secure_cookie: bool = False,
    session_hours: int = 168,
    db_name: str = DEFAULT_DB_NAME,
):
    """Compatibility helper returning a threaded Werkzeug server for local use."""
    if allowed_origins is None:
        allowed_origins = {
            'http://localhost:5173',
            'http://127.0.0.1:5173',
            f'http://localhost:{port}',
            f'http://127.0.0.1:{port}',
        }
    return make_server(
        host,
        port,
        create_app(database, allowed_origins, secure_cookie, session_hours, db_name),
        threaded=True,
    )


def main():
    load_env()
    default_uri = os.environ.get('MONGODB_URI') or os.environ.get('DATABASE_URL') or ''
    db_name = os.environ.get('MONGODB_DB_NAME', DEFAULT_DB_NAME).strip() or DEFAULT_DB_NAME

    parser = argparse.ArgumentParser(description='API dan web Kedai Don.Nih! (Flask)')
    parser.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8000')))
    parser.add_argument('--database', default=default_uri,
                        help='MongoDB connection URI (default: MONGODB_URI / DATABASE_URL)')
    parser.add_argument('--db-name', default=db_name, help=f'Nama database (default: {DEFAULT_DB_NAME})')
    args = parser.parse_args()
    if not args.database:
        parser.exit(1, 'Gagal: MONGODB_URI belum diatur di environment atau .env.\n')
    initialize(args.database, db_name=args.db_name)
    origins = {
        item.strip().rstrip('/')
        for item in os.environ.get(
            'WEB_ORIGINS',
            'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000',
        ).split(',')
        if item.strip()
    }
    hours = int(os.environ.get('SESSION_HOURS', '168'))
    if not 1 <= hours <= 720:
        parser.error('SESSION_HOURS harus 1–720.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    application = create_app(
        args.database,
        origins,
        os.environ.get('COOKIE_SECURE', 'false').lower() == 'true',
        hours,
        db_name=args.db_name,
    )
    print(f'Don.Nih! Flask berjalan di http://{args.host}:{args.port} (MongoDB: {args.db_name}).', flush=True)
    application.run(host=args.host, port=args.port, threaded=True)


load_env()
_default_uri = os.environ.get('MONGODB_URI') or os.environ.get('DATABASE_URL') or ''
_default_db_name = os.environ.get('MONGODB_DB_NAME', DEFAULT_DB_NAME).strip() or DEFAULT_DB_NAME
app = create_app(
    _default_uri,
    {
        item.strip().rstrip('/')
        for item in os.environ.get(
            'WEB_ORIGINS',
            'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000',
        ).split(',')
        if item.strip()
    },
    os.environ.get('COOKIE_SECURE', 'false').lower() == 'true',
    int(os.environ.get('SESSION_HOURS', '168')),
    db_name=_default_db_name,
)


if __name__ == '__main__':
    main()
