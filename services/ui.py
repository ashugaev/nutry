"""English defaults and Russian Telegram interface strings."""
from html import escape

TEXT = {
    'choose_language': ('Choose your language / Выберите язык', 'Выберите язык / Choose your language'),
    'language_saved': ('Language saved: English. Change it anytime with /lang.', 'Язык сохранён: Русский. Изменить его можно командой /lang.'),
    'saved_local': ('Saved locally: {entry}. Do not resubmit this meal.', 'Сохранено локально: {entry}. Не отправляй эту еду повторно.'),
    'help': (
        'Send food text, a photo, or a voice note. Reply to a saved meal to correct it.\n/log description — log food\n/today — daily totals\n/recent — recent entries\n/correct ID description — correction\n/delete ID — delete\n/help — help',
        'Пришли описание еды, фото или голосовое. Чтобы исправить запись, ответь на сообщение с ней — например: «порция была 200 г».\n\n/log описание — добавить еду\n/today — итоги дня\n/recent — последние записи\n/correct ID описание — исправить\n/delete ID — удалить\n/help — помощь'),
    'estimating': ('Estimating…', 'Распознаю еду и считаю…'),
    'saved': ('Saved: {entry}{notes}', 'Добавлено: {entry}{notes}'),
    'corrected': ('Corrected: {entry}', 'Исправлено: {entry}'),
    'deleted': ('Deleted.', 'Запись удалена.'),
    'missing': ('Entry not found; nothing was added.', 'Запись не найдена или уже удалена. Ничего не добавлено.'),
    'empty': ('No entries yet.', 'Пока нет записей. Пришли описание еды или фото.'),
    'today': ('Today: {count} entries\n{totals}', 'Сегодня: {count} записей\n{totals}'),
    'log_usage': ('Usage: /log meal description', 'Напиши, что съел: /log описание еды'),
    'delete_usage': ('Usage: /delete ID', 'Укажи номер записи: /delete 12'),
    'correct_usage': ('Usage: /correct ID corrected meal description', 'Укажи номер и исправление: /correct 12 порция 200 г'),
    'failed': ('Could not estimate this entry. Please try again with portion details.', 'Не удалось обработать сообщение. Попробуй ещё раз, указав блюдо и размер порции.'),
    'sync_failed': (' Saved locally; Notion sync failed.', ' Сохранено в дневнике, но синхронизация с Notion не удалась.'),
}


def text(language, key, **values):
    result = TEXT[key][1 if language.lower() in {'russian', 'ru'} else 0].format(**values)
    if key == 'help':
        result += '\n/lang — язык / language'
    return result


def meal_html(entry, language):
    russian = language.lower() in {'russian', 'ru'}
    unit = 'ккал' if russian else 'kcal'
    protein, fat, carbs, grams = ('Белки', 'Жиры', 'Углеводы', 'г') if russian else ('Protein', 'Fat', 'Carbs', 'g')
    return (f'#{entry.id}\n\n<b>{escape(entry.dish)}</b>\n'
            f'<b>{entry.calories_kcal:.0f} {unit}</b>\n\n'
            f'{protein}: {entry.protein_g:.1f} {grams} · '
            f'{fat}: {entry.fat_g:.1f} {grams} · '
            f'{carbs}: {entry.carbs_g:.1f} {grams}\n'
            + fiber_line(getattr(entry, 'fiber_g', None), language))


def fiber_line(value, language, missing=0):
    russian = language.lower() in {'russian', 'ru'}
    label, grams = ('Клетчатка', 'г') if russian else ('Fiber', 'g')
    amount = '—' if value is None else f'{"≥" if missing else ""}{value:.1f} {grams}'
    note = (f' (нет данных для {missing} записей)' if russian else f' (missing for {missing} entries)') if missing else ''
    return f'{label}: {amount}{note}'


def notes_html(notes):
    return f'\n\n<i>{escape(notes)}</i>' if notes.strip() else ''
