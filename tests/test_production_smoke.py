import sqlite3
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.production_smoke import wait_for_schema


class ProductionReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_startup_schema_without_writes(self):
        connection = MagicMock()
        with patch('scripts.production_smoke.sqlite3.connect', side_effect=[
            sqlite3.OperationalError('schema not ready'), connection,
        ]) as connect, patch('scripts.production_smoke.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await wait_for_schema('/tmp/example.db')
        sleep.assert_awaited_once_with(1)
        self.assertEqual(connect.call_count, 2)
        connect.assert_called_with('file:/tmp/example.db?mode=ro', uri=True)
        connection.__enter__.return_value.execute.assert_called_once_with(
            'SELECT language FROM user_preferences LIMIT 1')

    async def test_readiness_failure_is_bounded(self):
        with patch('scripts.production_smoke.sqlite3.connect', side_effect=sqlite3.OperationalError), \
                patch('scripts.production_smoke.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaises(sqlite3.OperationalError):
                await wait_for_schema('/tmp/example.db', attempts=2)
        sleep.assert_awaited_once_with(1)
