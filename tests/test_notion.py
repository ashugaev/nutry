import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.notion import NotionMirror


class NotionMirrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_includes_fiber(self):
        mirror = NotionMirror('token', 'database')
        entry = SimpleNamespace(dish='Apple', created_at='2026-09-13T12:00:00+00:00',
                                calories_kcal=52, protein_g=.3, carbs_g=14, fat_g=.2,
                                fiber_g=2.4, source='text')
        client = AsyncMock()
        client.post.return_value = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'id':'page'})
        with patch('services.notion.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value = client
            self.assertEqual(await mirror.add(entry), 'page')
        self.assertEqual(client.post.await_args.kwargs['json']['properties']['Fiber'], {'number':2.4})

    async def test_update_and_delete_patch_existing_page(self):
        mirror = NotionMirror("token", "database")
        mirror._patch = AsyncMock(return_value=True)
        entry = SimpleNamespace(
            notion_page_id="page", dish="Soup", calories_kcal=90,
            protein_g=3, carbs_g=12, fat_g=2, fiber_g=1.5,
        )
        self.assertTrue(await mirror.update(entry))
        self.assertEqual(mirror._patch.await_args.args[1]['properties']['Fiber'], {'number': 1.5})
        self.assertTrue(await mirror.delete(entry))
        self.assertEqual(mirror._patch.await_args_list[1].args, ("page", {"archived": True}))

    async def test_disabled_mirror_does_not_call_network(self):
        mirror = NotionMirror("", "")
        with patch("services.notion.httpx.AsyncClient") as client:
            self.assertIsNone(await mirror.add(SimpleNamespace()))
            client.assert_not_called()
