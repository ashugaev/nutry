import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.analyzer import Estimate


@dataclass(frozen=True)
class Entry:
    id: int
    created_at: str
    dish: str
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: str
    notes: str
    source: str
    notion_page_id: str | None = None
    fiber_g: float | None = None


class NutritionStore:
    def __init__(self, path: str, timezone: str):
        self.path = path
        self.timezone = ZoneInfo(timezone)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, dish TEXT NOT NULL,
                calories_kcal REAL NOT NULL, protein_g REAL NOT NULL,
                carbs_g REAL NOT NULL, fat_g REAL NOT NULL, confidence TEXT NOT NULL,
                notes TEXT NOT NULL, source TEXT NOT NULL,
                notion_page_id TEXT)""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(entries)")}
            if "notion_page_id" not in columns:
                db.execute("ALTER TABLE entries ADD COLUMN notion_page_id TEXT")
            if "fiber_g" not in columns:
                db.execute("ALTER TABLE entries ADD COLUMN fiber_g REAL")
            db.execute('''CREATE TABLE IF NOT EXISTS message_entries (
                chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
                entry_id INTEGER NOT NULL, PRIMARY KEY(chat_id, message_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL CHECK(language IN ('en','ru')))''')

    def get_language(self, user_id: int) -> str:
        with self._connect() as db:
            row = db.execute('SELECT language FROM user_preferences WHERE user_id=?', (user_id,)).fetchone()
        return row[0] if row else 'en'

    def set_language(self, user_id: int, language: str) -> None:
        if language not in {'en', 'ru'}:
            raise ValueError('Language must be en or ru')
        with self._connect() as db:
            db.execute('INSERT INTO user_preferences(user_id,language) VALUES (?,?) '
                       'ON CONFLICT(user_id) DO UPDATE SET language=excluded.language', (user_id, language))

    def link_message(self, chat_id: int, message_id: int, entry_id: int) -> None:
        with self._connect() as db:
            db.execute('INSERT OR REPLACE INTO message_entries VALUES (?,?,?)',
                       (chat_id, message_id, entry_id))

    def message_entry_id(self, chat_id: int, message_id: int) -> int | None:
        with self._connect() as db:
            row = db.execute('SELECT entry_id FROM message_entries WHERE chat_id=? AND message_id=?',
                             (chat_id, message_id)).fetchone()
        return row[0] if row else None

    def _connect(self):
        return sqlite3.connect(self.path)

    def add(self, estimate: Estimate, source: str, created_at: datetime | None = None) -> Entry:
        stamp = (created_at or datetime.now(self.timezone)).astimezone(self.timezone).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO entries (created_at,dish,calories_kcal,protein_g,carbs_g,fat_g,confidence,notes,source,fiber_g) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (stamp, estimate.dish, estimate.calories_kcal, estimate.protein_g,
                 estimate.carbs_g, estimate.fat_g, estimate.confidence, estimate.notes, source, estimate.fiber_g),
            )
            entry_id = cursor.lastrowid
        return self.get(entry_id)

    def set_notion_page(self, entry_id: int, page_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE entries SET notion_page_id=? WHERE id=?", (page_id, entry_id))

    def get(self, entry_id: int) -> Entry | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        return Entry(*row) if row else None

    def recent(self, limit: int = 10) -> list[Entry]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM entries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [Entry(*row) for row in rows]

    def today(self, now: datetime | None = None) -> list[Entry]:
        day = (now or datetime.now(self.timezone)).astimezone(self.timezone).date().isoformat()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM entries WHERE substr(created_at,1,10)=? ORDER BY id", (day,)).fetchall()
        return [Entry(*row) for row in rows]

    def delete(self, entry_id: int) -> bool:
        with self._connect() as db:
            # Keep tombstones so replies to deleted entries cannot target a reused id.
            db.execute('UPDATE message_entries SET entry_id=-1 WHERE entry_id=?', (entry_id,))
            cursor = db.execute("DELETE FROM entries WHERE id=?", (entry_id,))
        return cursor.rowcount == 1

    def correct(self, entry_id: int, estimate: Estimate) -> Entry | None:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE entries SET dish=?,calories_kcal=?,protein_g=?,carbs_g=?,fat_g=?,confidence=?,notes=?,fiber_g=? WHERE id=?",
                (estimate.dish, estimate.calories_kcal, estimate.protein_g, estimate.carbs_g,
                 estimate.fat_g, estimate.confidence, estimate.notes, estimate.fiber_g, entry_id),
            )
        return self.get(entry_id) if cursor.rowcount else None


def totals(entries: list[Entry]) -> tuple[float, float, float, float]:
    return tuple(sum(getattr(e, field) for e in entries) for field in ("calories_kcal", "protein_g", "carbs_g", "fat_g"))
