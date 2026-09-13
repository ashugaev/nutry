import hashlib
import hmac
import json
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from services.analyzer import Estimate
from services.dashboard import authenticate, create_app, statistics
from services.store import NutritionStore


def signed(user=42, stamp=1000, **extra):
    fields = {'auth_date': str(stamp), 'user': json.dumps({'id': user}), **extra}
    secret = hmac.new(b'WebAppData', b'fake-token', hashlib.sha256).digest()
    check = '\n'.join(f'{key}={fields[key]}' for key in sorted(fields))
    fields['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class AuthTests(unittest.TestCase):
    def test_valid_both_accounts(self):
        for user in (42, 84):
            self.assertEqual(authenticate(signed(user), 'fake-token', {42, 84}, now=1000), user)

    def test_fail_closed(self):
        for raw in ('', 'bad', signed(99), signed(stamp=-4000), signed(stamp=9000),
                    signed()+'&user=%7B%22id%22%3A99%7D', signed().replace('1000','1001'),
                    signed(chat_type='group'), signed(user=True), signed(user='42')):
            with self.subTest(raw=raw), self.assertRaises(web.HTTPUnauthorized):
                authenticate(raw, 'fake-token', {42}, now=1000)


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = NutritionStore(self.tmp.name+'/test.db', 'Europe/Moscow')
        self.settings = SimpleNamespace(telegram_token='fake-token', owner_user_id=42,
                                        allowed_user_ids=frozenset({84}), response_language='Russian')
        self.client = TestClient(TestServer(create_app(self.settings, self.store)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    async def test_unauthorized_never_reads_store(self):
        self.store._connect = MagicMock(side_effect=AssertionError('must not read diary'))
        response = await self.client.get('/api/stats')
        self.assertEqual(response.status, 401)
        self.store._connect.assert_not_called()
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    async def test_authenticated_api_range_and_empty_days(self):
        import time
        headers = {'X-Telegram-Init-Data': signed(84, int(time.time()))}
        response = await self.client.get('/api/stats?days=7', headers=headers)
        payload = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(len(payload['days']), 7)
        self.assertEqual(payload['language'], 'en')
        self.store.set_language(84, 'ru')
        changed = await self.client.get('/api/stats', headers=headers)
        self.assertEqual((await changed.json())['language'], 'ru')
        other = await self.client.get('/api/stats', headers={'X-Telegram-Init-Data': signed(42, int(time.time()))})
        self.assertEqual((await other.json())['language'], 'en')
        self.assertEqual(payload['days'][-1]['date'], payload['today'])
        self.assertEqual(payload['days'][-1]['count'], 0)
        for bad in ('0','91','banana'):
            response = await self.client.get('/api/stats?days='+bad, headers=headers)
            self.assertEqual(response.status, 400)

    async def test_only_public_assets_are_available(self):
        response = await self.client.get('/')
        self.assertEqual(response.status, 200)
        html = await response.text()
        self.assertIn('telegram-web-app.js', html)
        self.assertIn('maximum-scale=1, user-scalable=no', html)
        self.assertNotIn('id="refresh"', html)
        css = await self.client.get('/style.css')
        self.assertIn('touch-action: pan-x pan-y', await css.text())
        self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
        for path in ('/.env', '/config.py', '/nutrition.db'):
            self.assertEqual((await self.client.get(path)).status, 404)

    def test_timezone_totals_and_corrections(self):
        # 22:30 UTC belongs to the next day in Moscow.
        stamp = datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc)
        estimate = Estimate('Apple', 52, .3, 14, .2, 'medium', '', fiber_g=2.4)
        entry = self.store.add(estimate, 'text', stamp)
        result = statistics(self.store, 2, stamp)
        self.assertEqual(result['today'], '2026-09-12')
        self.assertEqual(result['days'][0]['count'], 0)
        self.assertEqual(result['days'][1]['calories_kcal'], 52)
        self.assertEqual(result['days'][1]['fiber_g'], 2.4)
        self.assertEqual(result['days'][1]['fiber_missing'], 0)
        self.assertEqual(result['days'][1]['meals'][0]['time'], '01:30')
        self.store.correct(entry.id, Estimate('Apple', 104, .6, 28, .4, 'medium', ''))
        self.assertEqual(statistics(self.store, 2, stamp)['days'][1]['calories_kcal'], 104)
        self.assertEqual(statistics(self.store, 2, stamp)['days'][1]['fiber_missing'], 1)
        self.store.delete(entry.id)
        self.assertEqual(statistics(self.store, 2, stamp)['days'][1]['count'], 0)
