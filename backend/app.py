from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bson import Binary
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from backend.db import DEFAULT_DB_NAME, connect, hash_password, now, verify_password

CATEGORIES = {'COFFEE', 'NON-COFFEE', 'DESSERT', 'BREAKFAST', 'MEAL'}
STATUSES = ['WAITING', 'CONFIRMED', 'PROCESSED', 'COMPLETED']
PUBLIC_USER_FIELDS = ['id', 'email', 'username', 'fullname', 'phone_number', 'avatar_url', 'role']
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


def public_record(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    result = {k: v for k, v in row.items() if k != '_id'}
    if 'active' in result:
        result['active'] = bool(result['active'])
    return result


def _project_user(user_doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user_doc:
        return None
    return {
        'id': user_doc.get('id'),
        'email': user_doc.get('email'),
        'username': user_doc.get('username'),
        'fullname': user_doc.get('fullname'),
        'phone_number': user_doc.get('phone_number', ''),
        'avatar_url': user_doc.get('avatar_url'),
        'role': user_doc.get('role', 'user'),
    }


def _next_seq(db: Database[Any], name: str) -> int:
    doc = db['counters'].find_one_and_update(
        {'_id': name},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc['seq'])


class Application:
    def __init__(self, database: str | Path, session_hours: int = 168, db_name: str = DEFAULT_DB_NAME):
        self.database = database
        self.session_hours = session_hours
        self.db_name = db_name

    def request(
        self,
        method: str,
        target: str,
        body: object = _MISSING,
        token: str = '',
        client_ip: str = 'local',
    ) -> Response:
        body = {} if body is _MISSING else body
        if not isinstance(body, dict):
            raise ApiError(400, 'Body JSON harus berupa objek.')
        db = connect(self.database, db_name=self.db_name)
        try:
            user = None
            if token:
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                session_doc = db['sessions'].find_one(
                    {'token_hash': token_hash, 'expires_at': {'$gt': int(time.time())}}
                )
                if session_doc:
                    raw_user = db['users'].find_one({'id': session_doc['user_id']})
                    user = _project_user(raw_user)
            parts = urlsplit(target)
            return self.dispatch(
                db,
                method,
                parts.path.rstrip('/'),
                parse_qs(parts.query),
                body,
                user,
                token,
                client_ip,
            )
        except DuplicateKeyError as exc:
            raise ApiError(409, 'Data sudah digunakan atau bertentangan dengan data yang tersimpan.') from exc

    @staticmethod
    def require_user(user: dict[str, Any] | None, admin: bool = False) -> dict[str, Any]:
        if user is None:
            raise ApiError(401, 'Silakan masuk terlebih dahulu.')
        if admin and user.get('role') != 'admin':
            raise ApiError(403, 'Akses ini hanya untuk admin.')
        return user

    @staticmethod
    def session(db: Database[Any], user_id: str, hours: int) -> str:
        token = secrets.token_urlsafe(32)
        current_epoch = int(time.time())
        db['sessions'].delete_many({'expires_at': {'$lte': current_epoch}})
        db['sessions'].insert_one(
            {
                'token_hash': hashlib.sha256(token.encode()).hexdigest(),
                'user_id': user_id,
                'expires_at': current_epoch + hours * 3600,
            }
        )
        return token

    @staticmethod
    def user_response(db: Database[Any], user_id: str) -> dict[str, Any]:
        raw_user = db['users'].find_one({'id': user_id})
        return {'user': _project_user(raw_user)}

    def dispatch(
        self,
        db: Database[Any],
        method: str,
        path: str,
        query: dict[str, list[str]],
        body: dict[str, Any],
        user: dict[str, Any] | None,
        token: str,
        client_ip: str,
    ) -> Response:
        if path == '/api/health' and method == 'GET':
            demo = bool(db['metadata'].find_one({'key': 'demo_seed'}))
            return Response(
                {
                    'ok': True,
                    'storage': 'mongodb',
                    'database': self.db_name,
                    'demo_data': demo,
                    'online_payment': False,
                }
            )
        if path == '/api/auth/me' and method == 'GET':
            return Response({'user': dict(user) if user else None})
        if path in ('/api/auth/register', '/api/auth/login') and method == 'POST':
            return self.authenticate(db, path, body, token, client_ip)
        if path == '/api/auth/logout' and method == 'POST':
            if token:
                db['sessions'].delete_one({'token_hash': hashlib.sha256(token.encode()).hexdigest()})
            return Response({'ok': True}, session='')
        if path == '/api/menus' and method == 'GET':
            search = text(query.get('search', [''])[0], 'Pencarian', 0, 100)
            category = query.get('category', [''])[0]
            if category and category not in CATEGORIES:
                raise ApiError(400, 'Kategori tidak valid.')

            mongo_filter: dict[str, Any] = {'active': 1}
            if category:
                mongo_filter['category'] = category
            if search:
                pattern = re.escape(search)
                mongo_filter['$or'] = [
                    {'name': {'$regex': pattern, '$options': 'i'}},
                    {'description': {'$regex': pattern, '$options': 'i'}},
                ]

            rows = db['menus'].find(mongo_filter).sort('id', ASCENDING)
            return Response([public_record(row) for row in rows])
        if path == '/api/toppings' and method == 'GET':
            rows = db['toppings'].find({'active': 1}).sort('id', ASCENDING)
            return Response([public_record(row) for row in rows])

        user = self.require_user(user, path.startswith('/api/admin/'))
        uid = user['id']

        if path == '/api/profile' and method == 'PATCH':
            name = text(body.get('fullname', user['fullname']), 'Nama lengkap', 2, 100)
            number = phone(body.get('phone_number', user.get('phone_number', '')))
            if set(body) - {'fullname', 'phone_number'}:
                raise ApiError(400, 'Hanya nama lengkap dan telepon yang dapat diperbarui.')
            db['users'].update_one({'id': uid}, {'$set': {'fullname': name, 'phone_number': number}})
            return Response(self.user_response(db, uid))

        if path == '/api/uploads' and method == 'POST':
            return self.upload(db, body, user)

        if path == '/api/favorites' and method == 'GET':
            favs = list(db['favorites'].find({'user_id': uid}))
            menu_ids = [f['menu_id'] for f in favs]
            if not menu_ids:
                return Response([])
            active_menus = {
                m['id']
                for m in db['menus'].find({'id': {'$in': menu_ids}, 'active': 1}, {'id': 1})
            }
            return Response(sorted(mid for mid in menu_ids if mid in active_menus))

        match = re.fullmatch(r'/api/favorites/(\d+)', path)
        if match and method in ('PUT', 'DELETE'):
            mid = integer(int(match[1]), 'ID menu', 1, 2**63 - 1)
            if method == 'PUT':
                self.active_menu(db, mid)
                db['favorites'].update_one(
                    {'user_id': uid, 'menu_id': mid},
                    {'$setOnInsert': {'user_id': uid, 'menu_id': mid}},
                    upsert=True,
                )
            else:
                db['favorites'].delete_one({'user_id': uid, 'menu_id': mid})
            return Response({'ok': True})

        if path == '/api/cart' and method == 'GET':
            return Response(self.cart(db, uid))

        if path == '/api/cart' and method == 'POST':
            mid = integer(body.get('menu_id'), 'Menu', 1)
            self.active_menu(db, mid)
            quantity = integer(body.get('quantity', 1), 'Jumlah', 1, 99)
            ids = self.validate_toppings(db, body.get('topping_ids'))
            count = db['carts'].count_documents({'user_id': uid})
            if count >= 100:
                raise ApiError(400, 'Keranjang maksimal 100 baris. Selesaikan pesanan terlebih dahulu.')
            cart_id = _next_seq(db, 'carts')
            db['carts'].insert_one(
                {
                    'id': cart_id,
                    'user_id': uid,
                    'menu_id': mid,
                    'quantity': quantity,
                    'topping_ids': ids,
                }
            )
            return Response(self.cart(db, uid), 201)

        match = re.fullmatch(r'/api/cart/(\d+)', path)
        if match and method in ('PATCH', 'DELETE'):
            cid = integer(int(match[1]), 'ID keranjang', 1, 2**63 - 1)
            existing_cart = db['carts'].find_one({'id': cid, 'user_id': uid})
            if not existing_cart:
                raise ApiError(404, 'Item keranjang tidak ditemukan.')
            if method == 'DELETE':
                db['carts'].delete_one({'id': cid, 'user_id': uid})
            else:
                quantity = integer(body.get('quantity'), 'Jumlah', 1, 99)
                db['carts'].update_one({'id': cid, 'user_id': uid}, {'$set': {'quantity': quantity}})
            return Response(self.cart(db, uid))

        if path == '/api/orders' and method == 'POST':
            return self.checkout(db, user, body)

        if path in ('/api/orders', '/api/admin/orders') and method == 'GET':
            order_filter = {'user_id': uid} if path == '/api/orders' else {}
            rows = db['orders'].find(order_filter, {'id': 1}).sort('id', DESCENDING)
            return Response([self.order(db, row['id']) for row in rows])

        match = re.fullmatch(r'/api/orders/(\d+)', path)
        if match and method == 'GET':
            order = self.order(db, integer(int(match[1]), 'ID pesanan', 1, 2**63 - 1))
            if order['user_id'] != uid and user.get('role') != 'admin':
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
            db['orders'].update_one(
                {'id': order['id']},
                {'$set': {'order_status': status, 'updated_at': timestamp}},
            )
            db['order_events'].insert_one(
                {
                    'id': _next_seq(db, 'order_events'),
                    'order_id': order['id'],
                    'status': status,
                    'actor_id': uid,
                    'created_at': timestamp,
                }
            )
            return Response(self.order(db, order['id']))

        if path.startswith('/api/admin/'):
            return self.admin_catalog(db, method, path, body)

        raise ApiError(404, 'Endpoint tidak ditemukan.')

    def authenticate(
        self,
        db: Database[Any],
        path: str,
        body: dict[str, Any],
        old_token: str,
        client_ip: str,
    ) -> Response:
        epoch = int(time.time())
        key = hashlib.sha256(client_ip.encode()).hexdigest()
        db['auth_attempts'].delete_many({'window_start': {'$lt': epoch - 600}})
        attempt = db['auth_attempts'].find_one({'key': key})
        if attempt and attempt.get('attempts', 0) >= 20:
            raise ApiError(429, 'Terlalu banyak percobaan. Coba kembali dalam 10 menit.')
        db['auth_attempts'].update_one(
            {'key': key},
            {'$inc': {'attempts': 1}, '$setOnInsert': {'key': key, 'window_start': epoch}},
            upsert=True,
        )

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
            db['users'].insert_one(
                {
                    'id': uid,
                    'email': email,
                    'username': username,
                    'fullname': fullname,
                    'phone_number': number,
                    'avatar_url': None,
                    'role': 'user',
                    'password_hash': hash_password(password),
                    'created_at': now(),
                }
            )
        else:
            row = db['users'].find_one({'email': email})
            valid = verify_password(password, row['password_hash'] if row else DUMMY_HASH)
            if not row or not valid:
                raise ApiError(401, 'Email atau password tidak sesuai.')
            uid = row['id']

        if old_token:
            db['sessions'].delete_one({'token_hash': hashlib.sha256(old_token.encode()).hexdigest()})
        session = self.session(db, uid, self.session_hours)
        return Response(self.user_response(db, uid), 201 if path.endswith('/register') else 200, session)

    @staticmethod
    def active_menu(db: Database[Any], mid: int) -> dict[str, Any]:
        menu = db['menus'].find_one({'id': mid, 'active': 1})
        if not menu:
            raise ApiError(404, 'Menu tidak ditemukan atau sudah tidak tersedia.')
        return public_record(menu)

    @staticmethod
    def validate_toppings(db: Database[Any], ids: object) -> list[int]:
        if (
            not isinstance(ids, list)
            or len(ids) > 50
            or any(type(tid) is not int for tid in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ApiError(400, 'Pilihan topping tidak valid atau duplikat.')
        toppings = []
        for tid in ids:
            row = db['toppings'].find_one({'id': tid, 'active': 1})
            if not row:
                raise ApiError(400, 'Salah satu topping sudah tidak tersedia.')
            toppings.append(row)
        if sum(t.get('kind') == 'size' for t in toppings) != 1 or sum(t.get('kind') == 'temperature' for t in toppings) != 1:
            raise ApiError(400, 'Pilih tepat satu ukuran dan satu suhu.')
        return ids

    @staticmethod
    def cart(db: Database[Any], uid: str) -> dict[str, Any]:
        cart_rows = list(db['carts'].find({'user_id': uid}).sort('id', ASCENDING))
        items = []
        for row in cart_rows:
            menu = db['menus'].find_one({'id': row['menu_id']}) or {}
            t_ids = row.get('topping_ids', [])
            topping_docs = list(db['toppings'].find({'id': {'$in': t_ids}})) if t_ids else []
            topping_by_id = {t['id']: public_record(t) for t in topping_docs}
            toppings = [topping_by_id[tid] for tid in t_ids if tid in topping_by_id]
            menu_price = int(menu.get('price', 0))
            unit = menu_price + sum(int(t.get('price', 0)) for t in toppings)
            menu_active = bool(menu.get('active', 0))
            items.append(
                {
                    'id': row['id'],
                    'menu_id': row['menu_id'],
                    'name': menu.get('name', ''),
                    'img': menu.get('img', ''),
                    'quantity': row['quantity'],
                    'unit_price': unit,
                    'total': unit * row['quantity'],
                    'toppings': toppings,
                    'available': menu_active and all(t.get('active') for t in toppings),
                }
            )
        return {'items': items, 'total': sum(item['total'] for item in items)}

    def checkout(self, db: Database[Any], user: dict[str, Any], body: dict[str, Any]) -> Response:
        key = text(body.get('idempotency_key'), 'Kunci checkout', 16, 100)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
            raise ApiError(400, 'Kunci checkout tidak valid.')
        previous = db['orders'].find_one({'user_id': user['id'], 'idempotency_key': key}, {'id': 1})
        if previous:
            return Response(self.order(db, previous['id']))
        cart = self.cart(db, user['id'])
        if not cart['items']:
            raise ApiError(400, 'Keranjang masih kosong.')
        if not all(item['available'] for item in cart['items']):
            raise ApiError(409, 'Menu atau topping tidak tersedia. Hapus item tersebut dari keranjang.')

        timestamp = now()
        oid = _next_seq(db, 'orders')
        order_details = []
        for item in cart['items']:
            order_details.append(
                {
                    'id': _next_seq(db, 'order_details'),
                    'order_id': oid,
                    'menu_id': item['menu_id'],
                    'name': item['name'],
                    'img': item['img'],
                    'quantity': item['quantity'],
                    'price': item['unit_price'],
                    'toppings_json': json.dumps(
                        [{'id': t['id'], 'name': t['name'], 'price': t['price']} for t in item['toppings']]
                    ),
                }
            )

        db['orders'].insert_one(
            {
                'id': oid,
                'user_id': user['id'],
                'customer_name': user['fullname'],
                'net_income': cart['total'],
                'order_status': 'WAITING',
                'idempotency_key': key,
                'created_at': timestamp,
                'updated_at': timestamp,
            }
        )
        if order_details:
            db['order_details'].insert_many(order_details)
        db['order_events'].insert_one(
            {
                'id': _next_seq(db, 'order_events'),
                'order_id': oid,
                'status': 'WAITING',
                'actor_id': user['id'],
                'created_at': timestamp,
            }
        )
        db['carts'].delete_many({'user_id': user['id']})
        return Response(self.order(db, oid), 201)

    @staticmethod
    def order(db: Database[Any], oid: int) -> dict[str, Any]:
        row = db['orders'].find_one({'id': oid})
        if not row:
            raise ApiError(404, 'Pesanan tidak ditemukan.')
        result = {k: v for k, v in row.items() if k != '_id'}
        result.pop('idempotency_key', None)

        items = []
        for detail in db['order_details'].find({'order_id': oid}).sort('id', ASCENDING):
            item = {k: v for k, v in detail.items() if k != '_id'}
            raw_toppings = item.pop('toppings_json', '[]')
            item['toppings'] = json.loads(raw_toppings) if isinstance(raw_toppings, str) else raw_toppings
            item['total'] = item['quantity'] * item['price']
            items.append(item)

        result['items'] = items
        result['events'] = [
            {'status': ev.get('status'), 'created_at': ev.get('created_at')}
            for ev in db['order_events'].find({'order_id': oid}).sort('id', ASCENDING)
        ]
        return result

    @staticmethod
    def image_path(db: Database[Any], value: object) -> str:
        path = text(value, 'Gambar', 1, 200)
        assets = {
            'LogoDonnih.png',
            'americano.png',
            'appletea.png',
            'caffelatte.png',
            'curry.png',
            'espresso.png',
            'menu_cappucino.png',
            'orderhistory.png',
            'pancake.png',
            'peachtea.png',
        }
        if path.startswith('/images/') and path[len('/images/') :] in assets:
            return path
        if db['uploads'].find_one({'path': path, 'kind': 'menu'}, {'_id': 1}):
            return path
        raise ApiError(400, 'Gunakan aset bawaan atau unggah gambar menu terlebih dahulu.')

    def admin_catalog(self, db: Database[Any], method: str, path: str, body: dict[str, Any]) -> Response:
        match = re.fullmatch(r'/api/admin/(menus|toppings)(?:/(\d+))?', path)
        if not match:
            raise ApiError(404, 'Endpoint admin tidak ditemukan.')
        collection_name = match[1]
        record_id = integer(int(match[2]), 'ID katalog', 1, 2**63 - 1) if match[2] else None

        if method == 'GET' and record_id is None:
            rows = db[collection_name].find({}).sort('id', ASCENDING)
            return Response([public_record(row) for row in rows])

        existing = None
        if record_id is not None:
            existing = db[collection_name].find_one({'id': record_id})
            if not existing:
                raise ApiError(404, 'Data tidak ditemukan.')

        if method == 'DELETE' and existing:
            if collection_name == 'toppings' and existing.get('kind') != 'extra':
                raise ApiError(400, 'Ukuran dan suhu bawaan tidak dapat dihapus.')
            db[collection_name].update_one({'id': record_id}, {'$set': {'active': 0}})
            return Response({'ok': True})

        if not ((method == 'POST' and record_id is None) or (method == 'PATCH' and existing)):
            raise ApiError(405, 'Metode tidak didukung.')

        allowed = {'name', 'price', 'active'} | (
            {'description', 'category', 'img'} if collection_name == 'menus' else set()
        )
        if set(body) - allowed:
            raise ApiError(400, 'Kolom katalog tidak dikenal.')

        values = {k: v for k, v in existing.items() if k != '_id'} if existing else {}
        values.update(body)
        name = text(values.get('name'), 'Nama', 2, 100)
        price = integer(values.get('price'), 'Harga')
        active = values.get('active', True)
        if 'active' in body and type(body['active']) is not bool:
            raise ApiError(400, 'Status aktif harus boolean.')

        if collection_name == 'menus':
            desc = text(values.get('description', ''), 'Deskripsi', 0, 1000)
            category = values.get('category')
            if not isinstance(category, str) or category not in CATEGORIES:
                raise ApiError(400, 'Kategori tidak valid.')
            image = self.image_path(db, values.get('img', '/images/LogoDonnih.png'))
            if existing:
                db['menus'].update_one(
                    {'id': record_id},
                    {
                        '$set': {
                            'name': name,
                            'price': price,
                            'active': int(active),
                            'description': desc,
                            'category': category,
                            'img': image,
                        }
                    },
                )
            else:
                record_id = _next_seq(db, 'menus')
                db['menus'].insert_one(
                    {
                        'id': record_id,
                        'name': name,
                        'price': price,
                        'active': int(active),
                        'description': desc,
                        'category': category,
                        'img': image,
                    }
                )
        else:
            if existing and existing.get('kind') != 'extra' and (name != existing.get('name') or not active):
                raise ApiError(400, 'Ukuran dan suhu bawaan hanya dapat diubah harganya.')
            if existing:
                db['toppings'].update_one(
                    {'id': record_id},
                    {'$set': {'name': name, 'price': price, 'active': int(active)}},
                )
            else:
                record_id = _next_seq(db, 'toppings')
                db['toppings'].insert_one(
                    {
                        'id': record_id,
                        'name': name,
                        'price': price,
                        'active': int(active),
                        'kind': 'extra',
                    }
                )

        updated_doc = db[collection_name].find_one({'id': record_id})
        return Response(public_record(updated_doc), 201 if method == 'POST' else 200)

    def upload(self, db: Database[Any], body: dict[str, Any], user: dict[str, Any]) -> Response:
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
        valid = (
            (mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n'))
            or (mime == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff'))
            or (mime == 'image/webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')
        )
        if not valid:
            raise ApiError(400, 'Isi berkas tidak cocok dengan format gambarnya.')

        user_uploads = db['uploads'].find({'user_id': user['id']}, {'content': 1})
        used = sum(len(doc.get('content', b'')) for doc in user_uploads)
        if used + len(raw) > 100 * MAX_IMAGE_BYTES:
            raise ApiError(413, 'Kuota unggahan akun tercapai (200 MB).')

        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[mime]
        path = f'/uploads/{uuid.uuid4().hex}.{extension}'
        db['uploads'].insert_one(
            {
                'path': path,
                'user_id': user['id'],
                'kind': kind,
                'mime_type': mime,
                'content': Binary(raw),
                'created_at': now(),
            }
        )
        if kind == 'avatar':
            old = user.get('avatar_url')
            db['users'].update_one({'id': user['id']}, {'$set': {'avatar_url': path}})
            if old:
                db['uploads'].delete_many({'path': old, 'user_id': user['id'], 'kind': 'avatar'})
        return Response({'url': path}, 201)