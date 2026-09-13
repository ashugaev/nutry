"""Authorized live reply/no-food smoke; uses the existing allowed Assistant account."""
import asyncio
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession
from live_lock import live_lock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.environments import dev_values
import httpx


async def main():
    logging.disable(logging.CRITICAL)
    root = Path(__file__).resolve().parents[1]
    config = dev_values(root)
    credentials = dotenv_values('/home/alek/.assistant-secrets/telegram.env')
    source = SQLiteSession('/home/alek/.assistant/state/telegram/armen')
    session = StringSession(StringSession.save(source))
    source.close()
    client = TelegramClient(session, int(credentials['TG_API_ID']), credentials['TG_API_HASH'])
    entry_id = None
    await client.connect()
    me = await client.get_me()
    allowed = {int(config['OWNER_USER_ID'])} | {int(value.strip()) for value in (config.get('ALLOWED_USER_IDS') or '').split(',') if value.strip()}
    if me.id not in allowed:
        await client.disconnect()
        raise RuntimeError('Connected test account is not allowed; configuration left unchanged')
    async with httpx.AsyncClient(timeout=20) as http:
        identity=(await http.post('https://api.telegram.org/bot'+config['TELEGRAM_TOKEN']+'/getMe')).json()
        assert identity.get('ok')
    peer = await client.get_entity(identity['result']['username'])
    await client.get_messages(peer, limit=20)

    async def wait(sent, prefix):
        prefixes = {'Saved:': ('Saved:', 'Добавлено:'), 'Corrected:': ('Corrected:', 'Исправлено:'), 'Deleted.': ('Deleted.', 'Запись удалена.'), 'Пришли': ('Пришли', 'Send food'), 'Не могу определить': ('Не могу определить', 'I could not identify')}.get(prefix, (prefix,))
        for _ in range(75):
            await asyncio.sleep(2)
            for message in await client.get_messages(peer, min_id=sent.id, limit=20):
                if not message.out and (message.raw_text or '').startswith(prefixes):
                    return message
        raise TimeoutError('Expected bot response not received')

    def rows():
        with sqlite3.connect(root / config.get('DATABASE_PATH', '.data/nutrition.db')) as db:
            return db.execute('SELECT id, calories_kcal FROM entries').fetchall()

    try:
        sent = await client.send_message(peer, '/help')
        await wait(sent, 'Пришли')
        print('live_help=PASS', flush=True)
        before = rows()
        sent = await client.send_message(peer, 'QA: просто привет! Это проверка связи, еды здесь нет.')
        await wait(sent, 'Не могу определить')
        assert rows() == before
        print('live_nonfood_no_insert=PASS', flush=True)
        sent = await client.send_message(peer, 'QA: съел одно яблоко весом 100 граммов.')
        saved = await wait(sent, 'Saved:')
        entry_id = int(re.search(r'#(\d+)', saved.raw_text).group(1))
        assert sum(type(entity).__name__ == 'MessageEntityBold' for entity in (saved.entities or [])) >= 2
        assert 'Ответь на это сообщение' not in saved.raw_text
        assert 'Reply to this message' not in saved.raw_text
        print('live_meal_formatting=PASS', flush=True)
        original = dict(rows())[entry_id]
        with sqlite3.connect(root / config.get('DATABASE_PATH', '.data/nutrition.db')) as db:
            original_fiber = db.execute('SELECT fiber_g FROM entries WHERE id=?', (entry_id,)).fetchone()[0]
        assert original_fiber is not None and original_fiber > 0
        assert 'Клетчатка:' in saved.raw_text or 'Fiber:' in saved.raw_text
        sent = await client.send_message(peer, 'Поправка: яблоко весило 300 граммов, а не 100.', reply_to=saved.id)
        corrected = await wait(sent, 'Corrected:')
        assert int(re.search(r'#(\d+)', corrected.raw_text).group(1)) == entry_id
        assert sum(type(entity).__name__ == 'MessageEntityBold' for entity in (corrected.entities or [])) >= 2
        assert dict(rows())[entry_id] > original
        with sqlite3.connect(root / config.get('DATABASE_PATH', '.data/nutrition.db')) as db:
            corrected_fiber = db.execute('SELECT fiber_g FROM entries WHERE id=?', (entry_id,)).fetchone()[0]
        assert corrected_fiber > original_fiber
        print('live_fiber_estimate_and_correction=PASS', flush=True)
        print('live_reply_updates_same_entry=PASS', flush=True)
    finally:
        if entry_id is not None:
            sent = await client.send_message(peer, f'/delete {entry_id}')
            await wait(sent, 'Deleted.')
            assert entry_id not in dict(rows())
            print('live_test_entry_deleted=PASS', flush=True)
        await client.disconnect()


if __name__ == '__main__':
    if '--run-live' not in sys.argv:
        raise SystemExit('Requires explicit --run-live and account-owner authorization.')
    try:
        with live_lock():
            asyncio.run(main())
    except Exception as exc:
        print('live_reply=FAIL; error_type='+type(exc).__name__, flush=True)
        raise SystemExit(1) from None
