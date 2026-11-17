from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'

_POOLS: dict[str, ConnectionPool] = {}


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


def _get_pool(database: str | Path) -> ConnectionPool:
    conninfo = str(database) if database else os.environ.get('DATABASE_URL', '')
    if not conninfo:
        raise RuntimeError('DATABASE_URL is not configured.')
    if conninfo not in _POOLS:
        _POOLS[conninfo] = ConnectionPool(
            conninfo=conninfo,
            kwargs={'row_factory': dict_row, 'autocommit': False},
            min_size=1,
            max_size=10,
            max_lifetime=300,
            max_idle=60,
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _POOLS[conninfo]


def connect(database: str | Path = '') -> psycopg.Connection:
    """Return a pooled PostgreSQL connection with dict_row enabled."""
    return _get_pool(database).getconn()


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


def initialize(database: str | Path = '') -> None:
    """Run all SQL migration files in backend/migrations/ in sorted order."""
    db = connect(database)
    try:
        db.execute('BEGIN')
        for sql_file in sorted(MIGRATIONS_DIR.glob('*.sql')):
            sql = sql_file.read_text(encoding='utf-8').strip()
            if sql:
                db.execute(sql)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed_demo(database: str | Path = '') -> None:
    """Insert initial demo catalog (menus, toppings, and metadata flag) if not already seeded."""
    db = connect(database)
    try:
        db.execute('BEGIN')
        already_seeded = db.execute("SELECT 1 FROM metadata WHERE key = 'demo_seed'").fetchone()
        if already_seeded:
            db.commit()
            return

        # Required base toppings (1 size + 1 temperature required by validate_toppings)
        toppings = [
            ('Regular', 0, 1, 'size'),
            ('Large', 5000, 1, 'size'),
            ('Hot', 0, 1, 'temperature'),
            ('Iced', 2000, 1, 'temperature'),
            ('Extra Espresso Shot', 6000, 1, 'extra'),
            ('Caramel Drizzle', 4000, 1, 'extra'),
        ]
        for name, price, active, kind in toppings:
            db.execute(
                'INSERT INTO toppings (name, price, active, kind) VALUES (%s, %s, %s, %s)',
                (name, price, active, kind),
            )

        menus = [
            ('Americano', 18000, 1, 'Espresso klasik dengan air panas atau dingin.', 'COFFEE', '/images/americano.png'),
            ('Caffe Latte', 24000, 1, 'Espresso lembut dengan susu steamed.', 'COFFEE', '/images/caffelatte.png'),
            ('Cappuccino', 24000, 1, 'Espresso dengan busa susu tebal.', 'COFFEE', '/images/menu_cappucino.png'),
            ('Peach Tea', 20000, 1, 'Teh segar dengan aroma buah persik.', 'NON-COFFEE', '/images/peachtea.png'),
            ('Apple Tea', 20000, 1, 'Teh manis segar rasa apel.', 'NON-COFFEE', '/images/appletea.png'),
            ('Classic Pancake', 28000, 1, 'Pancake hangat dengan sirup maple.', 'BREAKFAST', '/images/pancake.png'),
            ('Japanese Curry', 38000, 1, 'Nasi kari Jepang gurih dan hangat.', 'MEAL', '/images/curry.png'),
        ]
        for name, price, active, desc, category, img in menus:
            db.execute(
                'INSERT INTO menus (name, price, active, description, category, img) VALUES (%s, %s, %s, %s, %s, %s)',
                (name, price, active, desc, category, img),
            )

        db.execute("INSERT INTO metadata (key, value) VALUES ('demo_seed', '1') ON CONFLICT (key) DO NOTHING")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
