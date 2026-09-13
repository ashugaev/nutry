"""Read-only production acceptance: commands only, never synthetic food or prefs."""
import asyncio
import logging
import sqlite3
import sys
from pathlib import Path
import httpx
from dotenv import dotenv_values


async def wait_for_schema(path, attempts=30):
    """Wait for startup migrations without creating or modifying the database."""
    for attempt in range(attempts):
        try:
            with sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True) as db:
                db.execute('SELECT language FROM user_preferences LIMIT 1').fetchall()
            return
        except sqlite3.OperationalError:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(1)


async def main():
    from telethon import TelegramClient
    from telethon.sessions import SQLiteSession, StringSession

    logging.disable(logging.CRITICAL)
    root=Path(__file__).resolve().parents[1]; config=dotenv_values(root/'.env')
    credentials=dotenv_values('/home/alek/.assistant-secrets/telegram.env')
    source=SQLiteSession('/home/alek/.assistant/state/telegram/armen')
    session=StringSession(StringSession.save(source)); source.close()
    client=TelegramClient(session,int(credentials['TG_API_ID']),credentials['TG_API_HASH'])
    await wait_for_schema((root/config.get('DATABASE_PATH','.data/nutrition.db')).resolve())
    def rows():
        path=(root/config.get('DATABASE_PATH','.data/nutrition.db')).resolve()
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            return db.execute('SELECT * FROM entries ORDER BY id').fetchall()
    before=rows()
    await client.connect()
    try:
        me=await client.get_me()
        assert me.id in {int(config['OWNER_USER_ID'])}|{int(v) for v in config.get('ALLOWED_USER_IDS','').split(',') if v.strip()}
        async with httpx.AsyncClient(timeout=20) as http:
            result=(await http.post('https://api.telegram.org/bot'+config['TELEGRAM_TOKEN']+'/getMe')).json()
        peer=await client.get_entity(result['result']['username'])
        await client.get_messages(peer,limit=20)
        path=(root/config.get('DATABASE_PATH','.data/nutrition.db')).resolve()
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            choice=db.execute('SELECT language FROM user_preferences WHERE user_id=?',(me.id,)).fetchone()
        ru=bool(choice and choice[0]=='ru')
        for command,prefixes in (('/help',('Пришли',) if ru else ('Send food',)),('/today',('Сегодня:',) if ru else ('Today:',))):
            sent=await client.send_message(peer,command)
            for _ in range(30):
                replies=await client.get_messages(peer,min_id=sent.id,limit=10)
                if any(not m.out and (m.raw_text or '').startswith(prefixes) for m in replies): break
                await asyncio.sleep(1)
            else: raise TimeoutError('Production command response missing')
        assert before==rows()
        print('production_readonly_commands_and_unchanged_diary=PASS',flush=True)
    finally: await client.disconnect()


if __name__=='__main__':
    if '--run-live' not in sys.argv: raise SystemExit('Requires --run-live for read-only production smoke')
    try: asyncio.run(main())
    except Exception as exc:
        print('production_smoke=FAIL; error_type='+type(exc).__name__,flush=True)
        raise SystemExit(1) from None
