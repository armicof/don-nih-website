"""SQLite persistence. No external service or account is created automatically."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def now() -> str:
    return datetime.now(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def load_env() -> None:
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    _, salt, expected = encoded.split('$')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(expected, actual)


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db


def initialize(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        for migration in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
            if not db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (migration.name,)).fetchone():
                try:
                    db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text(encoding='utf-8'))
                    db.execute('INSERT INTO schema_migrations VALUES (?,?)', (migration.name, now()))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
    finally:
        db.close()


def seed_demo(path: str | Path) -> None:
    """Explicit, idempotent sample catalog; prices/descriptions are not production data."""
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM metadata WHERE key='demo_seed'").fetchone():
            db.rollback()
            return
        if db.execute('SELECT 1 FROM menus LIMIT 1').fetchone():
            raise ValueError('Seed demo hanya boleh dijalankan pada katalog kosong.')
        products = [
            ('Cappuccino', 'Espresso, susu lembut, dan lapisan foam untuk teman rehatmu.', 'COFFEE', 28000, 'menu_cappucino.png'),
            ('Caffè Latte', 'Perpaduan espresso dan susu yang creamy, sederhana dan hangat.', 'COFFEE', 27000, 'caffelatte.png'),
            ('Americano', 'Espresso dengan air, karakter kopi yang bersih dan tegas.', 'COFFEE', 22000, 'americano.png'),
            ('Espresso', 'Satu momen kecil dengan rasa kopi yang intens.', 'COFFEE', 18000, 'espresso.png'),
            ('Apple Tea', 'Teh dengan rasa apel yang ringan dan menyegarkan.', 'NON-COFFEE', 23000, 'appletea.png'),
            ('Peach Tea', 'Teh dengan sentuhan buah persik untuk hari yang manis.', 'NON-COFFEE', 23000, 'peachtea.png'),
            ('Pancake', 'Pancake lembut, teman sempurna untuk secangkir kopi.', 'DESSERT', 30000, 'pancake.png'),
            ('Chicken Curry', 'Sajian kari hangat dan nasi untuk mengisi harimu.', 'MEAL', 38000, 'curry.png'),
        ]
        db.executemany('INSERT INTO menus (name,description,category,price,img) VALUES (?,?,?,?,?)',
                       [(name, desc, category, price, '/images/' + image) for name, desc, category, price, image in products])
        db.execute('UPDATE toppings SET price=5000 WHERE id=9')
        db.executemany("INSERT INTO toppings (name,price,kind) VALUES (?,?,'extra')",
                       [('Extra Espresso', 5000), ('Caramel', 4000), ('Vanilla', 4000), ('Whipped Cream', 5000)])
        db.execute("INSERT INTO metadata VALUES ('demo_seed',?)", (now(),))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
