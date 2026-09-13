import logging

import httpx

from services.store import Entry

logger = logging.getLogger(__name__)


class NotionMirror:
    def __init__(self, token: str, database_id: str):
        self.token = token
        self.database_id = database_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.database_id)

    async def add(self, entry: Entry) -> str | None:
        if not self.enabled:
            return None
        headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": "2022-06-28"}
        body = {"parent": {"database_id": self.database_id}, "properties": {
            "Name": {"title": [{"text": {"content": entry.dish}}]},
            "Date": {"date": {"start": entry.created_at}},
            "Calories": {"number": entry.calories_kcal}, "Protein": {"number": entry.protein_g},
            "Carbs": {"number": entry.carbs_g}, "Fat": {"number": entry.fat_g},
            "Fiber": {"number": entry.fiber_g},
            "Source": {"select": {"name": entry.source}},
        }}
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                response = await http.post("https://api.notion.com/v1/pages", headers=headers, json=body)
                response.raise_for_status()
            return response.json()["id"]
        except Exception:
            logger.exception("Notion mirror failed; local entry remains saved")
            return None

    async def update(self, entry: Entry) -> bool:
        if not self.enabled or not entry.notion_page_id:
            return False
        properties = {
            "Name": {"title": [{"text": {"content": entry.dish}}]},
            "Calories": {"number": entry.calories_kcal}, "Protein": {"number": entry.protein_g},
            "Carbs": {"number": entry.carbs_g}, "Fat": {"number": entry.fat_g},
            "Fiber": {"number": entry.fiber_g},
        }
        return await self._patch(entry.notion_page_id, {"properties": properties})

    async def delete(self, entry: Entry) -> bool:
        if not self.enabled or not entry.notion_page_id:
            return False
        return await self._patch(entry.notion_page_id, {"archived": True})

    async def _patch(self, page_id: str, body: dict) -> bool:
        headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": "2022-06-28"}
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                response = await http.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json=body)
                response.raise_for_status()
            return True
        except Exception:
            logger.exception("Notion mirror update failed; local change remains saved")
            return False
