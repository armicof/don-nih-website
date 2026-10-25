"""Database setup and local admin provisioning. Run from the project root."""

import argparse
import getpass
import os
import sqlite3
import uuid

from backend.app import ApiError, text
from backend.db import (
    ROOT,
    connect,
    hash_password,
    initialize,
    load_env,
    now,
    seed_demo,
)


def main():
    load_env()
    parser = argparse.ArgumentParser(description='Setup lokal Kedai Don.Nih!')
    parser.add_argument('--database', default=os.environ.get('DATABASE_PATH', str(ROOT / 'data' / 'donnih.sqlite3')))
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Terapkan migrasi database')
    init.add_argument('--demo', action='store_true', help='Tambahkan katalog contoh, bukan data produksi')
    admin = commands.add_parser('create-admin', help='Buat akun admin; password diminta secara tersembunyi')
    admin.add_argument('--email', required=True)
    admin.add_argument('--username', required=True)
    admin.add_argument('--name', required=True)
    promote = commands.add_parser('promote-admin', help='Jadikan akun lokal yang sudah terdaftar sebagai admin')
    promote.add_argument('--email', required=True)
    args = parser.parse_args()
    initialize(args.database)
    if args.command == 'init':
        if args.demo:
            seed_demo(args.database)
        print('Database siap.' + (' Katalog DEMO ditambahkan (harga/deskripsi rekaan).' if args.demo else ' Katalog tidak diisi otomatis.'))
        return
    db = connect(args.database)
    try:
        db.execute('BEGIN IMMEDIATE')
        email = text(args.email, 'Email', 3, 254).lower()
        if args.command == 'promote-admin':
            updated = db.execute("UPDATE users SET role='admin' WHERE email=?", (email,))
            if not updated.rowcount:
                raise ValueError('Akun belum ada. Daftar lewat web terlebih dahulu.')
        else:
            import re
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                raise ValueError('Format email tidak valid.')
            username = text(args.username, 'Username', 3, 30)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', username):
                raise ValueError('Format username tidak valid.')
            fullname = text(args.name, 'Nama lengkap', 2, 100)
            password = getpass.getpass('Password admin (8–128 karakter): ')
            if not 8 <= len(password) <= 128:
                raise ValueError('Password harus 8–128 karakter.')
            if password != getpass.getpass('Ulangi password: '):
                raise ValueError('Konfirmasi password tidak sama.')
            db.execute("INSERT INTO users (id,email,username,fullname,password_hash,role,created_at) VALUES (?,?,?,?,?,'admin',?)",
                       (str(uuid.uuid4()), email, username, fullname, hash_password(password), now()))
        db.commit()
        print('Admin lokal siap. Masuk kembali melalui web.')
    except (ValueError, ApiError, sqlite3.IntegrityError) as exc:
        db.rollback()
        parser.exit(1, f'Gagal: {exc}\n')
    finally:
        db.close()


if __name__ == '__main__':
    main()
