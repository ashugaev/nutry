import asyncio
import logging
import os
import re
import tempfile
from collections import defaultdict
from contextvars import ContextVar
from functools import wraps

from telegram import Chat, Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, MenuButtonWebApp, BotCommandScopeChat
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, ExtBot, MessageHandler, filters

from config import Settings, load_settings
from services.analyzer import NoFoodIdentified, NutritionAnalyzer
from services.notion import NotionMirror
from services.store import Entry, NutritionStore, totals
from services.ui import text as ui_text, meal_html, notes_html, fiber_line

HELP = """Send a meal description, food photo, nutrition label, image with text, album, voice note, or audio file.
Reply to a saved meal message with your correction to update that entry.

/today — today's totals
/recent — last 10 entries
/correct ID description — re-estimate an entry
/delete ID — delete an entry
/help — this message

Estimates are approximate, not medical advice."""

LANGUAGE = ContextVar('nutrition_request_language', default='English')


def localized(handler):
    """Authorize first and isolate locale across concurrent requests/albums."""
    @wraps(handler)
    async def wrapped(self, update, context):
        if not self.allowed(update):
            return
        code = self.store.get_language(update.effective_user.id)
        token = LANGUAGE.set('Russian' if code == 'ru' else 'English')
        try:
            return await handler(self, update, context)
        finally:
            LANGUAGE.reset(token)
    return wrapped


class ObservedBot(ExtBot):
    async def get_updates(self, *args, **kwargs):
        updates = await super().get_updates(*args, **kwargs)
        logging.info("Telegram polling succeeded; updates=%d", len(updates))
        return updates


async def handle_error(update, context):
    # Exception messages and request URLs can contain credentials.
    logging.error("Telegram operation failed: %s", type(context.error).__name__)


