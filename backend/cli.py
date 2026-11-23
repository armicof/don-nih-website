"""Database setup and admin provisioning. Run from the project root."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import uuid

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from backend.app import ApiError, text
from backend.db import (
    DEFAULT_DB_NAME,
    connect,
    hash_password,
    initialize,
    load_env,
    now,
    seed_demo,
)


def main() -> None:
    load_env()
    default_uri = os.environ.get('MONGODB_URI') or os.environ.get('DATABASE_URL') or ''

    parser = argparse.ArgumentParser(description='Setup Kedai Don.Nih!')
    parser.add_argument(
        '--database',
        default=default_uri,
        help='MongoDB connection URI (default: MONGODB_URI / DATABASE_URL)',
    )
    parser.add_argument(
        '--db-name',
        default=os.environ.get('MONGODB_DB_NAME', DEFAULT_DB_NAME),
        help=f'MongoDB database name (default: {DEFAULT_DB_NAME})',
    )
    commands = parser.add_subparsers(dest='command', required=True)

    init = commands.add_parser('init', help='Terapkan inisialisasi database')
    init.add_argument('--demo', action='store_true', help='Tambahkan katalog contoh, bukan data produksi')

    admin = commands.add_parser('create-admin', help='Buat akun admin; password diminta secara tersembunyi')
    admin.add_argument('--email', required=True)
    admin.add_argument('--username', required=True)
    admin.add_argument('--name', required=True)

    promote = commands.add_parser('promote-admin', help='Jadikan akun yang sudah terdaftar sebagai admin')
    promote.add_argument('--email', required=True)

    args = parser.parse_args()

    if not args.database:
        parser.exit(1, 'Gagal: MONGODB_URI belum diatur di environment atau .env.\n')

    try:
        initialize(args.database, db_name=args.db_name)
        if args.command == 'init':
            if args.demo:
                seed_demo(args.database, db_name=args.db_name)
            print(
                f'Database ({args.db_name}) siap.'
                + (' Katalog DEMO ditambahkan (harga/deskripsi rekaan).' if args.demo else ' Katalog tidak diisi otomatis.')
            )
            return

        db = connect(args.database, db_name=args.db_name)
        users = db['users']
        users.create_index([('email', ASCENDING)], unique=True)
        users.create_index([('username', ASCENDING)], unique=True)

        email = text(args.email, 'Email', 3, 254).lower()
        if args.command == 'promote-admin':
            result = users.update_one({'email': email}, {'$set': {'role': 'admin'}})
            if result.matched_count == 0:
                raise ValueError('Akun belum ada. Daftar lewat web terlebih dahulu.')
        else:
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                raise ValueError('Format email tidak valid.')
            username = text(args.username, 'Username', 3, 30)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', username):
                raise ValueError('Format username tidak valid.')
            fullname = text(args.name, 'Nama lengkap', 2, 100)
            password = getpass.getpass('Password admin (8-128 karakter): ')
            if not 8 <= len(password) <= 128:
                raise ValueError('Password harus 8-128 karakter.')
            if password != getpass.getpass('Ulangi password: '):
                raise ValueError('Konfirmasi password tidak sama.')

            users.insert_one(
                {
                    'id': str(uuid.uuid4()),
                    'email': email,
                    'username': username,
                    'fullname': fullname,
                    'password_hash': hash_password(password),
                    'role': 'admin',
                    'created_at': now(),
                }
            )

        print('Admin siap. Masuk kembali melalui web.')
    except DuplicateKeyError as exc:
        parser.exit(1, f'Gagal: Email atau username sudah terdaftar ({exc}).\n')
    except (ValueError, ApiError, PyMongoError) as exc:
        parser.exit(1, f'Gagal: {exc}\n')


if __name__ == '__main__':
    main()