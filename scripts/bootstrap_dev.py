"""Explicit operator-authorized provisioning of isolated Telegram/Notion DEV."""
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key
from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession

ROOT = Path(__file__).resolve().parents[1]


async def main():
    logging.disable(logging.CRITICAL)
    production = dotenv_values(ROOT / '.env')
    target = ROOT / '.env.dev'
    dev = dotenv_values(target) if target.exists() else {}
    if not dev.get('TELEGRAM_TOKEN'):
        credentials = dotenv_values('/home/alek/.assistant-secrets/telegram.env')
        source = SQLiteSession('/home/alek/.assistant/state/telegram/armen')
        session = StringSession(StringSession.save(source)); source.close()
        client = TelegramClient(session, int(credentials['TG_API_ID']), credentials['TG_API_HASH'])
        await client.connect()
        try:
            assert await client.is_user_authorized()
            peer = await client.get_entity('BotFather')
            await client.get_messages(peer, limit=20)
            async with client.conversation(peer, timeout=45) as conversation:
                await conversation.send_message('/newbot')
                reply = await conversation.get_response()
                if 'name' not in reply.raw_text.lower():
                    raise RuntimeError('BotFather did not request a name')
                await conversation.send_message('Nutrition Bot DEV')
                reply = await conversation.get_response()
                if 'username' not in reply.raw_text.lower():
                    raise RuntimeError('BotFather did not request a username')
                token = None
                for username in (os.environ['DEV_BOT_USERNAME'],):
                    await conversation.send_message(username)
                    reply = await conversation.get_response()
                    match = re.search(r'\b\d{6,}:[A-Za-z0-9_-]{25,}\b', reply.raw_text)
                    if match:
                        token = match.group(0)
                        break
                    if 'taken' not in reply.raw_text.lower():
                        raise RuntimeError('BotFather creation did not complete')
                if not token:
                    raise RuntimeError('Development usernames unavailable')
                dev = {**production, 'TELEGRAM_TOKEN':token, 'NOTION_DATABASE_ID':'',
                       'DATABASE_PATH':str(ROOT/'.data/dev/nutrition.db'), 'RESPONSE_LANGUAGE':'English',
                       'MINI_APP_URL':os.environ.get('DEV_MINI_APP_URL', ''), 'MINI_APP_PORT':'8766'}
                target.touch(mode=0o600, exist_ok=True)
                os.chmod(target,0o600)
                for key,value in dev.items():
                    if value is not None:
                        set_key(target,key,value)
                print('dev_bot_created=PASS',flush=True)
        finally:
            await client.disconnect()
    assert dev['TELEGRAM_TOKEN'] != production['TELEGRAM_TOKEN']
    async with httpx.AsyncClient(timeout=30) as http:
        identity = (await http.post('https://api.telegram.org/bot'+dev['TELEGRAM_TOKEN']+'/getMe')).json()
        assert identity.get('ok')
        print('dev_bot_username='+identity['result']['username'],flush=True)
        if not dev.get('NOTION_DATABASE_ID'):
            headers={'Authorization':'Bearer '+production['NOTION_TOKEN'],'Notion-Version':'2022-06-28'}
            parent_db=await http.get('https://api.notion.com/v1/databases/'+production['NOTION_DATABASE_ID'],headers=headers)
            parent_db.raise_for_status()
            parent=parent_db.json()['parent']
            assert parent['type']=='page_id'
            # Clone property types, not data or integration-private property ids.
            properties={'Name':{'title':{}}, 'Date':{'date':{}}, 'Source':{'select':{'options':[]}}}
            properties.update({name:{'number':{'format':'number'}} for name in ('Calories','Protein','Carbs','Fat','Fiber')})
            response=await http.post('https://api.notion.com/v1/databases',headers=headers,json={
                'parent':{'type':'page_id','page_id':parent['page_id']},
                'title':[{'type':'text','text':{'content':'Nutrition Bot DEV — test diary'}}], 'properties':properties})
            response.raise_for_status()
            database_id=response.json()['id']
            assert database_id.replace('-','') != production['NOTION_DATABASE_ID'].replace('-','')
            set_key(target,'NOTION_DATABASE_ID',database_id)
            print('dev_notion_database_created=PASS',flush=True)


if __name__ == '__main__':
    if '--apply' not in sys.argv:
        raise SystemExit('Requires --apply and explicit operator authorization to provision DEV')
    try:
        asyncio.run(main())
    except Exception as exc:
        print('dev_bootstrap=FAIL; error_type='+type(exc).__name__,flush=True)
        raise SystemExit(1) from None
