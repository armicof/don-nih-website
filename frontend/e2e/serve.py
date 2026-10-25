"""Test-owned HTTP host. Never opens the application's default database."""

from __future__ import annotations

import argparse
import shutil
import sys
import threading
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.server import create_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    database = Path(args.database).resolve()
    temporary_root = Path(__file__).resolve().parent / '.tmp'
    if (database.parent.parent != temporary_root or
            not database.parent.name.startswith('run-') or
            database.name != 'donnih.sqlite3' or not database.is_file()):
        parser.error('E2E requires an explicitly seeded database in frontend/e2e/.tmp/run-*/.')

    # The mutable allowlist gets the actual OS-assigned port before serving.
    origins = {'http://127.0.0.1:0'}
    server = create_server(database, host='127.0.0.1', port=0,
                           allowed_origins=origins, secure_cookie=False, session_hours=1)
    origin = f'http://127.0.0.1:{server.server_address[1]}'
    origins.clear()
    origins.add(origin)

    def stop_on_parent_exit():
        # EOF also arrives if the Node runner crashes: no orphan HTTP server.
        sys.stdin.buffer.read()
        server.shutdown()

    threading.Thread(target=stop_on_parent_exit, daemon=True).start()
    print(f'E2E_READY {origin}', flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        shutil.rmtree(database.parent, ignore_errors=True)


if __name__ == '__main__':
    main()
