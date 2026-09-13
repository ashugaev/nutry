"""Explicitly authorized live QA. Never part of make test.

Uses Assistant's existing allowed user session; never changes owner configuration
or runtime ownership, and deletes only entries created by this run.
Requires optional telethon/Pillow and ffmpeg with flite.
"""
import asyncio
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values
from PIL import Image, ImageDraw
from telethon import TelegramClient, functions
from telethon.sessions import SQLiteSession, StringSession
from live_lock import live_lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.environments import dev_values
ENV = ROOT / '.env.dev'


async def run():
    logging.disable(logging.CRITICAL)
    config = dev_values(ROOT)
    credentials = dotenv_values('/home/alek/.assistant-secrets/telegram.env')
    source = SQLiteSession('/home/alek/.assistant/state/telegram/armen')
    session = StringSession(StringSession.save(source))
    source.close()
    client = TelegramClient(session, int(credentials['TG_API_ID']), credentials['TG_API_HASH'])
    report = {'checks': [], 'created_entries': [], 'cleanup': [], 'owner_restored': False}
    artifacts = Path(os.environ.get('SPUR_SESSION_ARTIFACTS_DIR',str(ROOT/'.data/dev/artifacts'))) / ('dev-live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    artifacts.mkdir(parents=True, exist_ok=True)
    original_owner = config['OWNER_USER_ID']
    switched = False
    db_path = ROOT / config.get('DATABASE_PATH', '.data/nutrition.db')

    def check(name, passed):
        report['checks'].append({'name': name, 'passed': bool(passed)})
        print(name + '=' + ('PASS' if passed else 'FAIL'), flush=True)
        if not passed:
            raise RuntimeError(name)

    async def response(after, prefix, timeout=150):
        prefixes = {'Saved': ('Saved', 'Добавлено:'), 'Corrected:': ('Corrected:', 'Исправлено:'), 'Deleted.': ('Deleted.', 'Запись удалена.'), 'Send a meal': ('Send food', 'Пришли'), 'Today:': ('Today:', 'Сегодня:')}.get(prefix, (prefix,))
        end = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end:
            messages = await client.get_messages(peer, limit=20, min_id=after)
            for message in messages:
                if not message.out and (message.raw_text or '').startswith(prefixes):
                    return message.raw_text
                if not message.out and (message.raw_text or '').startswith(('Could not estimate', 'Не удалось', 'Не могу определить')):
                    raise RuntimeError('analysis_failed')
            await asyncio.sleep(2)
        raise TimeoutError('bot_response_timeout')

    async def command(text, prefix):
        sent = await client.send_message(peer, text)
        return await response(sent.id, prefix, 150)

    def row(entry_id):
        with sqlite3.connect(db_path) as db:
            db.row_factory = sqlite3.Row
            result = db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
            return dict(result) if result else None

    async def saved(sent, name):
        text = await response(sent.id, 'Saved')
        entry_id = int(re.search(r'#(\d+)', text).group(1))
        report['created_entries'].append(entry_id)
        record = row(entry_id)
        check(name, bool(record and record['calories_kcal'] > 0))
        return entry_id

    try:
        await client.connect()
        await client(functions.help.GetConfigRequest())
        check('account_authorized', await client.is_user_authorized())
        me = await client.get_me()
        async with httpx.AsyncClient() as http:
            identity = (await http.post('https://api.telegram.org/bot' + config['TELEGRAM_TOKEN'] + '/getMe')).json()
        peer = await client.get_entity(identity['result']['username'])
        history = await client.get_messages(peer, limit=20)
        report['prior_messages_read'] = len(history)
        allowed = {int(original_owner)} | {int(value.strip()) for value in (config.get('ALLOWED_USER_IDS') or '').split(',') if value.strip()}
        check('test_account_allowlisted', me.id in allowed)
        report['unauthorized_check'] = 'Covered offline; live account is explicitly allowed'
        switched = True
        await asyncio.sleep(4)
        check('start', '/log' in await command('/start', 'Send a meal'))
        check('help', '/today' in await command('/help', 'Send a meal'))
        entry_id = await saved(await client.send_message(peer, 'QA meal: one apple, 180 grams, eaten whole.'), 'text_meal')
        await command(f'/correct {entry_id} QA meal: two apples, 360 grams total.', 'Corrected:')
        check('correction', row(entry_id)['calories_kcal'] > 100)
        check('recent', f'#{entry_id}' in await command('/recent', '#'))
        today_text = await command('/today', 'Today:')
        check('today', 'kcal' in today_text or 'ккал' in today_text)
        image = Image.new('RGB', (1000, 650), 'white')
        draw = ImageDraw.Draw(image)
        draw.multiline_text((40, 40), 'NUTRITION FACTS\nPer serving: 100 g\nCalories: 120 kcal\nProtein: 8 g\nCarbohydrate: 16 g\nFat: 3 g', fill='black', font_size=40, spacing=18)
        label = artifacts / 'test-label.jpg'
        image.save(label)
        await saved(await client.send_file(peer, label, caption='QA meal: ate one 100 g serving; use this label.'), 'label_photo')
        files = await client.send_file(peer, [label, label], caption='QA meal: two photos of the SAME label, not two meals. Ate one serving, 100 g.')
        await saved(files[0], 'album')
        audio = artifacts / 'test-voice.ogg'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'flite=text=I ate one banana weighing one hundred grams.:voice=slt', '-c:a', 'libopus', str(audio)], check=True)
        await saved(await client.send_file(peer, audio, voice_note=True), 'voice')
        await saved(await client.send_file(peer, audio, voice_note=False, caption='QA audio meal'), 'audio')
        if config.get('NOTION_TOKEN') and config.get('NOTION_DATABASE_ID'):
            headers = {'Authorization': 'Bearer ' + config['NOTION_TOKEN'], 'Notion-Version': '2022-06-28'}
            async with httpx.AsyncClient() as http:
                for created in report['created_entries']:
                    record = row(created)
                    check('notion_link_' + str(created), bool(record['notion_page_id']))
                    page = await http.get('https://api.notion.com/v1/pages/' + record['notion_page_id'], headers=headers)
                    check('notion_read_' + str(created), page.status_code == 200 and not page.json().get('archived'))
                    check('notion_fiber_' + str(created), page.json()['properties']['Fiber']['number'] == record['fiber_g'])
    except Exception as error:
        report['error_type'] = type(error).__name__
        print('run_error=' + type(error).__name__, flush=True)
    finally:
        if switched:
            try:
                for entry_id in report['created_entries']:
                    record = row(entry_id)
                    await command(f'/delete {entry_id}', 'Deleted.')
                    cleaned = row(entry_id) is None
                    if record and record.get('notion_page_id'):
                        async with httpx.AsyncClient() as http:
                            page = await http.get('https://api.notion.com/v1/pages/' + record['notion_page_id'], headers={'Authorization': 'Bearer ' + config['NOTION_TOKEN'], 'Notion-Version': '2022-06-28'})
                            cleaned = cleaned and page.status_code == 200 and page.json().get('archived', False)
                    report['cleanup'].append({'entry': entry_id, 'passed': cleaned})
                    print('cleanup_' + str(entry_id) + '=' + str(cleaned), flush=True)
            except Exception as error:
                report['cleanup_error'] = type(error).__name__
            finally:
                current = dotenv_values(ENV)
                report['owner_restored'] = current['OWNER_USER_ID'] == original_owner and current.get('ALLOWED_USER_IDS') == config.get('ALLOWED_USER_IDS')
        await client.disconnect()
        (artifacts / 'report.json').write_text(json.dumps(report, indent=2))
        print('owner_restored=' + str(report['owner_restored']), flush=True)
    return 1 if report.get('error_type') or report.get('cleanup_error') or not all(c['passed'] for c in report['cleanup']) else 0


if __name__ == '__main__':
    if '--run-live' not in sys.argv:
        raise SystemExit('Requires explicit --run-live and account-owner authorization.')
    with live_lock():
        raise SystemExit(asyncio.run(run()))
