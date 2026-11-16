"""Database setup and admin provisioning. Run from the project root."""

import argparse
import getpass
import os
import re
import uuid

from psycopg import errors as pg_errors

from backend.app import ApiError, text
from backend.db import (
    connect,
    hash_password,
    initialize,
    load_env,
    now,
    seed_demo,
)


def main():
    load_env()
    parser = argparse.ArgumentParser(description='Setup Kedai Don.Nih!')
    parser.add_argument(
        '--database',
        default=os.environ.get('DATABASE_URL', ''),
        help='PostgreSQL connection URI (default: DATABASE_URL)',
    )
    commands = parser.add_subparsers(dest='command', required=True)

    init = commands.add_parser('init', help='Terapkan migrasi database')
    init.add_argument('--demo', action='store_true', help='Tambahkan katalog contoh, bukan data produksi')

    admin = commands.add_parser('create-admin', help='Buat akun admin; password diminta secara tersembunyi')
    admin.add_argument('--email', required=True)
    admin.add_argument('--username', required=True)
    admin.add_argument('--name', required=True)

    promote = commands.add_parser('promote-admin', help='Jadikan akun yang sudah terdaftar sebagai admin')
    promote.add_argument('--email', required=True)

    args = parser.parse_args()

    if not args.database:
        parser.exit(1, 'Gagal: DATABASE_URL belum diatur di environment atau .env.\n')

    initialize(args.database)
    if args.command == 'init':
        if args.demo:
            seed_demo(args.database)
        print('Database siap.' + (' Katalog DEMO ditambahkan (harga/deskripsi rekaan).' if args.demo else ' Katalog tidak diisi otomatis.'))
        return

    db = connect(args.database)
    try:
        db.execute('BEGIN')
        email = text(args.email, 'Email', 3, 254).lower()
        if args.command == 'promote-admin':
            updated = db.execute("UPDATE users SET role='admin' WHERE email=%s", (email,))
            if not updated.rowcount:
                raise ValueError('Akun belum ada. Daftar lewat web terlebih dahulu.')
        else:
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
            db.execute(
                "INSERT INTO users (id,email,username,fullname,password_hash,role,created_at) VALUES (%s,%s,%s,%s,%s,'admin',%s)",
                (str(uuid.uuid4()), email, username, fullname, hash_password(password), now()),
            )
        db.commit()
        print('Admin siap. Masuk kembali melalui web.')
    except (ValueError, ApiError, pg_errors.IntegrityError) as exc:
        db.rollback()
        parser.exit(1, f'Gagal: {exc}\n')
    finally:
        db.close()


if __name__ == '__main__':
    main()  