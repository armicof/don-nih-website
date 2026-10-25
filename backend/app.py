"""Authenticated JSON application; business mutations use SQLite transactions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from backend.db import connect, hash_password, now, verify_password

CATEGORIES = {'COFFEE', 'NON-COFFEE', 'DESSERT', 'BREAKFAST', 'MEAL'}
STATUSES = ['WAITING', 'CONFIRMED', 'PROCESSED', 'COMPLETED']
PUBLIC_USER = 'id,email,username,fullname,phone_number,avatar_url,role'
MAX_IMAGE_BYTES = 2 * 1024 * 1024
_MISSING = object()
# Used for a timing-equivalent password check for unknown email addresses.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


@dataclass
class Response:
    data: object
    status: int = 200
    session: str | None = None


def text(value: object, label: str, minimum: int = 1, maximum: int = 100) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ApiError(400, f'{label} harus berisi {minimum}–{maximum} karakter.')
    return value.strip()


def integer(value: object, label: str, minimum: int = 0, maximum: int = 100_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ApiError(400, f'{label} harus bilangan bulat antara {minimum} dan {maximum}.')
    return value


def phone(value: object) -> str:
    result = text(value, 'Nomor telepon', 0, 25)
    if result and not re.fullmatch(r'[+0-9 ()-]{6,25}', result):
        raise ApiError(400, 'Format nomor telepon tidak valid.')
    return result


def public_record(row: sqlite3.Row) -> dict:
    result = dict(row)
    if 'active' in result:
        result['active'] = bool(result['active'])
    return result


class Application:
    def __init__(self, database: str | Path, session_hours: int = 168):
        self.database = database
        self.session_hours = session_hours

    def request(self, method: str, target: str, body: object = _MISSING,
                token: str = '', client_ip: str = 'local') -> Response:
        body = {} if body is _MISSING else body
        if not isinstance(body, dict):
            raise ApiError(400, 'Body JSON harus berupa objek.')
        db = connect(self.database)
        try:
            db.execute('BEGIN' if method == 'GET' else 'BEGIN IMMEDIATE')
            user = None
            if token:
                user = db.execute(
                    f'SELECT {",".join("u." + col for col in PUBLIC_USER.split(","))} FROM users u '
                    'JOIN sessions s ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',
                    (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
            parts = urlsplit(target)
            response = self.dispatch(db, method, parts.path.rstrip('/'), parse_qs(parts.query), body, user, token, client_ip)
            db.commit()
            return response
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ApiError(409, 'Data sudah digunakan atau bertentangan dengan data yang tersimpan.') from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def require_user(user: sqlite3.Row | None, admin: bool = False) -> sqlite3.Row:
        if user is None:
            raise ApiError(401, 'Silakan masuk terlebih dahulu.')
        if admin and user['role'] != 'admin':
            raise ApiError(403, 'Akses ini hanya untuk admin.')
        return user

    @staticmethod
    def session(db: sqlite3.Connection, user_id: str, hours: int) -> str:
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
        db.execute('INSERT INTO sessions VALUES (?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + hours * 3600))
        return token

    @staticmethod
    def user_response(db: sqlite3.Connection, user_id: str) -> dict:
        return {'user': dict(db.execute(f'SELECT {PUBLIC_USER} FROM users WHERE id=?', (user_id,)).fetchone())}

    def dispatch(self, db, method, path, query, body, user, token, client_ip) -> Response:
        if path == '/api/health' and method == 'GET':
            demo = bool(db.execute("SELECT 1 FROM metadata WHERE key='demo_seed'").fetchone())
            return Response({'ok': True, 'storage': 'sqlite', 'demo_data': demo, 'online_payment': False})
        if path == '/api/auth/me' and method == 'GET':
            return Response({'user': dict(user) if user else None})
        if path in ('/api/auth/register', '/api/auth/login') and method == 'POST':
            return self.authenticate(db, path, body, token, client_ip)
        if path == '/api/auth/logout' and method == 'POST':
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
            return Response({'ok': True}, session='')
        if path == '/api/menus' and method == 'GET':
            search = text(query.get('search', [''])[0], 'Pencarian', 0, 100)
            category = query.get('category', [''])[0]
            if category and category not in CATEGORIES:
                raise ApiError(400, 'Kategori tidak valid.')
            rows = db.execute("SELECT * FROM menus WHERE active=1 AND instr(lower(name || ' ' || description),lower(?))>0 "
                              "AND (?='' OR category=?) ORDER BY id", (search, category, category)).fetchall()
            return Response([public_record(row) for row in rows])
        if path == '/api/toppings' and method == 'GET':
            return Response([public_record(row) for row in db.execute('SELECT * FROM toppings WHERE active=1 ORDER BY id')])

        user = self.require_user(user, path.startswith('/api/admin/'))
        uid = user['id']
        if path == '/api/profile' and method == 'PATCH':
            name = text(body.get('fullname', user['fullname']), 'Nama lengkap', 2, 100)
            number = phone(body.get('phone_number', user['phone_number']))
            if set(body) - {'fullname', 'phone_number'}:
                raise ApiError(400, 'Hanya nama lengkap dan telepon yang dapat diperbarui.')
            db.execute('UPDATE users SET fullname=?,phone_number=? WHERE id=?', (name, number, uid))
            return Response(self.user_response(db, uid))
        if path == '/api/uploads' and method == 'POST':
            return self.upload(db, body, user)
        if path == '/api/favorites' and method == 'GET':
            return Response([row['menu_id'] for row in db.execute(
                'SELECT f.menu_id FROM favorites f JOIN menus m ON m.id=f.menu_id WHERE f.user_id=? AND m.active=1 ORDER BY f.menu_id', (uid,))])
        match = re.fullmatch(r'/api/favorites/(\d+)', path)
        if match and method in ('PUT', 'DELETE'):
            mid = integer(int(match[1]), 'ID menu', 1, 2**63 - 1)
            if method == 'PUT':
                self.active_menu(db, mid)
                db.execute('INSERT OR IGNORE INTO favorites VALUES (?,?)', (uid, mid))
            else:
                db.execute('DELETE FROM favorites WHERE user_id=? AND menu_id=?', (uid, mid))
            return Response({'ok': True})
        if path == '/api/cart' and method == 'GET':
            return Response(self.cart(db, uid))
        if path == '/api/cart' and method == 'POST':
            mid = integer(body.get('menu_id'), 'Menu', 1)
            self.active_menu(db, mid)
            quantity = integer(body.get('quantity', 1), 'Jumlah', 1, 99)
            ids = self.validate_toppings(db, body.get('topping_ids'))
            count = db.execute('SELECT COUNT(*) FROM carts WHERE user_id=?', (uid,)).fetchone()[0]
            if count >= 100:
                raise ApiError(400, 'Keranjang maksimal 100 baris. Selesaikan pesanan terlebih dahulu.')
            cursor = db.execute('INSERT INTO carts (user_id,menu_id,quantity) VALUES (?,?,?)', (uid, mid, quantity))
            db.executemany('INSERT INTO cart_toppings VALUES (?,?)', [(cursor.lastrowid, tid) for tid in ids])
            return Response(self.cart(db, uid), 201)
        match = re.fullmatch(r'/api/cart/(\d+)', path)
        if match and method in ('PATCH', 'DELETE'):
            cid = integer(int(match[1]), 'ID keranjang', 1, 2**63 - 1)
            if not db.execute('SELECT 1 FROM carts WHERE id=? AND user_id=?', (cid, uid)).fetchone():
                raise ApiError(404, 'Item keranjang tidak ditemukan.')
            if method == 'DELETE':
                db.execute('DELETE FROM carts WHERE id=? AND user_id=?', (cid, uid))
            else:
                quantity = integer(body.get('quantity'), 'Jumlah', 1, 99)
                db.execute('UPDATE carts SET quantity=? WHERE id=? AND user_id=?', (quantity, cid, uid))
            return Response(self.cart(db, uid))
        if path == '/api/orders' and method == 'POST':
            return self.checkout(db, user, body)
        if path in ('/api/orders', '/api/admin/orders') and method == 'GET':
            rows = db.execute('SELECT id FROM orders ' + ('WHERE user_id=? ' if path == '/api/orders' else '') + 'ORDER BY id DESC',
                              (uid,) if path == '/api/orders' else ()).fetchall()
            return Response([self.order(db, row['id']) for row in rows])
        match = re.fullmatch(r'/api/orders/(\d+)', path)
        if match and method == 'GET':
            order = self.order(db, integer(int(match[1]), 'ID pesanan', 1, 2**63 - 1))
            if order['user_id'] != uid and user['role'] != 'admin':
                raise ApiError(404, 'Pesanan tidak ditemukan.')
            return Response(order)
        match = re.fullmatch(r'/api/admin/orders/(\d+)/status', path)
        if match and method == 'PATCH':
            order = self.order(db, integer(int(match[1]), 'ID pesanan', 1, 2**63 - 1))
            status = body.get('order_status')
            current = order['order_status']
            if body.get('expected_status') != current:
                raise ApiError(409, 'Status telah berubah. Muat ulang pesanan sebelum melanjutkan.')
            if current == 'COMPLETED' or status != STATUSES[STATUSES.index(current) + 1]:
                raise ApiError(400, 'Status harus berurutan: WAITING → CONFIRMED → PROCESSED → COMPLETED.')
            timestamp = now()
            db.execute('UPDATE orders SET order_status=?,updated_at=? WHERE id=?', (status, timestamp, order['id']))
            db.execute('INSERT INTO order_events (order_id,status,actor_id,created_at) VALUES (?,?,?,?)',
                       (order['id'], status, uid, timestamp))
            return Response(self.order(db, order['id']))
        if path.startswith('/api/admin/'):
            return self.admin_catalog(db, method, path, body)
        raise ApiError(404, 'Endpoint tidak ditemukan.')

    def authenticate(self, db, path, body, old_token, client_ip) -> Response:
        # Persist rate limits even when login fails; no user write has occurred here.
        epoch = int(time.time())
        key = hashlib.sha256(client_ip.encode()).hexdigest()
        db.execute('DELETE FROM auth_attempts WHERE window_start<?', (epoch - 600,))
        attempt = db.execute('SELECT * FROM auth_attempts WHERE key=?', (key,)).fetchone()
        if attempt and attempt['attempts'] >= 20:
            raise ApiError(429, 'Terlalu banyak percobaan. Coba kembali dalam 10 menit.')
        db.execute('INSERT INTO auth_attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1', (key, epoch))
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        email = text(body.get('email'), 'Email', 3, 254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ApiError(400, 'Format email tidak valid.')
        password = body.get('password')
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise ApiError(400, 'Password harus berisi 1–128 karakter.')
        if path.endswith('/register'):
            if len(password) < 8:
                raise ApiError(400, 'Password minimal 8 karakter.')
            username = text(body.get('username'), 'Username', 3, 30)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', username):
                raise ApiError(400, 'Username hanya boleh huruf, angka, titik, garis bawah, atau tanda hubung.')
            fullname = text(body.get('fullname'), 'Nama lengkap', 2, 100)
            number = phone(body.get('phone_number', ''))
            uid = str(uuid.uuid4())
            # Role is never accepted from a browser. Admins are provisioned by CLI.
            db.execute('INSERT INTO users (id,email,username,fullname,phone_number,password_hash,created_at) VALUES (?,?,?,?,?,?,?)',
                       (uid, email, username, fullname, number, hash_password(password), now()))
        else:
            row = db.execute('SELECT id,password_hash FROM users WHERE email=?', (email,)).fetchone()
            valid = verify_password(password, row['password_hash'] if row else DUMMY_HASH)
            if not row or not valid:
                raise ApiError(401, 'Email atau password tidak sesuai.')
            uid = row['id']
        if old_token:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(old_token.encode()).hexdigest(),))
        session = self.session(db, uid, self.session_hours)
        return Response(self.user_response(db, uid), 201 if path.endswith('/register') else 200, session)

    @staticmethod
    def active_menu(db, mid):
        menu = db.execute('SELECT * FROM menus WHERE id=? AND active=1', (mid,)).fetchone()
        if not menu:
            raise ApiError(404, 'Menu tidak ditemukan atau sudah tidak tersedia.')
        return menu

    @staticmethod
    def validate_toppings(db, ids):
        if not isinstance(ids, list) or len(ids) > 50 or any(type(tid) is not int for tid in ids) or len(set(ids)) != len(ids):
            raise ApiError(400, 'Pilihan topping tidak valid atau duplikat.')
        toppings = []
        for tid in ids:
            row = db.execute('SELECT * FROM toppings WHERE id=? AND active=1', (tid,)).fetchone()
            if not row:
                raise ApiError(400, 'Salah satu topping sudah tidak tersedia.')
            toppings.append(row)
        if sum(t['kind'] == 'size' for t in toppings) != 1 or sum(t['kind'] == 'temperature' for t in toppings) != 1:
            raise ApiError(400, 'Pilih tepat satu ukuran dan satu suhu.')
        return ids

    @staticmethod
    def cart(db, uid):
        rows = db.execute('SELECT c.id,c.menu_id,c.quantity,m.name,m.img,m.price,m.active FROM carts c '
                          'JOIN menus m ON m.id=c.menu_id WHERE c.user_id=? ORDER BY c.id', (uid,)).fetchall()
        items = []
        for row in rows:
            toppings = [public_record(t) for t in db.execute('SELECT t.* FROM toppings t JOIN cart_toppings ct '
                        'ON ct.topping_id=t.id WHERE ct.cart_id=? ORDER BY t.id', (row['id'],))]
            unit = row['price'] + sum(t['price'] for t in toppings)
            items.append({'id': row['id'], 'menu_id': row['menu_id'], 'name': row['name'], 'img': row['img'],
                          'quantity': row['quantity'], 'unit_price': unit, 'total': unit * row['quantity'],
                          'toppings': toppings, 'available': bool(row['active']) and all(t['active'] for t in toppings)})
        return {'items': items, 'total': sum(item['total'] for item in items)}

    def checkout(self, db, user, body):
        key = text(body.get('idempotency_key'), 'Kunci checkout', 16, 100)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
            raise ApiError(400, 'Kunci checkout tidak valid.')
        previous = db.execute('SELECT id FROM orders WHERE user_id=? AND idempotency_key=?', (user['id'], key)).fetchone()
        if previous:
            return Response(self.order(db, previous['id']))
        cart = self.cart(db, user['id'])
        if not cart['items']:
            raise ApiError(400, 'Keranjang masih kosong.')
        if not all(item['available'] for item in cart['items']):
            raise ApiError(409, 'Menu atau topping tidak tersedia. Hapus item tersebut dari keranjang.')
        timestamp = now()
        cursor = db.execute('INSERT INTO orders (user_id,customer_name,net_income,idempotency_key,created_at,updated_at) '
                            'VALUES (?,?,?,?,?,?)', (user['id'], user['fullname'], cart['total'], key, timestamp, timestamp))
        oid = cursor.lastrowid
        for item in cart['items']:
            db.execute('INSERT INTO order_details (order_id,menu_id,name,img,quantity,price,toppings_json) VALUES (?,?,?,?,?,?,?)',
                       (oid, item['menu_id'], item['name'], item['img'], item['quantity'], item['unit_price'],
                        json.dumps([{'id': t['id'], 'name': t['name'], 'price': t['price']} for t in item['toppings']])))
        db.execute('INSERT INTO order_events (order_id,status,actor_id,created_at) VALUES (?,?,?,?)',
                   (oid, 'WAITING', user['id'], timestamp))
        db.execute('DELETE FROM carts WHERE user_id=?', (user['id'],))
        return Response(self.order(db, oid), 201)

    @staticmethod
    def order(db, oid):
        row = db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
        if not row:
            raise ApiError(404, 'Pesanan tidak ditemukan.')
        result = dict(row)
        del result['idempotency_key']
        items = []
        for detail in db.execute('SELECT * FROM order_details WHERE order_id=? ORDER BY id', (oid,)):
            item = dict(detail)
            item['toppings'] = json.loads(item.pop('toppings_json'))
            item['total'] = item['quantity'] * item['price']
            items.append(item)
        result['items'] = items
        result['events'] = [dict(event) for event in db.execute('SELECT status,created_at FROM order_events WHERE order_id=? ORDER BY id', (oid,))]
        return result

    @staticmethod
    def image_path(db, value):
        path = text(value, 'Gambar', 1, 200)
        assets = {'LogoDonnih.png', 'americano.png', 'appletea.png', 'caffelatte.png', 'curry.png',
                  'espresso.png', 'menu_cappucino.png', 'orderhistory.png', 'pancake.png', 'peachtea.png'}
        if path.startswith('/images/') and path[len('/images/'):] in assets:
            return path
        if db.execute("SELECT 1 FROM uploads WHERE path=? AND kind='menu'", (path,)).fetchone():
            return path
        raise ApiError(400, 'Gunakan aset bawaan atau unggah gambar menu terlebih dahulu.')

    def admin_catalog(self, db, method, path, body):
        match = re.fullmatch(r'/api/admin/(menus|toppings)(?:/(\d+))?', path)
        if not match:
            raise ApiError(404, 'Endpoint admin tidak ditemukan.')
        table = match[1]
        record_id = integer(int(match[2]), 'ID katalog', 1, 2**63 - 1) if match[2] else None
        if method == 'GET' and record_id is None:
            return Response([public_record(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY id')])
        existing = None
        if record_id is not None:
            existing = db.execute(f'SELECT * FROM {table} WHERE id=?', (record_id,)).fetchone()
            if not existing:
                raise ApiError(404, 'Data tidak ditemukan.')
        if method == 'DELETE' and existing:
            if table == 'toppings' and existing['kind'] != 'extra':
                raise ApiError(400, 'Ukuran dan suhu bawaan tidak dapat dihapus.')
            db.execute(f'UPDATE {table} SET active=0 WHERE id=?', (record_id,))
            return Response({'ok': True})
        if not ((method == 'POST' and record_id is None) or (method == 'PATCH' and existing)):
            raise ApiError(405, 'Metode tidak didukung.')
        allowed = {'name', 'price', 'active'} | ({'description', 'category', 'img'} if table == 'menus' else set())
        if set(body) - allowed:
            raise ApiError(400, 'Kolom katalog tidak dikenal.')
        values = dict(existing) if existing else {}
        values.update(body)
        name = text(values.get('name'), 'Nama', 2, 100)
        price = integer(values.get('price'), 'Harga')
        active = values.get('active', True)
        if 'active' in body and type(body['active']) is not bool:
            raise ApiError(400, 'Status aktif harus boolean.')
        if table == 'menus':
            desc = text(values.get('description', ''), 'Deskripsi', 0, 1000)
            category = values.get('category')
            if not isinstance(category, str) or category not in CATEGORIES:
                raise ApiError(400, 'Kategori tidak valid.')
            image = self.image_path(db, values.get('img', '/images/LogoDonnih.png'))
            if existing:
                db.execute('UPDATE menus SET name=?,price=?,active=?,description=?,category=?,img=? WHERE id=?',
                           (name, price, int(active), desc, category, image, record_id))
            else:
                record_id = db.execute('INSERT INTO menus (name,price,active,description,category,img) VALUES (?,?,?,?,?,?)',
                                       (name, price, int(active), desc, category, image)).lastrowid
        else:
            if existing and existing['kind'] != 'extra' and (name != existing['name'] or not active):
                raise ApiError(400, 'Ukuran dan suhu bawaan hanya dapat diubah harganya.')
            if existing:
                db.execute('UPDATE toppings SET name=?,price=?,active=? WHERE id=?', (name, price, int(active), record_id))
            else:
                record_id = db.execute("INSERT INTO toppings (name,price,active,kind) VALUES (?,?,?,'extra')", (name, price, int(active))).lastrowid
        return Response(public_record(db.execute(f'SELECT * FROM {table} WHERE id=?', (record_id,)).fetchone()), 201 if method == 'POST' else 200)

    def upload(self, db, body, user):
        kind = body.get('kind')
        if kind not in ('avatar', 'menu'):
            raise ApiError(400, 'Jenis unggahan harus avatar atau menu.')
        if kind == 'menu':
            self.require_user(user, admin=True)
        data = body.get('data_url')
        if not isinstance(data, str) or len(data) > 2_800_000:
            raise ApiError(413, 'Gambar maksimal 2 MB.')
        match = re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)', data)
        if not match:
            raise ApiError(400, 'Format gambar harus PNG, JPEG, atau WebP.')
        try:
            raw = base64.b64decode(match[2], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(400, 'Data gambar tidak valid.') from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ApiError(413, 'Gambar maksimal 2 MB.')
        mime = match[1]
        valid = ((mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or
                 (mime == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff')) or
                 (mime == 'image/webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'))
        if not valid:
            raise ApiError(400, 'Isi berkas tidak cocok dengan format gambarnya.')
        used = db.execute('SELECT COALESCE(SUM(length(content)),0) FROM uploads WHERE user_id=?', (user['id'],)).fetchone()[0]
        if used + len(raw) > 100 * MAX_IMAGE_BYTES:
            raise ApiError(413, 'Kuota unggahan akun tercapai (200 MB).')
        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[mime]
        path = f'/uploads/{uuid.uuid4().hex}.{extension}'
        db.execute('INSERT INTO uploads VALUES (?,?,?,?,?,?)', (path, user['id'], kind, mime, raw, now()))
        if kind == 'avatar':
            old = user['avatar_url']
            db.execute('UPDATE users SET avatar_url=? WHERE id=?', (path, user['id']))
            if old:
                db.execute("DELETE FROM uploads WHERE path=? AND user_id=? AND kind='avatar'", (old, user['id']))
        return Response({'url': path}, 201)
