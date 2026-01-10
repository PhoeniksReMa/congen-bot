from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Сброс")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выбери действие…",
    )

def start_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Генерация музыки", callback_data="function:generation_music")],
        [InlineKeyboardButton(text="Редактирование музыки", callback_data="function:edit_music")],
    ])

def generation_song_mode_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обычный", callback_data="mode:classic")],
        [InlineKeyboardButton(text="Расширенный", callback_data="mode:custom")],
    ])

def song_type_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Инструментал", callback_data="instrumental:true")],
        [InlineKeyboardButton(text="🎤 Песня", callback_data="instrumental:false")],
    ])