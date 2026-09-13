import tempfile
import sqlite3
from dataclasses import replace
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.analyzer import Estimate
from services.store import NutritionStore, totals


ESTIMATE = Estimate("Pasta", 500, 20, 70, 15, "medium", "estimate")


class StoreTests(unittest.TestCase):
    def test_fiber_migration_and_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'old.db')
            store = NutritionStore(path, 'UTC')
            first = store.add(ESTIMATE, 'text')
            with sqlite3.connect(path) as db:
                db.execute('ALTER TABLE entries DROP COLUMN fiber_g')
            store = NutritionStore(path, 'UTC')
            self.assertIsNone(store.get(first.id).fiber_g)
            changed = store.correct(first.id, replace(ESTIMATE, fiber_g=4.5))
            self.assertEqual(changed.fiber_g, 4.5)
            store = NutritionStore(path, 'UTC')
            self.assertEqual(store.get(first.id).fiber_g, 4.5)
            self.assertEqual(store.add(replace(ESTIMATE, fiber_g=2), 'photo').fiber_g, 2)

    def test_persistence_totals_correction_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "diary.db")
            store = NutritionStore(path, "UTC")
            now = datetime(2026, 9, 12, 12, tzinfo=ZoneInfo("UTC"))
            first = store.add(ESTIMATE, "text", now)
            store.add(Estimate("Apple", 100, 1, 25, 0, "high", ""), "photo", now)
            self.assertEqual(totals(store.today(now)), (600, 21, 95, 15))
            changed = store.correct(first.id, Estimate("Small pasta", 400, 18, 55, 12, "high", "weighed"))
            self.assertEqual(changed.calories_kcal, 400)
            store.set_notion_page(first.id, "page-1")
            self.assertEqual(store.get(first.id).notion_page_id, "page-1")
            self.assertTrue(store.delete(first.id))
            self.assertEqual(len(store.recent()), 1)
