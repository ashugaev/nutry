import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot import NutritionBot
from services.analyzer import Estimate, NoFoodIdentified
from services.store import NutritionStore
from tests.test_bot import settings, update


class LanguageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name)/'diary.db')
        self.store = NutritionStore(self.path, 'UTC')
        self.analyzer = SimpleNamespace(analyze=AsyncMock(side_effect=NoFoodIdentified))
        self.bot = NutritionBot(replace(settings(), allowed_user_ids=frozenset({7}), response_language='Russian'),
                                store=self.store, analyzer=self.analyzer, notion=SimpleNamespace(enabled=False))
        self.context = SimpleNamespace(args=[], bot=SimpleNamespace(id=999, set_my_commands=AsyncMock(), set_chat_menu_button=AsyncMock()))

    async def test_english_default_and_start_always_offers_choice(self):
        item = update(42, '/start')
        item.effective_user.language_code='ru'
        await self.bot.start(item, self.context)
        reply = item.effective_message.reply_text.await_args
        self.assertTrue(reply.args[0].startswith('Send food'))
        buttons = reply.kwargs['reply_markup'].inline_keyboard[0]
        self.assertEqual([b.callback_data for b in buttons], ['lang:en','lang:ru'])
        self.assertEqual(self.store.get_language(42), 'en')

    async def test_command_persists_across_store_restart_and_accounts(self):
        item = update(42, '/lang ru'); item.callback_query = None
        self.context.args = ['ru']
        await self.bot.lang(item, self.context)
        self.assertIn('Язык сохранён', item.effective_message.reply_text.await_args.args[0])
        self.bot.store = NutritionStore(self.path, 'UTC')
        self.assertEqual(self.bot.store.get_language(42), 'ru')
        self.assertEqual(self.bot.store.get_language(7), 'en')
        await self.bot.start(update(42,'/start'),self.context)
        self.assertEqual(self.bot.store.get_language(42),'ru')
        for user_id, prefix in ((42,'Пришли'), (7,'Send food')):
            item = update(user_id, '/help')
            await self.bot.help(item, self.context)
            self.assertTrue(item.effective_message.reply_text.await_args.args[0].startswith(prefix))

    async def test_callback_switch_and_invalid_command_do_not_corrupt_choice(self):
        item = update(42)
        item.callback_query = SimpleNamespace(data='lang:ru', answer=AsyncMock(), edit_message_text=AsyncMock())
        await self.bot.lang(item, self.context)
        self.assertEqual(self.store.get_language(42), 'ru')
        item.callback_query.answer.assert_awaited_once()
        item.callback_query.data = 'lang:en'
        await self.bot.lang(item, self.context)
        self.assertEqual(self.store.get_language(42), 'en')
        item.callback_query = None; self.context.args=['de']
        await self.bot.lang(item, self.context)
        self.assertEqual(self.store.get_language(42), 'en')
        self.assertIn('Choose', item.effective_message.reply_text.await_args.args[0])
        with self.assertRaises(ValueError):
            self.store.set_language(42,'de')

    async def test_guard_before_preferences_and_callback_answer(self):
        self.store.get_language = Mock(side_effect=AssertionError('guard must run first'))
        for item in (update(8), update(42, chat_type='group')):
            item.callback_query = SimpleNamespace(data='lang:ru', answer=AsyncMock())
            await self.bot.lang(item, self.context)
            item.callback_query.answer.assert_not_awaited()
        self.store.get_language.assert_not_called()

    async def test_concurrent_model_requests_keep_separate_language(self):
        self.store.set_language(42,'ru')
        async def analyze(**kwargs):
            await asyncio.sleep(0)
            raise NoFoodIdentified()
        self.analyzer.analyze.side_effect = analyze
        russian, english = update(42,'hi'), update(7,'hi')
        await asyncio.gather(self.bot.message(russian,self.context), self.bot.message(english,self.context))
        self.assertEqual({call.kwargs['language'] for call in self.analyzer.analyze.await_args_list}, {'English','Russian'})
        self.assertTrue(russian.effective_message.reply_text.return_value.edit_text.await_args.args[0].startswith('Не могу'))
        self.assertTrue(english.effective_message.reply_text.return_value.edit_text.await_args.args[0].startswith('I could not'))
