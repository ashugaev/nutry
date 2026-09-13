import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot import NutritionBot, ObservedBot, handle_error
from config import Settings


def settings():
    return Settings("token", "key", 42, "model", "audio", "UTC", ":memory:", "English", "", "")


def update(user_id, text="meal", chat_type="private"):
    message = SimpleNamespace(
        text=text, caption=None, photo=None, voice=None, audio=None, media_group_id=None,
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type=chat_type),
        effective_message=message,
    )


def estimate():
    return SimpleNamespace(
        dish="Meal", calories_kcal=100, protein_g=2, carbs_g=10, fat_g=5,
        confidence="medium", notes="estimate",
    )


def entry(source):
    return SimpleNamespace(
        id=3, dish="Meal", calories_kcal=100, protein_g=2, carbs_g=10, fat_g=5,
        confidence="medium", notes="estimate", source=source,
    )


def authorized_service():
    analyzer = SimpleNamespace(analyze=AsyncMock(return_value=estimate()), transcribe=AsyncMock(return_value="spoken meal"))
    store = SimpleNamespace(add=Mock(side_effect=lambda _estimate, source: entry(source)), set_notion_page=Mock(), get_language=Mock(return_value='en'))
    notion = SimpleNamespace(enabled=False, add=AsyncMock(return_value=None))
    return NutritionBot(settings(), analyzer=analyzer, store=store, notion=notion), analyzer, store


class BotGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_success_means_completed_request(self):
        with patch("telegram.ext.ExtBot.get_updates", new=AsyncMock(return_value=[])) as request:
            client = ObservedBot("123:fake")
            with self.assertLogs(level="INFO") as logs:
                self.assertEqual(await client.get_updates(timeout=10), [])
            request.assert_awaited_once_with(timeout=10)
            self.assertIn("polling succeeded", logs.output[0])

    async def test_error_log_excludes_exception_credentials(self):
        with self.assertLogs(level="ERROR") as logs:
            await handle_error(None, SimpleNamespace(error=RuntimeError("sensitive-url")))
        self.assertNotIn("sensitive-url", str(logs.output))

    async def test_unexpected_mirror_exception_preserves_local_success(self):
        service, analyzer, store = authorized_service()
        service.notion.add.side_effect = RuntimeError("offline")
        item = update(42)
        item.effective_message.reply_text.return_value = SimpleNamespace(edit_text=AsyncMock())
        with self.assertLogs(level="ERROR"):
            await service.message(item, SimpleNamespace(bot=Mock()))
        store.add.assert_called_once()
        self.assertIn("Saved locally", item.effective_message.reply_text.await_args.args[0])

    def test_constructor_passes_response_language_to_analyzer(self):
        configured = settings()
        with (
            patch("bot.NutritionAnalyzer") as analyzer,
            patch("bot.NutritionStore"),
            patch("bot.NotionMirror"),
        ):
            NutritionBot(configured)
        analyzer.assert_called_once_with("key", "model", "audio", "English")

    async def test_guard_blocks_before_provider_and_storage(self):
        analyzer = SimpleNamespace(analyze=AsyncMock(), transcribe=AsyncMock())
        store = Mock()
        notion = SimpleNamespace(add=AsyncMock())
        service = NutritionBot(settings(), analyzer=analyzer, store=store, notion=notion)
        item = update(7)
        await service.message(item, SimpleNamespace(bot=Mock()))
        analyzer.analyze.assert_not_awaited()
        analyzer.transcribe.assert_not_awaited()
        store.add.assert_not_called()
        notion.add.assert_not_awaited()
        item.effective_message.reply_text.assert_not_awaited()

    async def test_guard_blocks_command(self):
        service = NutritionBot(settings(), analyzer=Mock(), store=Mock(), notion=Mock())
        item = update(7)
        await service.today(item, SimpleNamespace())
        service.store.today.assert_not_called()
        item.effective_message.reply_text.assert_not_awaited()

    async def test_guard_blocks_owner_in_group(self):
        analyzer = SimpleNamespace(analyze=AsyncMock(), transcribe=AsyncMock())
        service = NutritionBot(settings(), analyzer=analyzer, store=Mock(), notion=Mock())
        item = update(42, chat_type="group")
        await service.message(item, SimpleNamespace(bot=Mock()))
        analyzer.analyze.assert_not_awaited()
        item.effective_message.reply_text.assert_not_awaited()

    async def test_notion_failure_reports_local_save(self):
        estimate = SimpleNamespace(
            dish="Meal", calories_kcal=100, protein_g=2, carbs_g=10, fat_g=5,
            confidence="medium", notes="estimate",
        )
        analyzer = SimpleNamespace(analyze=AsyncMock(return_value=estimate), transcribe=AsyncMock())
        entry = SimpleNamespace(id=3, dish="Meal", calories_kcal=100, protein_g=2,
                                carbs_g=10, fat_g=5, confidence="medium", notes="estimate")
        store = SimpleNamespace(add=Mock(return_value=entry), set_notion_page=Mock(), get_language=Mock(return_value='en'))
        notion = SimpleNamespace(enabled=True, add=AsyncMock(return_value=None))
        service = NutritionBot(settings(), analyzer=analyzer, store=store, notion=notion)
        item = update(42)
        status = SimpleNamespace(edit_text=AsyncMock())
        item.effective_message.reply_text.return_value = status
        await service.message(item, SimpleNamespace(bot=Mock()))
        self.assertIn("Saved locally", status.edit_text.await_args.args[0])
        self.assertNotIn("Could not estimate", status.edit_text.await_args.args[0])

    async def test_authorized_text_handler_flow(self):
        service, analyzer, store = authorized_service()
        item = update(42, "rice and chicken")
        item.effective_message.reply_text.return_value = SimpleNamespace(edit_text=AsyncMock())
        await service.message(item, SimpleNamespace(bot=Mock()))
        analyzer.analyze.assert_awaited_once_with(text="rice and chicken", images=[], language='English')
        self.assertEqual(store.add.call_args.args[1], "text")

    async def test_authorized_photo_handler_flow(self):
        service, analyzer, store = authorized_service()
        item = update(42, None)
        item.effective_message.caption = "nutrition label"
        item.effective_message.photo = [SimpleNamespace(file_id="photo")]
        item.effective_message.reply_text.return_value = SimpleNamespace(edit_text=AsyncMock())
        telegram_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"jpg")))
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=telegram_file)))
        await service.message(item, context)
        self.assertEqual(analyzer.analyze.await_args.kwargs["images"], [(b"jpg", "image/jpeg")])
        self.assertEqual(store.add.call_args.args[1], "photo")

    async def test_authorized_album_handler_flow(self):
        service, analyzer, store = authorized_service()
        first = update(42, None)
        second = update(42, None)
        for index, item in enumerate((first, second), 1):
            item.effective_message.caption = "meal" if index == 1 else None
            item.effective_message.photo = [SimpleNamespace(file_id=f"photo-{index}")]
            item.effective_message.media_group_id = "album"
            item.effective_message.reply_text.return_value = SimpleNamespace(edit_text=AsyncMock())
        telegram_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"jpg")))
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=telegram_file)))
        release = __import__("asyncio").Event()

        async def wait_for_album(_seconds):
            await release.wait()

        with patch("bot.asyncio.sleep", side_effect=wait_for_album):
            await service.message(first, context)
            task = service.album_tasks["album"]
            await service.message(second, context)
            release.set()
            await task
        self.assertEqual(len(analyzer.analyze.await_args.kwargs["images"]), 2)
        self.assertEqual(store.add.call_args.args[1], "album")

    async def test_authorized_voice_handler_flow(self):
        service, analyzer, store = authorized_service()
        item = update(42, None)
        item.effective_message.voice = SimpleNamespace(file_id="voice")
        item.effective_message.reply_text.return_value = SimpleNamespace(edit_text=AsyncMock())
        telegram_file = SimpleNamespace(file_path="voice.ogg", download_to_drive=AsyncMock())
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=telegram_file)))
        await service.message(item, context)
        analyzer.transcribe.assert_awaited_once()
        analyzer.analyze.assert_awaited_once_with(text="spoken meal", images=[], language='English')
        self.assertEqual(store.add.call_args.args[1], "voice")
