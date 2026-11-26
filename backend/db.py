from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_NAME = 'PSOFP-db123'

_CLIENTS: dict[str, MongoClient[Any]] = {}


def load_env(env_path: Path | None = None) -> None:
    """Load key=value pairs from .env into os.environ if not already set."""
    target = env_path or (ROOT / '.env')
    if not target.is_file():
        return
    for raw_line in target.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _resolve_uri(database: str | Path = '') -> str:
    raw = str(database).strip() if database else ''
    if raw and not raw.startswith(('mongodb://', 'mongodb+srv://')):
        raw = ''
    uri = (
        raw
        or os.environ.get('MONGODB_URI', '').strip()
        or (
            os.environ.get('DATABASE_URL', '').strip()
            if os.environ.get('DATABASE_URL', '').strip().startswith(('mongodb://', 'mongodb+srv://'))
            else ''
        )
    )
    if not uri:
        raise RuntimeError(
            'MONGODB_URI belum diatur. Isi MONGODB_URI di file .env (contoh: mongodb+srv://... atau mongodb://localhost:27017).'
        )
    return uri


def get_client(database: str | Path = '') -> MongoClient[Any]:
    """Return a cached MongoClient instance (manages connection pool internally)."""
    uri = _resolve_uri(database)
    if uri not in _CLIENTS:
        _CLIENTS[uri] = MongoClient(
            uri,
            maxPoolSize=10,
            minPoolSize=1,
            maxIdleTimeMS=60_000,
            serverSelectionTimeoutMS=5_000,
        )
    return _CLIENTS[uri]


def connect(database: str | Path = '', db_name: str | None = None) -> Database[Any]:
    """Return the MongoDB Database handle for PSOFP-db123 (or override via env/arg)."""
    client = get_client(database)
    target_db = (
        db_name
        or os.environ.get('MONGODB_DB_NAME', '').strip()
        or DEFAULT_DB_NAME
    )
    return client[target_db]


def now() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return f'pbkdf2_sha256${iterations}${salt}${digest.hex()}'


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash."""
    try:
        algorithm, iter_str, salt, expected_hex = stored_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            int(iter_str),
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def initialize(database: str | Path = '', db_name: str | None = None) -> None:
    """Ensure required MongoDB collections and indexes exist in PSOFP-db123."""
    db = connect(database, db_name=db_name)
    try:
        db['metadata'].create_index([('key', ASCENDING)], unique=True)
        db['toppings'].create_index([('id', ASCENDING)], unique=True)
        db['toppings'].create_index([('name', ASCENDING), ('kind', ASCENDING)])
        db['menus'].create_index([('id', ASCENDING)], unique=True)
        db['menus'].create_index([('category', ASCENDING), ('active', ASCENDING)])
        db['users'].create_index([('id', ASCENDING)], unique=True)
        db['users'].create_index([('email', ASCENDING)], unique=True)
        db['users'].create_index([('username', ASCENDING)], unique=True)
        db['sessions'].create_index([('token_hash', ASCENDING)], unique=True)
        db['carts'].create_index([('id', ASCENDING)], unique=True)
        db['orders'].create_index(
            [('user_id', ASCENDING), ('idempotency_key', ASCENDING)],
            unique=True,
        )
    except PyMongoError as exc:
        raise RuntimeError(
            f'Gagal terhubung atau menginisialisasi MongoDB ({exc}). '
            'Pastikan service MongoDB lokal sudah berjalan atau MONGODB_URI di .env mengarah ke MongoDB Atlas yang aktif.'
        ) from exc


def seed_demo(database: str | Path = '', db_name: str | None = None) -> None:
    """Insert initial demo catalog (menus, toppings, and metadata flag) if not already seeded."""
    db = connect(database, db_name=db_name)
    try:
        already_seeded = db['metadata'].find_one({'key': 'demo_seed'})
        if already_seeded:
            return

        # Required base toppings (1 size + 1 temperature required by validate_toppings)
        toppings = [
            {'id': 1, 'name': 'Regular', 'price': 0, 'active': 1, 'kind': 'size'},
            {'id': 2, 'name': 'Large', 'price': 5000, 'active': 1, 'kind': 'size'},
            {'id': 3, 'name': 'Hot', 'price': 0, 'active': 1, 'kind': 'temperature'},
            {'id': 4, 'name': 'Iced', 'price': 2000, 'active': 1, 'kind': 'temperature'},
            {'id': 5, 'name': 'Extra Espresso Shot', 'price': 6000, 'active': 1, 'kind': 'extra'},
            {'id': 6, 'name': 'Caramel Drizzle', 'price': 4000, 'active': 1, 'kind': 'extra'},
        ]

        menus = [
            {
                'id': 1,
                'name': 'Americano',
                'price': 18000,
                'active': 1,
                'description': 'Espresso klasik dengan air panas atau dingin.',
                'category': 'COFFEE',
                'img': '/images/americano.png',
            },
            {
                'id': 2,
                'name': 'Caffe Latte',
                'price': 24000,
                'active': 1,
                'description': 'Espresso lembut dengan susu steamed.',
                'category': 'COFFEE',
                'img': '/images/caffelatte.png',
            },
            {
                'id': 3,
                'name': 'Cappuccino',
                'price': 24000,
                'active': 1,
                'description': 'Espresso dengan busa susu tebal.',
                'category': 'COFFEE',
                'img': '/images/menu_cappucino.png',
            },
            {
                'id': 4,
                'name': 'Peach Tea',
                'price': 20000,
                'active': 1,
                'description': 'Teh segar dengan aroma buah persik.',
                'category': 'NON-COFFEE',
                'img': '/images/peachtea.png',
            },
            {
                'id': 5,
                'name': 'Apple Tea',
                'price': 20000,
                'active': 1,
                'description': 'Teh manis segar rasa apel.',
                'category': 'NON-COFFEE',
                'img': '/images/appletea.png',
            },
            {
                'id': 6,
                'name': 'Classic Pancake',
                'price': 28000,
                'active': 1,
                'description': 'Pancake hangat dengan sirup maple.',
                'category': 'BREAKFAST',
                'img': '/images/pancake.png',
            },
            {
                'id': 7,
                'name': 'Japanese Curry',
                'price': 38000,
                'active': 1,
                'description': 'Nasi kari Jepang gurih dan hangat.',
                'category': 'MEAL',
                'img': '/images/curry.png',
            },
        ]

        db['toppings'].insert_many(toppings)
        db['menus'].insert_many(menus)
        db['counters'].update_one({'_id': 'toppings'}, {'$max': {'seq': len(toppings)}}, upsert=True)
        db['counters'].update_one({'_id': 'menus'}, {'$max': {'seq': len(menus)}}, upsert=True)
        db['metadata'].update_one(
            {'key': 'demo_seed'},
            {'$setOnInsert': {'key': 'demo_seed', 'value': '1'}},
            upsert=True,
        )
    except PyMongoError as exc:
        raise RuntimeError(f'Gagal mengisi data demo ke MongoDB: {exc}') from exc