class NutritionBot:
    def __init__(self, settings: Settings, analyzer=None, store=None, notion=None):
        self.settings = settings
        self.analyzer = analyzer or NutritionAnalyzer(
            settings.openai_api_key,
            settings.nutrition_model,
            settings.transcription_model,
            settings.response_language,
        )
        self.store = store or NutritionStore(settings.database_path, settings.timezone)
        self.notion = notion or NotionMirror(settings.notion_token, settings.notion_database_id)
        self.albums: dict[str, list[Update]] = defaultdict(list)
        self.album_tasks: dict[str, asyncio.Task] = {}
        self.dashboard_runner = None

    def text(self, key, **values):
        return ui_text(self.language, key, **values)

    @property
    def language(self):
        return LANGUAGE.get()

    @staticmethod
    def language_keyboard():
        return InlineKeyboardMarkup([[InlineKeyboardButton('English', callback_data='lang:en'),
                                      InlineKeyboardButton('Русский', callback_data='lang:ru')]])

    @staticmethod
    def commands(language):
        ru = language == 'Russian'
        return [('log', 'Добавить еду' if ru else 'Log food'),
                ('stats', 'Калории и статистика' if ru else 'Calories and statistics'),
                ('today', 'Итоги дня' if ru else 'Daily totals'),
                ('recent', 'Последние записи' if ru else 'Recent entries'),
                ('lang', 'Выбрать язык' if ru else 'Choose language'),
                ('help', 'Как пользоваться' if ru else 'Help')]

    async def register_user_menu(self, bot, user_id, language):
        await bot.set_my_commands(self.commands(language), scope=BotCommandScopeChat(user_id))
        if self.settings.mini_app_url:
            await bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonWebApp(
                text='Калории' if language == 'Russian' else 'Calories', web_app=WebAppInfo(self.settings.mini_app_url)))

    @localized
    async def lang(self, update, context):
        query = update.callback_query
        code = query.data.removeprefix('lang:') if query else (context.args[0].lower() if context.args else '')
        if code not in {'en', 'ru'}:
            if query:
                await query.answer()
                return
            await update.effective_message.reply_text(self.text('choose_language'), reply_markup=self.language_keyboard())
            return
        self.store.set_language(update.effective_user.id, code)
        LANGUAGE.set('Russian' if code == 'ru' else 'English')
        if query:
            await query.answer()
        message = self.text('language_saved') + '\n\n' + self.text('help')
        if query:
            await query.edit_message_text(message, reply_markup=self.stats_keyboard())
        else:
            await update.effective_message.reply_text(message, reply_markup=self.stats_keyboard())
        try:
            await self.register_user_menu(context.bot, update.effective_user.id, self.language)
        except Exception:
            logging.warning('Language saved; command menu update deferred until restart')

    async def post_init(self, app):
        await app.bot.set_my_commands(self.commands('English'))
        if self.settings.mini_app_url:
            from services.dashboard import start_dashboard
            self.dashboard_runner = await start_dashboard(self.settings, self.store)
        for user_id in self.settings.allowed_user_ids | {self.settings.owner_user_id}:
            language = 'Russian' if self.store.get_language(user_id) == 'ru' else 'English'
            try:
                await self.register_user_menu(app.bot, user_id, language)
            except Exception:
                logging.warning('Account menu not registered; use /start or /lang')
        logging.info('Telegram command menu registered')

    async def post_shutdown(self, app):
        if self.dashboard_runner is not None:
            await self.dashboard_runner.cleanup()

    def stats_keyboard(self):
        if not self.settings.mini_app_url:
            return None
        russian = self.language == 'Russian'
        return InlineKeyboardMarkup([[InlineKeyboardButton(
            'Калории и статистика' if russian else 'Calories and statistics',
            web_app=WebAppInfo(self.settings.mini_app_url))]])

    @localized
    async def stats(self, update, context):
        if not self.allowed(update):
            return
        keyboard = self.stats_keyboard()
        russian = self.language == 'Russian'
        message = ('Калории за сегодня и история по дням.' if russian else 'Today’s calories and daily history.') if keyboard else ('Статистика пока доступна через /today и /recent.' if russian else 'Use /today and /recent for statistics.')
        await update.effective_message.reply_text(message, reply_markup=keyboard)

    @localized
    async def log(self, update, context):
        if not self.allowed(update):
            return
        if not context.args:
            await update.effective_message.reply_text(self.text('log_usage'))
            return
        await self._process([update], context)

    def allowed(self, update: Update) -> bool:
        user = update.effective_user
        chat = update.effective_chat
        return (
            user is not None
            and chat is not None
            and chat.type == Chat.PRIVATE
            and user.id in (self.settings.allowed_user_ids | {self.settings.owner_user_id})
        )

    def no_food_text(self):
        if self.language == 'Russian':
            return 'Не могу определить блюдо или ингредиенты. Ничего не изменено и не добавлено. Пришли описание еды или более понятное фото.'
        return 'I could not identify a dish or ingredients. Nothing was changed or added. Send a food description or a clearer photo.'

    def link_response(self, message, entry_id):
        if isinstance(getattr(message, 'chat_id', None), int) and isinstance(getattr(message, 'message_id', None), int):
            self.store.link_message(message.chat_id, message.message_id, entry_id)

    def reply_entry_id(self, message, context):
        reply = getattr(message, 'reply_to_message', None)
        if not reply or not reply.from_user or reply.from_user.id != context.bot.id:
            return None
        linked = self.store.message_entry_id(message.chat_id, reply.message_id)
        if linked is not None:
            return linked
        # Support saved bot messages sent before durable message links existed.
        match = re.match(r'^(?:Saved(?: locally)?|Corrected): #([0-9]+) ', reply.text or '')
        return int(match.group(1)) if match else None

    async def estimate_correction(self, entry, text, images=None):
        previous = f'{entry.dish}; {entry.calories_kcal} kcal; protein {entry.protein_g} g; carbs {entry.carbs_g} g; fat {entry.fat_g} g; fiber {entry.fiber_g if entry.fiber_g is not None else "unknown"} g. Notes: {entry.notes}'
        return await self.analyzer.analyze(text=f'Update the existing meal, not an additional meal.\nExisting meal: {previous}\nUser correction: {text}', images=images or [], language=self.language)

    @localized
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(self.text('help')+'\n\n'+self.text('choose_language'), reply_markup=self.language_keyboard())

    @localized
    async def help(self, update, context):
        if self.allowed(update):
            await update.effective_message.reply_text(self.text('help'), reply_markup=self.stats_keyboard())

    @localized
    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        entries = self.store.today()
        kcal, protein, carbs, fat = totals(entries)
        known_fiber = [e.fiber_g for e in entries if e.fiber_g is not None]
        fiber = sum(known_fiber) if known_fiber or not entries else None
        fiber_details = fiber_line(fiber, self.language, len(entries)-len(known_fiber))
        unit, p, c, f, g = ('ккал', 'Б', 'У', 'Ж', 'г') if self.language == 'Russian' else ('kcal','P','C','F','g')
        await update.effective_message.reply_text(
            self.text('today', count=len(entries), totals=f'{kcal:.0f} {unit} · {p} {protein:.1f} {g} · {c} {carbs:.1f} {g} · {f} {fat:.1f} {g}\n{fiber_details}')
        )

    @localized
    async def recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        entries = self.store.recent()
        text = self.text('empty') if not entries else "\n".join(_format_entry(e, self.language) for e in entries)
        await update.effective_message.reply_text(text)

    @localized
    async def delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        try:
            entry_id = int(context.args[0])
        except (IndexError, ValueError):
            await update.effective_message.reply_text(self.text('delete_usage'))
            return
        entry = self.store.get(entry_id)
        if not entry:
            await update.effective_message.reply_text(self.text('missing'))
            return
        synced = await self.notion.delete(entry) if self.notion.enabled and entry.notion_page_id else True
        self.store.delete(entry_id)
        suffix = "" if synced else " Notion sync failed; deleted locally."
        await update.effective_message.reply_text(self.text('deleted') + (self.text('sync_failed') if not synced else ''))

    @localized
    async def correct(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        try:
            entry_id = int(context.args[0])
            text = " ".join(context.args[1:]).strip()
            if not text or not self.store.get(entry_id):
                raise ValueError
        except (IndexError, ValueError):
            await update.effective_message.reply_text(self.text('correct_usage'))
            return
        try:
            estimate = await self.estimate_correction(self.store.get(entry_id), text)
        except NoFoodIdentified:
            await update.effective_message.reply_text(self.no_food_text())
            return
        entry = self.store.correct(entry_id, estimate)
        synced = await self.notion.update(entry) if self.notion.enabled and entry.notion_page_id else True
        suffix = "" if synced else " Notion sync failed; corrected locally."
        sent = await update.effective_message.reply_text(self.text('corrected', entry=meal_html(entry, self.language)) + (self.text('sync_failed') if not synced else ''), parse_mode='HTML')
        self.link_response(sent, entry.id)

    @localized
    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        message = update.effective_message
        if message.media_group_id and message.photo:
            group = message.media_group_id
            self.albums[group].append(update)
            if group not in self.album_tasks:
                self.album_tasks[group] = asyncio.create_task(self._finish_album(group, context))
            return
        await self._process([update], context)

    async def _finish_album(self, group: str, context) -> None:
        await asyncio.sleep(0.8)
        updates = self.albums.pop(group, [])
        self.album_tasks.pop(group, None)
        if updates:
            await self._process(updates, context)

    async def _process(self, updates: list[Update], context) -> None:
        message = updates[0].effective_message
        target_id = self.reply_entry_id(message, context)
        previous = self.store.get(target_id) if target_id is not None else None
        if target_id is not None and previous is None:
            await message.reply_text(self.text('missing'))
            return
        status = await message.reply_text(self.text('estimating'))
        entry = None
        try:
            texts, images, source = [], [], "text"
            for update in updates:
                item = update.effective_message
                if item.caption:
                    texts.append(item.caption)
                if item.text:
                    texts.append(re.sub(r'^/log(?:@\w+)?\s+', '', item.text))
                if item.photo:
                    source = "photo" if len(updates) == 1 else "album"
                    file = await context.bot.get_file(item.photo[-1].file_id)
                    images.append((bytes(await file.download_as_bytearray()), "image/jpeg"))
            audio = message.voice or message.audio
            if audio:
                source = "voice" if message.voice else "audio"
                file = await context.bot.get_file(audio.file_id)
                suffix = os.path.splitext(getattr(file, "file_path", "") or "")[1] or ".ogg"
                with tempfile.NamedTemporaryFile(suffix=suffix) as temp:
                    await file.download_to_drive(temp.name)
                    texts.append(await self.analyzer.transcribe(temp.name))
            if previous is not None:
                estimate = await self.estimate_correction(previous, '\n'.join(texts), images)
                entry = self.store.correct(previous.id, estimate)
                if entry is None:
                    await status.edit_text(self.text('missing'))
                    return
                self.link_response(status, entry.id)
                synced = await self.notion.update(entry) if self.notion.enabled and entry.notion_page_id else True
                suffix = '' if synced else ' Notion sync failed; corrected locally.'
                await status.edit_text(self.text('corrected', entry=meal_html(entry, self.language)) + (self.text('sync_failed') if not synced else ''), parse_mode='HTML')
                return
            estimate = await self.analyzer.analyze(text="\n".join(texts), images=images, language=self.language)
            entry = self.store.add(estimate, source)
            self.link_response(status, entry.id)
            notion_page_id = await self.notion.add(entry)
            if notion_page_id:
                self.store.set_notion_page(entry.id, notion_page_id)
            notion_note = ""
            if self.notion.enabled and not notion_page_id:
                notion_note = "\nSaved locally. Notion sync failed."
            await status.edit_text(
                self.text('saved', entry=meal_html(entry, self.language), notes=notes_html(entry.notes)) + (self.text('sync_failed') if notion_note else ''), parse_mode='HTML'
            )
        except NoFoodIdentified:
            await status.edit_text(self.no_food_text())
        except Exception:
            logging.error("Nutrition processing or delivery failed; locally_saved=%s", entry is not None)
            if entry is not None:
                await message.reply_text(self.text('saved_local', entry=_format_entry(entry, self.language)))
            else:
                await status.edit_text(self.text('failed'))


def _format_entry(entry: Entry, language='English') -> str:
    unit, p, c, f, g = ('ккал', 'Б', 'У', 'Ж', 'г') if language == 'Russian' else ('kcal','P','C','F','g')
    return f"#{entry.id} {entry.dish}: {entry.calories_kcal:.0f} {unit} · {p} {entry.protein_g:.1f} · {c} {entry.carbs_g:.1f} · {f} {entry.fat_g:.1f} {g} · " + fiber_line(getattr(entry, 'fiber_g', None), language)


def build_application(settings: Settings | None = None, service: NutritionBot | None = None):
    settings = settings or load_settings()
    service = service or NutritionBot(settings)
    app = ApplicationBuilder().bot(ObservedBot(settings.telegram_token)).post_init(service.post_init).post_shutdown(service.post_shutdown).build()
    app.add_error_handler(handle_error)
    app.add_handler(CommandHandler('start', service.start))
    app.add_handler(CommandHandler('help', service.help))
    app.add_handler(CommandHandler('lang', service.lang))
    app.add_handler(CallbackQueryHandler(service.lang, pattern=r'^lang:(en|ru)$'))
    app.add_handler(CommandHandler("today", service.today))
    app.add_handler(CommandHandler("stats", service.stats))
    app.add_handler(CommandHandler("day", service.today))
    app.add_handler(CommandHandler("log", service.log))
    app.add_handler(CommandHandler("recent", service.recent))
    app.add_handler(CommandHandler("delete", service.delete))
    app.add_handler(CommandHandler("correct", service.correct))
    accepted = filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO
    app.add_handler(MessageHandler(accepted & ~filters.COMMAND, service.message))
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    build_application().run_polling(allowed_updates=Update.ALL_TYPES, timeout=10)
