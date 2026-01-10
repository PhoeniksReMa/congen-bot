import os
import re
import logging

import httpx
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.methods import RefundStarPayment

from db.db import SessionLocal, init_db
from db.dao import (
    get_or_create_user,
    create_order,
    set_order_invoiced,
    get_order_by_id,
    mark_paid,
    mark_submitted,
    mark_failed,
    get_state,
    set_state,
    clear_state
)
from db.models import OrderStatus
from bot.buttons import start_menu, generation_song_mode_menu, song_type_menu, main_menu

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aiogram-stars-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MODEL = os.getenv("MODEL", "V4_5ALL")
PRICE_STARS = int(os.getenv("PRICE_STARS", "6"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

STATE: dict[int, dict] = {}


ORDER_PAYLOAD_RE = re.compile(r"^order:(\d+)$")


async def api_generate(payload: dict) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{API_BASE_URL}/music/generate", json=payload)
        if r.status_code == 422:
            log.error("422 from API. Sent payload=%s", payload)
            log.error("422 details=%s", r.text)
        r.raise_for_status()
        return r.json()["taskId"]


@dp.message(Command("start"))
async def start_cmd(message: Message):
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await clear_state(session, user)
        await session.commit()

    await message.answer(
        text='Бот умеет генерировать и редактировать музыку. Выбери действие.',
        reply_markup=start_menu(),
    )
    await  message.answer(
        text='Начать занаво можно нажав "Сбросить" в нижнем меню 👇',
        reply_markup=main_menu(),
    )

@dp.callback_query(F.data.startswith("function:"))
async def function_chosen(callback: CallbackQuery):
    await callback.answer()
    function = callback.data.split(":", 1)[1]

    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        await set_state(session, user, function=function, step="mode")
        await session.commit()

    if function == 'generation_music':
        await callback.message.answer(
            text="Выбери режим: \n\nОбычный - указывается только описание трека, "
                 "по описанию генерируется текст песни и жанры."
                 "\n\nРасширенный - Описываетсся жанр трека, выберается инмтрументальный трек или песня, "
                 "для песни указывается текст.",
            reply_markup=generation_song_mode_menu(),
        )
    elif function == 'edit_music':
        await callback.message.answer(
            text='Функция пока в разработке',
            reply_markup=start_menu(),
        )

@dp.callback_query(F.data.startswith("mode:"))
async def mode_chosen(callback: CallbackQuery):
    await callback.answer()
    mode = callback.data.split(":", 1)[1]

    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        await set_state(session, user, mode=mode, step="instrumental")
        await session.commit()

    await callback.message.answer(
        "Выбери что хочешь получить, мелодию(только музыка, без текста) или песню(с текстом)",
        reply_markup=song_type_menu()
    )

@dp.callback_query(F.data.startswith("instrumental:"))
async def instrumental_chosen(callback: CallbackQuery):
    await callback.answer()
    instrumental = callback.data.split(":", 1)[1] == "true"

    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        st = await get_state(session, user.id)
        mode = st.mode
        await set_state(session, user, instrumental=instrumental, step="style")
        await session.commit()

    if mode == "classic":
        await callback.message.answer(
            text="Опиши стиль трека который хочешь получить. Описывать нужно в свободной форме.",
            parse_mode="Markdown"
        )
    if mode == "custom":
        await callback.message.answer(
            text="Опиши стиль трека который хочешь получить. Описывать нужно в свободной форме на английском языке. например:\n"
                    "Dark ambient techno, 128 BPM, deep drones, industrial textures, distorted kick, no vocals",
            parse_mode="Markdown"
        )

@dp.message(F.text == "❌ Сброс")
async def reset_handler(message: Message):
    # 1) сбрасываем state в БД
    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await clear_state(session, user)
        await session.commit()

    # 2) отвечаем пользователю
    await message.answer(
        "Состояние сброшено. Начнём заново 👌",
        reply_markup=main_menu()
    )

    # 3) можно снова показать стартовое меню
    await message.answer(
        "Выбери действие:",
        reply_markup=start_menu()
    )

@dp.message(F.text)
async def text_flow(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    async with SessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        st = await get_state(session, user.id)
        if not st or not st.step:
            return

        if st.step == "style":
            await set_state(session, user, style=text, step="prompt")
            await session.commit()

            if not st.instrumental and st.mode == "custom":
                await message.answer("2/2) Пришли текст песни (lyrics). Можно с [verse]/[chorus].")
                return

        function = st.function
        mode = st.mode
        style = st.style
        instrumental = st.instrumental
        prompt = text

        order = await create_order(
            session=session,
            user=user,
            chat_id=message.chat.id,
            instrumental=instrumental,
            function=function,
            mode=mode,
            style=style,
            prompt=prompt,
            model=MODEL,
            price_stars=PRICE_STARS,
        )
        invoice_payload = f"order:{order.id}"
        await set_order_invoiced(session, order, invoice_payload)
        await clear_state(session, user)
        await session.commit()

    await message.answer("Ок. Отправляю счёт на оплату ⭐")

    await bot.send_invoice(
        chat_id=message.chat.id,
        title="AI Music Generation",
        description=f"Запуск генерации (Suno). Цена: {PRICE_STARS}⭐",
        payload=invoice_payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{PRICE_STARS} Stars", amount=PRICE_STARS)],
    )


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    sp = message.successful_payment
    m = ORDER_PAYLOAD_RE.match(sp.invoice_payload or "")
    if not m:
        await message.answer("Оплата получена ✅, но payload заказа непонятен. /start")
        return

    order_id = int(m.group(1))

    # 1) Тянем заказ из БД
    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            await message.answer("Оплата получена ✅, но заказ не найден. Напиши /start.")
            return

        # защита от повторной обработки
        if order.status in (OrderStatus.PAID, OrderStatus.SUBMITTED):
            await message.answer("Этот заказ уже оплачен и обрабатывается ✅")
            return

        await mark_paid(session, order, telegram_payment_charge_id=sp.telegram_payment_charge_id)
        await session.commit()

    await message.answer("✅ Оплата получена! Запускаю генерацию…")

    # 2) Запускаем генерацию через твой FastAPI
    try:
        api_payload = {
            "chatId": message.chat.id,
            "userId": message.from_user.id,
            "telegramPaymentChargeId": order.telegram_payment_charge_id,
            "prompt": order.prompt,
            "customMode": True if order == "custom" else False,
            "style": order.style,
            "title": "Paid via Telegram Stars",
            "instrumental": order.instrumental,
            "model": order.model
        }
        task_id = await api_generate(api_payload)

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if order:
                await mark_submitted(session, order, task_id=task_id)
                await session.commit()

        await message.answer(f"🎛 Генерация запущена!\nTaskId: `{task_id}`", parse_mode="Markdown")

    except Exception as e:
        log.exception("generate after payment failed: %s", e)
        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if order:
                await mark_failed(session, order)
                await session.commit()

        await message.answer(
            "⚠️ Оплата прошла, но генерацию запустить не удалось.\n"
            "Заказ помечен как FAILED — можно попробовать повторить админ-командой."
        )
        await bot(RefundStarPayment(
            user_id=order.user_id,
            telegram_payment_charge_id=order.telegram_payment_charge_id,
        ))


async def on_startup(dispatcher: Dispatcher):
    await init_db()

def main():
    dp.startup.register(on_startup)
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
