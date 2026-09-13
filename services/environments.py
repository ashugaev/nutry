"""Explicit DEV configuration with fail-closed production separation."""
from pathlib import Path
from dotenv import dotenv_values


def dev_values(root: Path) -> dict:
    production = {k:v.strip() if isinstance(v,str) else v for k,v in dotenv_values(root/'.env').items()}
    dev = {k:v.strip() if isinstance(v,str) else v for k,v in dotenv_values(root/'.env.dev').items()}
    for key in ('TELEGRAM_TOKEN','NOTION_DATABASE_ID','DATABASE_PATH'):
        if not dev.get(key) or dev[key] == production.get(key):
            raise RuntimeError('DEV must have a distinct '+key)
    if dev['TELEGRAM_TOKEN'].split(':')[0] == production.get('TELEGRAM_TOKEN','').split(':')[0]:
        raise RuntimeError('DEV must use a different bot identity, not a rotated production token')
    if (root/dev['DATABASE_PATH']).resolve() == (root/production.get('DATABASE_PATH','.data/nutrition.db')).resolve():
        raise RuntimeError('DEV database resolves to production')
    if dev['NOTION_DATABASE_ID'].replace('-','').lower() == production.get('NOTION_DATABASE_ID','').replace('-','').lower():
        raise RuntimeError('DEV Notion database matches production')
    if dev.get('MINI_APP_URL') and (dev['MINI_APP_URL'] == production.get('MINI_APP_URL') or
                                  int(dev.get('MINI_APP_PORT','8765')) == int(production.get('MINI_APP_PORT','8765'))):
        raise RuntimeError('DEV web endpoint must be isolated')
    return {key:value for key,value in dev.items() if value is not None}
