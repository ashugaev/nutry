import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import NutritionBot
from services.analyzer import Estimate, NoFoodIdentified
from services.store import NutritionStore
from tests.test_bot import settings, update


class ReplyEditTests(unittest.IsolatedAsyncioTestCase):
    async def test_today_fiber_marks_incomplete_history(self):
        self.bot.settings = replace(settings(), response_language='Russian')
        self.store.set_language(42, 'ru')
        self.store.add(replace(self.initial, fiber_g=3.2), 'text')
        self.store.add(self.initial, 'text')
        item = update(42, '/today')
        await self.bot.today(item, self.context)
        message = item.effective_message.reply_text.await_args.args[0]
        self.assertIn('Клетчатка: ≥3.2 г', message)
        self.assertIn('нет данных для 1 записей', message)

    async def test_saved_and_corrected_use_html(self):
        item = update(42, 'rice')
        await self.bot.message(item, self.context)
        status = item.effective_message.reply_text.return_value
        self.assertEqual(status.edit_text.await_args.kwargs['parse_mode'], 'HTML')
        self.assertIn('<b>', status.edit_text.await_args.args[0])
        entry = self.store.recent()[0]
        self.context.args = [str(entry.id), 'rice', '300g']
        corrected = update(42, '/correct')
        await self.bot.correct(corrected, self.context)
        self.assertEqual(corrected.effective_message.reply_text.await_args.kwargs['parse_mode'], 'HTML')

    async def test_stats_button_is_private_and_allowlisted(self):
        self.bot.settings = replace(settings(), mini_app_url='https://example.com', allowed_user_ids=frozenset({7}))
        for user_id in (42, 7):
            item = update(user_id)
            await self.bot.stats(item, self.context)
            keyboard = item.effective_message.reply_text.await_args.kwargs['reply_markup']
            self.assertEqual(keyboard.inline_keyboard[0][0].web_app.url, 'https://example.com')
        for item in (update(8), update(42, chat_type='group')):
            await self.bot.stats(item, self.context)
            item.effective_message.reply_text.assert_not_awaited()
        self.analyzer.analyze.assert_not_awaited()

    async def test_log_command_and_empty_usage(self):
        self.context.args = []
        item = update(42, '/log')
        await self.bot.log(item, self.context)
        self.analyzer.analyze.assert_not_awaited()
        self.context.args = ['rice']
        item.effective_message.text = '/log rice'
        await self.bot.log(item, self.context)
        self.assertEqual(self.analyzer.analyze.await_args.kwargs['text'], 'rice')
        self.assertEqual(len(self.store.recent()), 1)

    async def test_russian_help_and_command_menu(self):
        self.bot.settings = replace(settings(), response_language='Russian')
        self.store.set_language(42, 'ru')
        item = update(42)
        await self.bot.start(item, self.context)
        self.assertIn('Пришли', item.effective_message.reply_text.await_args.args[0])
        app = SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()))
        await self.bot.post_init(app)
        self.assertIn(('log', 'Добавить еду'), app.bot.set_my_commands.await_args.args[0])
    async def test_both_allowed_accounts_private_only(self):
        self.bot.settings = replace(settings(), allowed_user_ids=frozenset({7}))
        self.assertTrue(self.bot.allowed(update(42)))
        self.assertTrue(self.bot.allowed(update(7)))
        self.assertFalse(self.bot.allowed(update(8)))
        self.assertFalse(self.bot.allowed(update(7, chat_type='group')))
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = NutritionStore(str(Path(self.temp.name) / 'diary.db'), 'UTC')
        self.initial = Estimate('Rice 100 g', 130, 3, 28, 1, 'medium', 'Cooked rice')
        self.changed = replace(self.initial, dish='Rice 200 g', calories_kcal=260)
        self.analyzer = SimpleNamespace(analyze=AsyncMock(return_value=self.changed))
        self.notion = SimpleNamespace(enabled=True, add=AsyncMock(return_value='page'), update=AsyncMock(return_value=True))
        self.bot = NutritionBot(settings(), analyzer=self.analyzer, store=self.store, notion=self.notion)
        self.context = SimpleNamespace(bot=SimpleNamespace(id=999))

    def reply(self, target_message=10, target_text='Saved: #1 Rice 100 g: 130 kcal', sender=999):
        item = update(42, 'Actually 200 grams')
        item.effective_message.chat_id = 42
        item.effective_message.reply_to_message = SimpleNamespace(
            message_id=target_message, text=target_text, from_user=SimpleNamespace(id=sender))
        item.effective_message.reply_text.return_value = SimpleNamespace(chat_id=42, message_id=11, edit_text=AsyncMock())
        return item

    async def test_reply_updates_same_entry_and_notion_after_restart(self):
        entry = self.store.add(self.initial, 'text')
        self.store.set_notion_page(entry.id, 'page')
        self.store.link_message(42, 10, entry.id)
        self.bot.store = NutritionStore(self.store.path, 'UTC')
        await self.bot.message(self.reply(), self.context)
        self.assertEqual(len(self.store.recent()), 1)
        self.assertEqual(self.store.get(entry.id).calories_kcal, 260)
        self.assertEqual(self.store.message_entry_id(42, 11), entry.id)
        self.assertIn('Rice 100 g', self.analyzer.analyze.await_args.kwargs['text'])
        self.assertIn('Actually 200 grams', self.analyzer.analyze.await_args.kwargs['text'])
        self.notion.update.assert_awaited_once()
        self.notion.add.assert_not_awaited()

    async def test_old_saved_bot_message_supported(self):
        entry = self.store.add(self.initial, 'text')
        await self.bot.message(self.reply(target_text=f'Saved: #{entry.id} Rice 100 g: 130 kcal'), self.context)
        self.assertEqual(len(self.store.recent()), 1)
        self.assertEqual(self.store.get(entry.id).calories_kcal, 260)

    async def test_deleted_reply_does_not_target_reused_id(self):
        entry = self.store.add(self.initial, 'text')
        self.store.link_message(42, 10, entry.id)
        self.store.delete(entry.id)
        newer = self.store.add(self.initial, 'text')
        await self.bot.message(self.reply(), self.context)
        self.analyzer.analyze.assert_not_awaited()
        self.assertEqual(self.store.get(newer.id).calories_kcal, 130)

    async def test_no_food_reply_preserves_original(self):
        entry = self.store.add(self.initial, 'text')
        self.analyzer.analyze.side_effect = NoFoodIdentified()
        await self.bot.message(self.reply(), self.context)
        self.assertEqual(self.store.get(entry.id).calories_kcal, 130)
        self.notion.update.assert_not_awaited()

    async def test_nonfood_creates_nothing_and_responds_in_russian(self):
        self.bot.settings = replace(settings(), response_language='Russian')
        self.store.set_language(42, 'ru')
        self.analyzer.analyze.side_effect = NoFoodIdentified()
        item = update(42, 'hello')
        status = SimpleNamespace(edit_text=AsyncMock())
        item.effective_message.reply_text.return_value = status
        await self.bot.message(item, self.context)
        self.assertEqual(self.store.recent(), [])
        self.notion.add.assert_not_awaited()
        self.assertIn('Не могу определить', status.edit_text.await_args.args[0])

    async def test_other_sender_text_cannot_select_correction(self):
        self.store.add(self.initial, 'text')
        await self.bot.message(self.reply(sender=55), self.context)
        self.assertEqual(len(self.store.recent()), 2)
