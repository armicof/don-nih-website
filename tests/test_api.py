"""Stdlib integration tests against MongoDB (PSOFP-db123 by default).

Run from the project root: python -m unittest discover -s tests -v
Admin fixtures are provisioned out of band, like the local CLI, never via the API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPConnection, HTTPMessage
from http.cookies import SimpleCookie
from itertools import pairwise
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

from backend.app import MAX_IMAGE_BYTES, Application
from backend.db import connect, initialize, seed_demo, verify_password
from backend.server import MAX_BODY, create_server

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'Integration-password-42'
ORIGIN = 'http://integration.test'
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8Dw'
    'HwAFAAH/iZk9HQAAAABJRU5ErkJggg=='
)


def _mongo_uri() -> str:
    uri = (os.environ.get('MONGODB_URI') or os.environ.get('DATABASE_URL') or '').strip()
    if not uri:
        raise unittest.SkipTest('MONGODB_URI is not configured for MongoDB integration tests.')
    return uri


def data_url(content: bytes = PNG, mime: str = 'image/png') -> str:
    return 'data:' + mime + ';base64,' + base64.b64encode(content).decode('ascii')


@contextmanager
def running_server(database: str, db_name: str, **options: Any):
    server = create_server(
        database,
        host='127.0.0.1',
        port=0,
        allowed_origins={ORIGIN},
        db_name=db_name,
        **options,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={'poll_interval': 0.01},
        daemon=True,
    )
    try:
        thread.start()
        yield server
    finally:
        try:
            if thread.is_alive():
                server.shutdown()
        finally:
            server.server_close()
            if thread.ident is not None:
                thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError('Integration HTTP server did not stop')


@dataclass
class Reply:
    status: int
    # Decoded JSON has endpoint-specific shapes checked by the tests; images are bytes.
    data: Any
    headers: HTTPMessage


class Client:
    """One connection per call; cookie state is local to this test client."""

    def __init__(self, server: Any, token: str = ''):
        self.address = server.server_address
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        raw: bytes | None = None,
        headers: dict[str, str | None] | None = None,
    ) -> Reply:
        outgoing: dict[str, str] = {}
        payload: bytes | None = None
        if method not in ('GET', 'HEAD'):
            outgoing.update(
                {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'donnih-web',
                    'Origin': ORIGIN,
                }
            )
            payload = json.dumps({} if body is None else body).encode('utf-8')
        if raw is not None:
            payload = raw
        if self.token:
            outgoing['Cookie'] = 'donnih_session=' + self.token
        for key, value in (headers or {}).items():
            if value is None:
                outgoing.pop(key, None)
            else:
                outgoing[key] = value
        connection = HTTPConnection(*self.address, timeout=10)
        try:
            connection.request(method, path, body=payload, headers=outgoing)
            response = connection.getresponse()
            content = response.read()
            if response.getheader('Set-Cookie') is not None:
                cookie = SimpleCookie(response.getheader('Set-Cookie'))
                self.token = cookie['donnih_session'].value
            parsed = (
                json.loads(content)
                if content and response.getheader('Content-Type', '').startswith('application/json')
                else content
            )
            return Reply(response.status, parsed, response.headers)
        finally:
            connection.close()


class _MongoTestCase(unittest.TestCase):
    def prepare_isolated_db(self, prefix: str = 'donnih_test') -> tuple[str, str]:
        uri = _mongo_uri()
        db_name = f'{prefix}_{uuid.uuid4().hex[:10]}'
        client_db = connect(uri, db_name=db_name)
        client_db.client.drop_database(db_name)
        self.addCleanup(client_db.client.drop_database, db_name)
        return uri, db_name

    def db_handle(self) -> Any:
        return connect(self.database, db_name=self.db_name)

    def docs(self, collection: str, query: dict[str, Any] | None = None, sort_field: str | None = None) -> list[dict[str, Any]]:
        cursor = self.db_handle()[collection].find(query or {})
        if sort_field:
            cursor = cursor.sort(sort_field, 1)
        return [{k: v for k, v in doc.items() if k != '_id'} for doc in cursor]


class APIIntegrationTests(_MongoTestCase):
    def setUp(self):
        self.database, self.db_name = self.prepare_isolated_db('donnih_api')
        initialize(self.database, db_name=self.db_name)
        seed_demo(self.database, db_name=self.db_name)
        self.server = self.enterContext(running_server(self.database, self.db_name))
        self.client = Client(self.server)
        self.menus = self.expect(self.client, 'GET', '/api/menus')
        self.toppings = self.expect(self.client, 'GET', '/api/toppings')
        self.menu = self.menus[0]
        self.sizes = [t for t in self.toppings if t['kind'] == 'size']
        self.temperatures = [t for t in self.toppings if t['kind'] == 'temperature']
        self.extra = next(t for t in self.toppings if t['kind'] == 'extra')
        self.selection = [self.sizes[0]['id'], self.temperatures[0]['id']]

    def app_instance(self) -> Application:
        return Application(self.database, db_name=self.db_name)

    def expect(self, client: Client, method: str, path: str, body: Any = None, status: int = 200, **kwargs: Any) -> Any:
        result = client.request(method, path, body, **kwargs)
        self.assertEqual(
            result.status,
            status,
            f'{method} {path}: expected {status}, got {result.status}: {result.data!r}',
        )
        if status >= 400:
            self.assertIsInstance(result.data, dict)
            self.assertIsInstance(result.data.get('error'), str)
            self.assertTrue(result.data['error'])
        return result.data

    def signup(self, name: str = 'customer', *, admin: bool = False, **overrides: Any) -> tuple[Client, dict[str, Any]]:
        client = Client(self.server)
        body = {
            'email': name + '@example.test',
            'username': name,
            'fullname': 'Test ' + name,
            'password': PASSWORD,
        }
        body.update(overrides)
        user = self.expect(client, 'POST', '/api/auth/register', body, 201)['user']
        if admin:
            self.db_handle()['users'].update_one({'id': user['id']}, {'$set': {'role': 'admin'}})
            user = self.expect(client, 'GET', '/api/auth/me')['user']
            self.assertEqual(user['role'], 'admin')
        return client, user

    def add_cart(self, client: Client, *, menu: dict[str, Any] | None = None, topping_ids: list[int] | None = None, quantity: int = 1, **fields: Any) -> Any:
        body = {
            'menu_id': (menu or self.menu)['id'],
            'quantity': quantity,
            'topping_ids': self.selection if topping_ids is None else topping_ids,
        }
        body.update(fields)
        return self.expect(client, 'POST', '/api/cart', body, 201)

    def checkout(self, client: Client, key: str = 'checkout-integration-0001', **fields: Any) -> Any:
        return self.expect(client, 'POST', '/api/orders', {'idempotency_key': key, **fields}, 201)

    def test_numeric_url_ids_outside_integer_range_are_rejected(self):
        client, _ = self.signup()
        admin, _ = self.signup('administrator', admin=True)
        cart = self.add_cart(client)
        favorite_path = f'/api/favorites/{self.menu["id"]}'
        self.expect(client, 'PUT', favorite_path)
        routes = [
            (client, 'PUT', '/api/favorites/{id}'),
            (client, 'DELETE', '/api/favorites/{id}'),
            (client, 'PATCH', '/api/cart/{id}'),
            (client, 'DELETE', '/api/cart/{id}'),
            (client, 'GET', '/api/orders/{id}'),
            (admin, 'PATCH', '/api/admin/orders/{id}/status'),
        ]
        for catalog in ('menus', 'toppings'):
            for method in ('PATCH', 'DELETE'):
                routes.append((admin, method, f'/api/admin/{catalog}/{{id}}'))
        for record_id in ('0', str(2**63), '9' * 100):
            for actor, method, template in routes:
                path = template.format(id=record_id)
                with self.subTest(method=method, path=path):
                    self.expect(actor, method, path, {'quantity': 1, 'price': 1}, 400)
        self.assertEqual(self.expect(client, 'GET', '/api/cart'), cart)
        self.assertEqual(self.expect(client, 'GET', '/api/favorites'), [self.menu['id']])
        self.assertEqual(self.expect(client, 'GET', '/api/orders'), [])
        self.assertEqual(self.expect(self.client, 'GET', '/api/menus'), self.menus)
        self.assertEqual(self.expect(self.client, 'GET', '/api/toppings'), self.toppings)
        self.expect(client, 'GET', f'/api/orders/{2**63 - 1}', status=404)

    def test_signup_hashes_password_and_session_and_logout_revokes_cookie(self):
        client, user = self.signup()
        self.assertEqual(user['role'], 'user')
        self.assertNotIn('password', user)
        self.assertNotIn('password_hash', user)
        stored = self.docs('users', {'id': user['id']})[0]
        self.assertTrue(stored['password_hash'].startswith('pbkdf2_sha256$'))
        self.assertNotIn(PASSWORD, stored['password_hash'])
        self.assertTrue(verify_password(PASSWORD, stored['password_hash']))
        self.assertFalse(verify_password('wrong-password', stored['password_hash']))
        token = client.token
        sessions = self.docs('sessions')
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session['token_hash'], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(session['token_hash'], token)
        self.assertEqual(session['user_id'], user['id'])
        self.assertGreater(session['expires_at'], int(time.time()))
        self.assertEqual(self.expect(client, 'GET', '/api/auth/me')['user'], user)
        result = client.request('POST', '/api/auth/logout')
        self.assertEqual(result.status, 200)
        cookie = SimpleCookie(result.headers['Set-Cookie'])['donnih_session']
        self.assertEqual(cookie.value, '')
        self.assertEqual(cookie['max-age'], '0')
        self.assertTrue(cookie['httponly'])
        self.assertEqual(client.token, '')
        self.assertEqual(self.docs('sessions'), [])
        replay = Client(self.server, token)
        self.assertIsNone(self.expect(replay, 'GET', '/api/auth/me')['user'])
        self.expect(replay, 'GET', '/api/cart', status=401)

    def test_login_cookie_flags_rotation_and_case_insensitive_email(self):
        client, user = self.signup()
        old_token = client.token
        before = int(time.time())
        result = client.request(
            'POST',
            '/api/auth/login',
            {'email': 'CUSTOMER@EXAMPLE.TEST', 'password': PASSWORD},
        )
        self.assertEqual(result.status, 200)
        self.assertEqual(result.data['user'], user)
        cookie = SimpleCookie(result.headers['Set-Cookie'])['donnih_session']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(cookie['path'], '/')
        self.assertEqual(cookie['max-age'], str(168 * 3600))
        self.assertFalse(cookie['secure'])
        self.assertNotEqual(client.token, old_token)
        self.expect(Client(self.server, old_token), 'GET', '/api/cart', status=401)
        sessions = self.docs('sessions')
        self.assertEqual(len(sessions), 1)
        self.assertGreaterEqual(sessions[0]['expires_at'], before + 168 * 3600)
        self.assertLessEqual(sessions[0]['expires_at'], int(time.time()) + 168 * 3600)

    def test_secure_cookie_and_custom_session_lifetime(self):
        self.signup()
        with running_server(self.database, self.db_name, secure_cookie=True, session_hours=2) as server:
            result = Client(server).request(
                'POST',
                '/api/auth/login',
                {'email': 'customer@example.test', 'password': PASSWORD},
            )
        self.assertEqual(result.status, 200)
        cookie = SimpleCookie(result.headers['Set-Cookie'])['donnih_session']
        self.assertTrue(cookie['secure'])
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['max-age'], '7200')
        token_hash = hashlib.sha256(cookie.value.encode()).hexdigest()
        expiry = self.docs('sessions', {'token_hash': token_hash})[0]['expires_at']
        self.assertAlmostEqual(expiry - int(time.time()), 7200, delta=5)

    def test_expired_and_unknown_sessions_are_unauthenticated(self):
        client, _ = self.signup()
        self.db_handle()['sessions'].update_many({}, {'$set': {'expires_at': int(time.time()) - 1}})
        self.assertIsNone(self.expect(client, 'GET', '/api/auth/me')['user'])
        self.expect(client, 'GET', '/api/cart', status=401)
        self.expect(Client(self.server, 'not-a-real-session'), 'GET', '/api/orders', status=401)
        self.expect(
            client,
            'POST',
            '/api/auth/login',
            {'email': 'customer@example.test', 'password': PASSWORD},
        )
        self.assertEqual(len(self.docs('sessions')), 1)
        self.assertIsNotNone(self.expect(client, 'GET', '/api/auth/me')['user'])

    def test_registration_validation_and_unique_email_username(self):
        valid = {
            'email': 'new@example.test',
            'username': 'newuser',
            'fullname': 'New User',
            'password': PASSWORD,
        }
        for changes in (
            {'email': 'not-email'},
            {'username': 'bad name'},
            {'fullname': ''},
            {'password': 'short'},
            {'phone_number': 'abcdef'},
        ):
            with self.subTest(changes=changes):
                self.expect(self.client, 'POST', '/api/auth/register', {**valid, **changes}, 400)
        self.assertEqual(self.docs('users'), [])
        first, _ = self.signup()
        second, _ = self.signup('second')
        users = self.docs('users')
        self.assertEqual(len(users), 2)
        self.assertNotEqual(users[0]['password_hash'], users[1]['password_hash'])
        for changes in ({'email': 'CUSTOMER@EXAMPLE.TEST'}, {'username': 'CUSTOMER'}):
            with self.subTest(changes=changes):
                self.expect(self.client, 'POST', '/api/auth/register', {**valid, **changes}, 409)
        self.assertEqual(len(self.docs('users')), 2)
        self.assertTrue(first.token and second.token)

    def test_bad_login_does_not_create_or_replace_sessions(self):
        client, _ = self.signup()
        sessions = self.docs('sessions')
        errors = []
        for email, password in (('customer@example.test', 'wrong-password'), ('missing@example.test', PASSWORD)):
            errors.append(self.expect(client, 'POST', '/api/auth/login', {'email': email, 'password': password}, 401))
        self.assertEqual(errors[0], errors[1])
        self.assertEqual(self.docs('sessions'), sessions)
        self.assertIsNotNone(self.expect(client, 'GET', '/api/auth/me')['user'])

    def test_role_escalation_and_protected_admin_endpoints(self):
        client, user = self.signup(role='admin', id='forged-user-id')
        self.assertEqual(user['role'], 'user')
        self.assertNotEqual(user['id'], 'forged-user-id')
        for body in ({'role': 'admin'}, {'id': 'forged'}, {'email': 'other@example.test'}):
            with self.subTest(body=body):
                self.expect(client, 'PATCH', '/api/profile', body, 400)
        routes = [
            ('GET', '/api/admin/menus'),
            ('POST', '/api/admin/menus'),
            ('PATCH', f'/api/admin/menus/{self.menu["id"]}'),
            ('DELETE', f'/api/admin/menus/{self.menu["id"]}'),
            ('GET', '/api/admin/toppings'),
            ('POST', '/api/admin/toppings'),
            ('PATCH', f'/api/admin/toppings/{self.extra["id"]}'),
            ('DELETE', f'/api/admin/toppings/{self.extra["id"]}'),
            ('GET', '/api/admin/orders'),
            ('PATCH', '/api/admin/orders/1/status'),
        ]
        for method, path in routes:
            with self.subTest(method=method, path=path):
                self.expect(self.client, method, path, status=401)
                self.expect(client, method, path, status=403)
        for method, path in [
            ('GET', '/api/favorites'),
            ('PUT', '/api/favorites/1'),
            ('GET', '/api/cart'),
            ('POST', '/api/cart'),
            ('GET', '/api/orders'),
            ('POST', '/api/orders'),
            ('PATCH', '/api/profile'),
            ('POST', '/api/uploads'),
        ]:
            with self.subTest(anonymous=path):
                self.expect(self.client, method, path, status=401)
        self.assertEqual(self.expect(client, 'GET', '/api/auth/me')['user'], user)

    def test_favorites_are_idempotent_and_owned_by_session(self):
        alice, a = self.signup('alice')
        bob, b = self.signup('bobby')
        path = f'/api/favorites/{self.menu["id"]}'
        for _ in range(2):
            self.expect(alice, 'PUT', path, {'user_id': b['id']})
        self.assertEqual(self.expect(alice, 'GET', '/api/favorites'), [self.menu['id']])
        self.assertEqual(self.expect(bob, 'GET', '/api/favorites'), [])
        self.expect(bob, 'DELETE', path, {'user_id': a['id']})
        self.assertEqual(len(self.docs('favorites')), 1)
        self.expect(alice, 'PUT', '/api/favorites/999999', status=404)
        self.expect(alice, 'DELETE', path)
        self.expect(alice, 'DELETE', path)
        self.assertEqual(self.expect(alice, 'GET', '/api/favorites'), [])

    def test_cart_and_order_ownership_cannot_be_forged(self):
        alice, a = self.signup('alice')
        bob, b = self.signup('bobby')
        admin, _ = self.signup('administrator', admin=True)
        cart = self.add_cart(alice, user_id=b['id'])
        cid = cart['items'][0]['id']
        self.assertEqual(self.expect(bob, 'GET', '/api/cart'), {'items': [], 'total': 0})
        for method in ('PATCH', 'DELETE'):
            self.expect(bob, method, f'/api/cart/{cid}', {'quantity': 9, 'user_id': a['id']}, 404)
        self.assertEqual(self.expect(alice, 'GET', '/api/cart'), cart)
        order = self.checkout(alice, user_id=b['id'])
        self.assertEqual(order['user_id'], a['id'])
        self.assertEqual(self.expect(bob, 'GET', '/api/orders'), [])
        self.expect(bob, 'GET', f'/api/orders/{order["id"]}', status=404)
        self.assertEqual(self.expect(admin, 'GET', f'/api/orders/{order["id"]}'), order)
        self.assertEqual(self.expect(admin, 'GET', '/api/admin/orders'), [order])
        self.assertEqual(self.expect(admin, 'GET', '/api/orders'), [])
        self.assertEqual(self.expect(alice, 'GET', '/api/orders'), [order])
        self.assertEqual(self.expect(alice, 'GET', '/api/cart')['items'], [])

    def test_mutations_require_custom_header_allowed_origin_and_json(self):
        client, _ = self.signup()
        cases = [
            ({'X-Requested-With': None}, 403),
            ({'X-Requested-With': 'XMLHttpRequest'}, 403),
            ({'Origin': 'https://attacker.invalid'}, 403),
            ({'Origin': 'null'}, 403),
            ({'Sec-Fetch-Site': 'cross-site'}, 403),
            ({'Content-Type': 'text/plain'}, 415),
            ({'Content-Type': None}, 415),
        ]
        for headers, status in cases:
            with self.subTest(headers=headers):
                self.expect(client, 'PATCH', '/api/profile', {'fullname': 'Rejected Name'}, status, headers=headers)
        self.assertEqual(self.expect(client, 'GET', '/api/auth/me')['user']['fullname'], 'Test customer')
        updated = self.expect(
            client,
            'PATCH',
            '/api/profile',
            {'fullname': 'Allowed Name'},
            headers={'Content-Type': 'application/json; charset=utf-8'},
        )
        self.assertEqual(updated['user']['fullname'], 'Allowed Name')
        self.expect(client, 'PATCH', '/api/profile', {'phone_number': '+62 812-345678'}, headers={'Origin': None})

    def test_malformed_json_and_non_object_bodies_are_rejected(self):
        for raw in (b'{', b'{"a":}', b'\xff', b'[]', b'"string"', b'7', b'true'):
            with self.subTest(raw=raw):
                self.expect(self.client, 'POST', '/api/auth/logout', raw=raw, status=400)

    def test_json_null_is_rejected_as_non_object_body(self):
        self.expect(self.client, 'POST', '/api/auth/logout', raw=b'null', status=400)

    def test_http_body_length_and_transfer_encoding_guards(self):
        for headers, status in [
            ({'Content-Length': '-1'}, 413),
            ({'Content-Length': str(MAX_BODY + 1)}, 413),
            ({'Content-Length': 'invalid'}, 400),
            ({'Transfer-Encoding': 'chunked'}, 400),
        ]:
            with self.subTest(headers=headers):
                self.expect(self.client, 'POST', '/api/auth/logout', raw=b'{}', headers=headers, status=status)

    def test_health_and_response_security_headers(self):
        result = self.client.request('GET', '/api/health')
        self.assertEqual(result.status, 200)
        self.assertEqual(
            result.data,
            {
                'ok': True,
                'storage': 'mongodb',
                'database': self.db_name,
                'demo_data': True,
                'online_payment': False,
            },
        )
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertEqual(result.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(result.headers['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", result.headers['Content-Security-Policy'])
        self.assertIsNone(result.headers['Access-Control-Allow-Origin'])

    def test_server_computes_current_prices_ignoring_forged_fields(self):
        client, user = self.signup()
        admin, _ = self.signup('administrator', admin=True)
        ids = self.selection + [self.extra['id']]
        cart = self.add_cart(
            client,
            topping_ids=ids,
            quantity=2,
            price=1,
            unit_price=1,
            total=1,
            user_id='forged',
            toppings=[{'price': -99999}],
        )
        unit = self.menu['price'] + sum(t['price'] for t in self.toppings if t['id'] in ids)
        self.assertEqual(cart['items'][0]['unit_price'], unit)
        self.assertEqual(cart['total'], 2 * unit)
        self.expect(admin, 'PATCH', f'/api/admin/menus/{self.menu["id"]}', {'price': self.menu['price'] + 1000})
        self.expect(admin, 'PATCH', f'/api/admin/toppings/{self.extra["id"]}', {'price': self.extra['price'] + 500})
        order = self.checkout(
            client,
            user_id='forged',
            net_income=1,
            price=1,
            order_status='COMPLETED',
            items=[{'menu_id': 999999, 'price': 1}],
        )
        self.assertEqual(order['user_id'], user['id'])
        self.assertEqual(order['net_income'], 2 * (unit + 1500))
        self.assertEqual(order['items'][0]['price'], unit + 1500)
        self.assertEqual(order['items'][0]['menu_id'], self.menu['id'])
        self.assertEqual(order['order_status'], 'WAITING')
        self.assertNotIn('idempotency_key', order)

    def test_exactly_one_size_and_temperature_and_valid_unique_toppings(self):
        client, _ = self.signup()
        size, temperature = self.selection
        invalid = [
            None,
            {},
            '9,10',
            [],
            [size],
            [temperature],
            [size, self.sizes[1]['id'], temperature],
            [size, temperature, self.temperatures[1]['id']],
            [size, temperature, size],
            [size, temperature, 999999],
            [size, temperature, -1],
            [size, temperature, True],
            [str(size), temperature],
            [size, float(temperature)],
            list(range(51)),
        ]
        for ids in invalid:
            with self.subTest(ids=ids):
                self.expect(client, 'POST', '/api/cart', {'menu_id': self.menu['id'], 'topping_ids': ids}, 400)
        self.assertEqual(self.expect(client, 'GET', '/api/cart'), {'items': [], 'total': 0})
        cart = self.add_cart(client, topping_ids=self.selection + [self.extra['id']])
        self.assertEqual(len(cart['items'][0]['toppings']), 3)
        admin, _ = self.signup('administrator', admin=True)
        self.expect(admin, 'DELETE', f'/api/admin/toppings/{self.extra["id"]}')
        self.expect(client, 'POST', '/api/cart', {'menu_id': self.menu['id'], 'topping_ids': self.selection + [self.extra['id']]}, 400)
        self.assertEqual(len(self.expect(client, 'GET', '/api/cart')['items']), 1)

    def test_quantity_bounds_and_persistence_across_application_instances(self):
        client, _ = self.signup()
        for quantity in (0, -1, 100, True, 1.5, '2', None):
            with self.subTest(create_quantity=quantity):
                self.expect(
                    client,
                    'POST',
                    '/api/cart',
                    {'menu_id': self.menu['id'], 'topping_ids': self.selection, 'quantity': quantity},
                    400,
                )
        cart = self.add_cart(client, quantity=1)
        cid = cart['items'][0]['id']
        cart = self.expect(client, 'PATCH', f'/api/cart/{cid}', {'quantity': 99})
        self.assertEqual(cart['items'][0]['quantity'], 99)
        self.assertEqual(cart['total'], 99 * cart['items'][0]['unit_price'])
        for quantity in (0, -1, 100, True, 1.5, '2', None):
            with self.subTest(update_quantity=quantity):
                self.expect(client, 'PATCH', f'/api/cart/{cid}', {'quantity': quantity}, 400)
        self.assertEqual(self.app_instance().request('GET', '/api/cart', token=client.token).data, cart)
        with running_server(self.database, self.db_name) as server:
            reopened = Client(server, client.token)
            self.assertEqual(self.expect(reopened, 'GET', '/api/cart'), cart)
            cart = self.expect(reopened, 'PATCH', f'/api/cart/{cid}', {'quantity': 1})
        self.assertEqual(self.expect(client, 'GET', '/api/cart'), cart)
        self.expect(client, 'DELETE', f'/api/cart/{cid}')
        self.assertEqual(self.docs('carts'), [])
        self.expect(client, 'PATCH', f'/api/cart/{cid}', {'quantity': 1}, 404)

    def test_empty_checkout_and_invalid_idempotency_keys_do_not_write(self):
        client, _ = self.signup()
        for key in (None, '', 'short', 'x' * 101, 'invalid key with spaces'):
            with self.subTest(key=key):
                self.expect(client, 'POST', '/api/orders', {'idempotency_key': key}, 400)
        key = 'empty-then-retry-0001'
        self.expect(client, 'POST', '/api/orders', {'idempotency_key': key}, 400)
        for table in ('orders', 'order_details', 'order_events'):
            self.assertEqual(self.docs(table), [])
        self.add_cart(client)
        self.checkout(client, key)

    def assert_unavailable_checkout(self, collection_name: str, record: dict[str, Any]):
        client, _ = self.signup()
        admin, _ = self.signup('administrator', admin=True)
        ids = self.selection + [self.extra['id']]
        self.add_cart(client, menu=self.menus[1])
        self.add_cart(client, topping_ids=ids)
        path = f'/api/admin/{collection_name}/{record["id"]}'
        self.expect(admin, 'DELETE', path)
        cart = self.expect(client, 'GET', '/api/cart')
        self.assertTrue(cart['items'][0]['available'])
        self.assertFalse(cart['items'][1]['available'])
        key = 'unavailable-retry-0001'
        self.expect(client, 'POST', '/api/orders', {'idempotency_key': key}, 409)
        self.assertEqual(self.expect(client, 'GET', '/api/cart'), cart)
        for table_name in ('orders', 'order_details', 'order_events'):
            self.assertEqual(self.docs(table_name), [])
        self.expect(admin, 'PATCH', path, {'active': True})
        order = self.checkout(client, key)
        self.assertEqual(len(order['items']), 2)
        self.assertEqual(self.expect(client, 'GET', '/api/cart')['items'], [])

    def test_unavailable_menu_checkout_is_atomic_and_retryable(self):
        self.assert_unavailable_checkout('menus', self.menu)

    def test_unavailable_topping_checkout_is_atomic_and_retryable(self):
        self.assert_unavailable_checkout('toppings', self.extra)

    def test_idempotent_retry_preserves_new_cart_and_keys_are_user_scoped(self):
        client, _ = self.signup()
        other, _ = self.signup('second')
        self.add_cart(client)
        key = 'shared-idempotency-0001'
        order = self.checkout(client, key)
        cart = self.add_cart(client, menu=self.menus[1], quantity=2)
        retry = self.expect(client, 'POST', '/api/orders', {'idempotency_key': key})
        self.assertEqual(retry, order)
        self.assertEqual(self.expect(client, 'GET', '/api/cart'), cart)
        self.add_cart(other)
        other_order = self.checkout(other, key)
        self.assertNotEqual(other_order['id'], order['id'])
        next_order = self.checkout(client, 'different-idempotency-0002')
        self.assertNotEqual(next_order['id'], order['id'])
        self.assertEqual(len(self.docs('orders')), 3)

    def test_concurrent_duplicate_checkout_creates_one_order(self):
        client, _ = self.signup()
        cart = self.add_cart(client, quantity=3)
        workers = 6
        barrier = threading.Barrier(workers, timeout=10)

        def submit():
            independent = Client(self.server, client.token)
            barrier.wait()
            return independent.request('POST', '/api/orders', {'idempotency_key': 'concurrent-checkout-0001'})

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(submit) for _ in range(workers)]
            replies = [future.result(timeout=20) for future in futures]
        statuses = sorted(reply.status for reply in replies)
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(200), workers - 1)
        order = replies[0].data
        for reply in replies:
            self.assertEqual(reply.data, order)
        self.assertEqual(order['net_income'], cart['total'])
        for table in ('orders', 'order_details', 'order_events'):
            self.assertEqual(len(self.docs(table)), 1, table)
        self.assertEqual(self.expect(client, 'GET', '/api/cart')['items'], [])

    def test_status_requires_sequential_transitions_and_current_expected_status(self):
        client, _ = self.signup()
        admin, _ = self.signup('administrator', admin=True)
        self.add_cart(client)
        order = self.checkout(client)
        path = f'/api/admin/orders/{order["id"]}/status'
        self.expect(client, 'PATCH', path, {'expected_status': 'WAITING', 'order_status': 'CONFIRMED'}, 403)
        self.expect(admin, 'PATCH', path, {'order_status': 'CONFIRMED'}, 409)
        self.expect(admin, 'PATCH', path, {'expected_status': 'WAITING', 'order_status': 'COMPLETED'}, 400)
        self.assertEqual(self.expect(client, 'GET', f'/api/orders/{order["id"]}'), order)
        statuses = ['WAITING', 'CONFIRMED', 'PROCESSED', 'COMPLETED']
        for current, following in pairwise(statuses):
            order = self.expect(admin, 'PATCH', path, {'expected_status': current, 'order_status': following})
            self.assertEqual(order['order_status'], following)
            self.assertEqual([e['status'] for e in order['events']], statuses[: statuses.index(following) + 1])
            self.expect(admin, 'PATCH', path, {'expected_status': current, 'order_status': following}, 409)
            self.assertEqual(self.expect(client, 'GET', f'/api/orders/{order["id"]}'), order)
        self.expect(admin, 'PATCH', path, {'expected_status': 'COMPLETED', 'order_status': 'WAITING'}, 400)
        dates = [datetime.fromisoformat(e['created_at']) for e in order['events']]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(order['events'][0]['created_at'], order['created_at'])
        self.assertEqual(order['events'][-1]['created_at'], order['updated_at'])
        events = self.docs('order_events', sort_field='id')
        owner_id = self.expect(client, 'GET', '/api/auth/me')['user']['id']
        admin_id = self.expect(admin, 'GET', '/api/auth/me')['user']['id']
        self.assertEqual([event['actor_id'] for event in events], [owner_id] + [admin_id] * 3)

    def test_order_snapshots_survive_profile_catalog_edits_and_archives(self):
        client, _ = self.signup()
        admin, _ = self.signup('administrator', admin=True)
        self.add_cart(client, topping_ids=self.selection + [self.extra['id']], quantity=2)
        order = self.checkout(client)
        self.expect(client, 'PATCH', '/api/profile', {'fullname': 'Changed Customer'})
        self.expect(
            admin,
            'PATCH',
            f'/api/admin/menus/{self.menu["id"]}',
            {'name': 'Changed Menu', 'price': 99999, 'img': '/images/LogoDonnih.png'},
        )
        self.expect(admin, 'PATCH', f'/api/admin/toppings/{self.extra["id"]}', {'name': 'Changed Extra', 'price': 88888})
        self.expect(admin, 'DELETE', f'/api/admin/menus/{self.menu["id"]}')
        self.expect(admin, 'DELETE', f'/api/admin/toppings/{self.extra["id"]}')
        self.assertEqual(self.expect(client, 'GET', f'/api/orders/{order["id"]}'), order)
        self.assertEqual(self.expect(client, 'GET', '/api/orders'), [order])
        self.assertEqual(self.app_instance().request('GET', '/api/orders', token=client.token).data, [order])

    def test_menu_crud_archive_restore_and_validation(self):
        admin, _ = self.signup('administrator', admin=True)
        customer, _ = self.signup()
        body = {
            'name': 'Integration Breakfast',
            'description': 'Fresh local fixture',
            'category': 'BREAKFAST',
            'price': 15000,
            'img': '/images/LogoDonnih.png',
        }
        menu = self.expect(admin, 'POST', '/api/admin/menus', body, 201)
        self.assertTrue(menu['active'])
        self.assertIn(menu, self.expect(self.client, 'GET', '/api/menus'))
        path = f'/api/admin/menus/{menu["id"]}'
        changed = self.expect(admin, 'PATCH', path, {'name': 'Updated Breakfast', 'price': 17000})
        self.assertEqual(changed['name'], 'Updated Breakfast')
        self.assertEqual(changed['price'], 17000)
        for invalid in (
            {'category': 'UNKNOWN'},
            {'price': -1},
            {'price': True},
            {'active': 1},
            {'img': 'https://example.test/image.png'},
            {'kind': 'extra'},
        ):
            with self.subTest(invalid=invalid):
                self.expect(admin, 'PATCH', path, invalid, 400)
        self.expect(customer, 'PUT', f'/api/favorites/{menu["id"]}')
        self.expect(admin, 'DELETE', path)
        self.expect(admin, 'DELETE', path)
        self.assertNotIn(menu['id'], [m['id'] for m in self.expect(self.client, 'GET', '/api/menus')])
        archived = next(m for m in self.expect(admin, 'GET', '/api/admin/menus') if m['id'] == menu['id'])
        self.assertFalse(archived['active'])
        self.assertEqual(archived['name'], changed['name'])
        self.assertEqual(self.expect(customer, 'GET', '/api/favorites'), [])
        self.expect(customer, 'POST', '/api/cart', {'menu_id': menu['id'], 'topping_ids': self.selection}, 404)
        restored = self.expect(admin, 'PATCH', path, {'active': True})
        self.assertIn(restored, self.expect(self.client, 'GET', '/api/menus'))
        self.expect(admin, 'PATCH', '/api/admin/menus/999999', {'price': 1}, 404)

    def test_extra_topping_crud_and_archive_restore(self):
        admin, _ = self.signup('administrator', admin=True)
        extra = self.expect(admin, 'POST', '/api/admin/toppings', {'name': 'Test Syrup', 'price': 3000}, 201)
        self.assertEqual(extra['kind'], 'extra')
        self.assertTrue(extra['active'])
        self.assertIn(extra, self.expect(self.client, 'GET', '/api/toppings'))
        path = f'/api/admin/toppings/{extra["id"]}'
        changed = self.expect(admin, 'PATCH', path, {'name': 'New Syrup', 'price': 4000})
        self.assertEqual(changed['name'], 'New Syrup')
        self.assertEqual(changed['price'], 4000)
        for invalid in ({'kind': 'size'}, {'price': -1}, {'price': '4000'}, {'active': 'true'}):
            with self.subTest(invalid=invalid):
                self.expect(admin, 'PATCH', path, invalid, 400)
        self.expect(admin, 'DELETE', path)
        self.assertNotIn(extra['id'], [t['id'] for t in self.expect(self.client, 'GET', '/api/toppings')])
        archived = next(t for t in self.expect(admin, 'GET', '/api/admin/toppings') if t['id'] == extra['id'])
        self.assertFalse(archived['active'])
        restored = self.expect(admin, 'PATCH', path, {'active': True})
        self.assertIn(restored, self.expect(self.client, 'GET', '/api/toppings'))
        self.expect(admin, 'POST', '/api/admin/toppings', {'name': 'New Size', 'price': 0, 'kind': 'size'}, 400)

    def test_basic_size_and_temperature_toppings_are_fixed_except_price(self):
        admin, _ = self.signup('administrator', admin=True)
        for topping in self.sizes + self.temperatures:
            path = f'/api/admin/toppings/{topping["id"]}'
            with self.subTest(topping=topping['name']):
                self.expect(admin, 'DELETE', path, status=400)
                for changes in ({'name': 'Renamed'}, {'active': False}, {'kind': 'extra'}):
                    self.expect(admin, 'PATCH', path, changes, 400)
                updated = self.expect(admin, 'PATCH', path, {'price': 1234})
                self.assertEqual(updated, {**topping, 'price': 1234})

    def test_profile_updates_are_validated_and_persisted(self):
        client, user = self.signup()
        changed = self.expect(
            client,
            'PATCH',
            '/api/profile',
            {'fullname': 'Updated Customer', 'phone_number': '+62 812-345678'},
        )['user']
        self.assertEqual(changed, {**user, 'fullname': 'Updated Customer', 'phone_number': '+62 812-345678'})
        for body in ({'fullname': 'X'}, {'phone_number': 'not a phone'}, {'phone_number': None}):
            with self.subTest(body=body):
                self.expect(client, 'PATCH', '/api/profile', body, 400)
        profile = self.app_instance().request('GET', '/api/auth/me', token=client.token).data
        self.assertIsInstance(profile, dict)
        self.assertEqual(cast(dict[str, Any], profile)['user'], changed)

    def test_profile_png_upload_serving_and_replacement(self):
        client, user = self.signup()
        other, other_user = self.signup('second')
        body = {'kind': 'avatar', 'data_url': data_url(), 'user_id': other_user['id']}
        first = self.expect(client, 'POST', '/api/uploads', body, 201)['url']
        self.assertTrue(first.startswith('/uploads/'))
        self.assertTrue(first.endswith('.png'))
        self.assertEqual(self.expect(client, 'GET', '/api/auth/me')['user']['avatar_url'], first)
        self.assertIsNone(self.expect(other, 'GET', '/api/auth/me')['user']['avatar_url'])
        image = self.client.request('GET', first)
        self.assertEqual(image.status, 200)
        self.assertEqual(image.data, PNG)
        self.assertEqual(image.headers['Content-Type'], 'image/png')
        self.assertEqual(int(image.headers['Content-Length']), len(PNG))
        self.assertEqual(image.headers['X-Content-Type-Options'], 'nosniff')
        head = self.client.request('HEAD', first)
        self.assertEqual(head.status, 200)
        self.assertEqual(head.data, b'')
        self.assertEqual(int(head.headers['Content-Length']), len(PNG))
        second = self.expect(client, 'POST', '/api/uploads', body, 201)['url']
        self.assertNotEqual(first, second)
        self.expect(self.client, 'GET', first, status=404)
        uploads = self.docs('uploads')
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]['path'], second)
        self.assertEqual(uploads[0]['user_id'], user['id'])
        self.assertEqual(uploads[0]['kind'], 'avatar')
        self.assertEqual(self.expect(client, 'GET', '/api/auth/me')['user']['avatar_url'], second)

    def test_upload_rejects_invalid_mime_content_base64_and_oversize(self):
        client, _ = self.signup()
        invalid = [
            data_url(mime='text/html'),
            data_url(mime='image/svg+xml'),
            data_url(mime='image/jpeg'),
            data_url(b'not a png'),
            'data:image/png;base64,A',
            'data:image/png;base64,@@@@',
        ]
        for url in invalid:
            with self.subTest(url=url[:60]):
                self.expect(client, 'POST', '/api/uploads', {'kind': 'avatar', 'data_url': url}, 400)
        oversized = PNG + b'\0' * (MAX_IMAGE_BYTES + 1 - len(PNG))
        self.assertLess(len(json.dumps({'kind': 'avatar', 'data_url': data_url(oversized)})), MAX_BODY)
        self.expect(client, 'POST', '/api/uploads', {'kind': 'avatar', 'data_url': data_url(oversized)}, 413)
        self.expect(client, 'POST', '/api/uploads', {'kind': 'avatar', 'data_url': 'x' * 2_800_001}, 413)
        self.expect(client, 'POST', '/api/uploads', {'kind': 'invalid', 'data_url': data_url()}, 400)
        self.assertEqual(self.docs('uploads'), [])
        self.assertIsNone(self.expect(client, 'GET', '/api/auth/me')['user']['avatar_url'])

    def test_menu_image_upload_requires_admin_and_can_be_used_in_catalog(self):
        customer, _ = self.signup()
        admin, _ = self.signup('administrator', admin=True)
        body = {'kind': 'menu', 'data_url': data_url()}
        self.expect(self.client, 'POST', '/api/uploads', body, 401)
        self.expect(customer, 'POST', '/api/uploads', body, 403)
        self.assertEqual(self.docs('uploads'), [])
        url = self.expect(admin, 'POST', '/api/uploads', body, 201)['url']
        changed = self.expect(admin, 'PATCH', f'/api/admin/menus/{self.menu["id"]}', {'img': url})
        self.assertEqual(changed['img'], url)
        self.assertEqual(self.client.request('GET', url).data, PNG)
        self.assertIsNone(self.expect(admin, 'GET', '/api/auth/me')['user']['avatar_url'])
        avatar = self.expect(customer, 'POST', '/api/uploads', {'kind': 'avatar', 'data_url': data_url()}, 201)['url']
        self.expect(admin, 'PATCH', f'/api/admin/menus/{self.menu["id"]}', {'img': avatar}, 400)

    def test_search_category_and_combined_filters(self):
        self.assertEqual(len(self.menus), 7)
        for category in ('COFFEE', 'NON-COFFEE', 'DESSERT', 'BREAKFAST', 'MEAL'):
            with self.subTest(category=category):
                expected = [m for m in self.menus if m['category'] == category]
                self.assertEqual(self.expect(self.client, 'GET', '/api/menus?' + urlencode({'category': category})), expected)
        for search in ('CAPPUCCINO', 'foam', 'Tea', 'not-present', "' OR 1=1 --", '%'):
            with self.subTest(search=search):
                expected = [m for m in self.menus if search.lower() in (m['name'] + ' ' + m['description']).lower()]
                self.assertEqual(self.expect(self.client, 'GET', '/api/menus?' + urlencode({'search': search})), expected)
        self.assertEqual(self.expect(self.client, 'GET', '/api/menus?search=Tea&category=COFFEE'), [])
        tea = self.expect(self.client, 'GET', '/api/menus?search=Tea&category=NON-COFFEE')
        self.assertEqual(len(tea), 2)
        self.expect(self.client, 'GET', '/api/menus?category=INVALID', status=400)
        self.expect(self.client, 'GET', '/api/menus?search=' + 'x' * 101, status=400)


class DatabaseIntegrationTests(_MongoTestCase):
    def setUp(self):
        self.database, self.db_name = self.prepare_isolated_db('donnih_db')

    def test_initialize_and_demo_seed_are_idempotent(self):
        initialize(self.database, db_name=self.db_name)
        db = self.db_handle()
        for col in ('menus', 'users', 'sessions', 'orders', 'metadata'):
            self.assertEqual(db[col].count_documents({}), 0)

        health = Application(self.database, db_name=self.db_name).request('GET', '/api/health').data
        self.assertIsInstance(health, dict)
        self.assertFalse(cast(dict[str, Any], health)['demo_data'])

        seed_demo(self.database, db_name=self.db_name)
        self.assertEqual(db['menus'].count_documents({}), 7)
        self.assertEqual(db['toppings'].count_documents({}), 6)
        self.assertEqual(db['users'].count_documents({}), 0)

        db['menus'].update_one({'id': 1}, {'$set': {'name': 'Locally edited', 'price': 123}})
        seed_demo(self.database, db_name=self.db_name)
        initialize(self.database, db_name=self.db_name)
        seed_demo(self.database, db_name=self.db_name)

        edited = db['menus'].find_one({'id': 1})
        self.assertIsNotNone(edited)
        self.assertEqual(edited['name'], 'Locally edited')
        self.assertEqual(edited['price'], 123)

        health_after = Application(self.database, db_name=self.db_name).request('GET', '/api/health').data
        self.assertIsInstance(health_after, dict)
        self.assertTrue(cast(dict[str, Any], health_after)['demo_data'])

    def test_cli_init_only_seeds_when_demo_is_explicit(self):
        command = [
            sys.executable,
            '-m',
            'backend.cli',
            '--database',
            self.database,
            '--db-name',
            self.db_name,
            'init',
        ]
        for arguments in ([], [], ['--demo'], ['--demo']):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    command + arguments,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                db = self.db_handle()
                self.assertEqual(db['menus'].count_documents({}), 7 if arguments else 0)
                self.assertEqual(db['users'].count_documents({}), 0)
        self.assertEqual(self.db_handle()['metadata'].count_documents({}), 1)


if __name__ == '__main__':
    unittest.main()