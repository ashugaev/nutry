"""Idempotent, explicit migration of the configured nutrition Notion database."""
import asyncio
import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_settings


async def main():
    logging.disable(logging.CRITICAL)
    settings = load_settings()
    if not settings.notion_token or not settings.notion_database_id:
        print('notion_fiber_schema=DISABLED')
        return
    headers = {'Authorization': 'Bearer '+settings.notion_token, 'Notion-Version': '2022-06-28'}
    url = 'https://api.notion.com/v1/databases/'+settings.notion_database_id
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        properties = response.json()['properties']
        # Refuse unrelated databases or incompatible properties, never overwrite.
        assert all(properties.get(name, {}).get('type') == kind for name, kind in
                   {'Name':'title', 'Calories':'number', 'Protein':'number', 'Carbs':'number', 'Fat':'number'}.items())
        if 'Fiber' not in properties:
            response = await client.patch(url, json={'properties': {'Fiber': {'number': {'format':'number'}}}})
            response.raise_for_status()
            properties = response.json()['properties']
        assert properties['Fiber']['type'] == 'number'
        print('notion_fiber_schema=PASS')


if __name__ == '__main__':
    if '--apply' not in sys.argv:
        raise SystemExit('Requires --apply to migrate the configured nutrition database')
    try:
        asyncio.run(main())
    except Exception as exc:
        print('notion_fiber_schema=FAIL; error_type='+type(exc).__name__)
        raise SystemExit(1) from None
