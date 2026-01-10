from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def start_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обычный", callback_data="mode:classic")],
        [InlineKeyboardButton(text="Расширенный", callback_data="mode:custom")],
    ])

def song_type_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Инструментал", callback_data="mode:instrumental")],
        [InlineKeyboardButton(text="🎤 Песня", callback_data="mode:song")],
    ])