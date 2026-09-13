"""Read-only live Telegram Mini App verification; never emit signed launch URLs."""
import asyncio
import logging
import sys
import os
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from dotenv import dotenv_values
from telethon import TelegramClient, functions
from telethon.sessions import SQLiteSession, StringSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_settings
from services.store import NutritionStore
from services.dashboard import statistics
from services.environments import dev_values


async def main():
    logging.disable(logging.CRITICAL)
    root=Path(__file__).resolve().parents[1]
    values=dotenv_values(root/'.env') if '--production' in sys.argv else dev_values(root)
    os.environ.update({key:value for key,value in values.items() if value is not None})
    settings = load_settings(None)
    if not settings.mini_app_url:
        print('live_mini_app=DISABLED')
        return
    credentials = dotenv_values('/home/alek/.assistant-secrets/telegram.env')
    source = SQLiteSession('/home/alek/.assistant/state/telegram/armen')
    session = StringSession(StringSession.save(source)); source.close()
    client = TelegramClient(session, int(credentials['TG_API_ID']), credentials['TG_API_HASH'])
    await client.connect()
    try:
        me = await client.get_me()
        assert me.id in settings.allowed_user_ids | {settings.owner_user_id}
        async with httpx.AsyncClient(timeout=30) as http:
            # Bot API identity/menu checks are not a second getUpdates poller.
            base = 'https://api.telegram.org/bot'+settings.telegram_token
            identity = (await http.post(base+'/getMe')).json()
            assert identity.get('ok')
            peer = await client.get_input_entity(identity['result']['username'])
            # An account must have started this particular bot before chat-scoped menus exist.
            for user_id in {me.id}:
                menu = (await http.post(base+'/getChatMenuButton', json={'chat_id': user_id})).json()
                assert menu.get('ok') and menu['result']['type'] == 'web_app'
                assert menu['result']['web_app']['url'].rstrip('/') == settings.mini_app_url.rstrip('/')
            print('live_mini_app_menu=PASS', flush=True)
            view = await client(functions.messages.RequestWebViewRequest(
                peer=peer, bot=peer, platform='android', from_bot_menu=True, url=settings.mini_app_url))
            init_data = parse_qs(urlsplit(view.url).fragment)['tgWebAppData'][0]
            public = await http.get(settings.mini_app_url+'/')
            assert public.status_code == 200 and 'telegram-web-app.js' in public.text
            denied = await http.get(settings.mini_app_url+'/api/stats')
            assert denied.status_code == 401
            print('live_mini_app_public_and_guard=PASS', flush=True)
            for days in (7, 30, 90):
                response = await http.get(settings.mini_app_url+'/api/stats', params={'days': days},
                                          headers={'X-Telegram-Init-Data': init_data})
                assert response.status_code == 200
                db_path=(root/settings.database_path).resolve()
                store=SimpleNamespace(timezone=ZoneInfo(settings.timezone),
                                      _connect=lambda: sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True))
                expected = statistics(store, days)
                payload = response.json()
                assert payload['days'] == expected['days'] and payload['today'] == expected['today']
                with store._connect() as db:
                    choice=db.execute('SELECT language FROM user_preferences WHERE user_id=?',(me.id,)).fetchone()
                assert payload['language'] == (choice[0] if choice else 'en')
            print('live_mini_app_signed_data_and_sqlite_totals=PASS', flush=True)
    finally:
        await client.disconnect()


if __name__ == '__main__':
    if '--run-live' not in sys.argv:
        raise SystemExit('Requires explicit --run-live and existing account authorization')
    try:
        asyncio.run(main())
    except Exception as exc:
        # HTTP exceptions may include the Bot API token or signed user data.
        print('live_mini_app=FAIL; error_type='+type(exc).__name__, flush=True)
        raise SystemExit(1) from None
