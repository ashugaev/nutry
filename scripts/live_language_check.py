"""Exercise DEV language commands, callback buttons and restart persistence."""
import asyncio
import logging
import sqlite3
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values
from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession
from live_lock import live_lock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.environments import dev_values


async def main():
    logging.disable(logging.CRITICAL)
    config=dev_values(ROOT)
    credentials=dotenv_values('/home/alek/.assistant-secrets/telegram.env')
    source=SQLiteSession('/home/alek/.assistant/state/telegram/armen')
    session=StringSession(StringSession.save(source)); source.close()
    client=TelegramClient(session,int(credentials['TG_API_ID']),credentials['TG_API_HASH'])
    await client.connect()
    try:
        me=await client.get_me()
        assert me.id in {int(config['OWNER_USER_ID'])}|{int(v) for v in config.get('ALLOWED_USER_IDS','').split(',') if v.strip()}
        async with httpx.AsyncClient(timeout=20) as http:
            identity=(await http.post('https://api.telegram.org/bot'+config['TELEGRAM_TOKEN']+'/getMe')).json()
        peer=await client.get_entity(identity['result']['username'])
        await client.get_messages(peer,limit=20)
        def prefs():
            with sqlite3.connect(config['DATABASE_PATH']) as db:
                return dict(db.execute('SELECT user_id,language FROM user_preferences'))
        others={key:value for key,value in prefs().items() if key!=me.id}
        async def reply(sent,prefixes):
            for _ in range(40):
                for message in await client.get_messages(peer,min_id=sent.id,limit=10):
                    if not message.out and (message.raw_text or '').startswith(prefixes): return message
                await asyncio.sleep(1)
            raise TimeoutError('Expected language response missing')
        async def command(text,prefixes):
            return await reply(await client.send_message(peer,text),prefixes)
        initial=await command('/start','Пришли' if prefs().get(me.id)=='ru' else 'Send food')
        assert initial.buttons and {b.text for b in initial.buttons[0]}=={'English','Русский'}
        await command('/lang en','Language saved: English')
        start=await command('/start','Send food')
        assert start.buttons and {b.text for b in start.buttons[0]}=={'English','Русский'}
        await start.click(text='Русский')
        for _ in range(30):
            edited=await client.get_messages(peer,ids=start.id)
            if edited.raw_text.startswith('Язык сохранён'): break
            await asyncio.sleep(1)
        else: raise TimeoutError('Language callback did not update message')
        assert prefs()[me.id]=='ru'
        await command('/help','Пришли')
        print('dev_language_buttons_ru=PASS',flush=True)
        if '--restart-check' in sys.argv:
            previous=(ROOT/'.data/dev/pid').read_text()
            (ROOT/'.data/dev/restart.request').write_text(uuid.uuid4().hex)
            for _ in range(60):
                await asyncio.sleep(1)
                if (ROOT/'.data/dev/pid').read_text()!=previous: break
            else: raise TimeoutError('DEV did not restart')
            await command('/help','Пришли')
            assert prefs()[me.id]=='ru'
            print('dev_language_restart_persistence=PASS',flush=True)
        await command('/lang en','Language saved: English')
        await command('/help','Send food')
        invalid=await command('/lang de','Choose your language')
        assert invalid.buttons and prefs()[me.id]=='en'
        assert {key:value for key,value in prefs().items() if key!=me.id}==others
        if '--russian' in sys.argv:
            await command('/lang ru','Язык сохранён')
        print('dev_language_en_and_account_isolation=PASS',flush=True)
    finally:
        await client.disconnect()


if __name__=='__main__':
    if '--run-live' not in sys.argv: raise SystemExit('Requires --run-live; DEV only')
    try:
        with live_lock(): asyncio.run(main())
    except Exception as exc:
        print('dev_language=FAIL; error_type='+type(exc).__name__,flush=True)
        raise SystemExit(1) from None
