import os
import re
import logging

import httpx
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery

from db import SessionLocal, init_db
from dao import (
    get_or_create_user,
    create_order,
    set_order_invoiced,
    get_order_by_id,
    mark_paid,
    mark_submitted,
    mark_failed,
)
from models import OrderStatus
from messages import START_MESSAGE
from buttons import menu

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
        r.raise_for_status()
        return r.json()["taskId"]


@dp.message(Command("start"))
async def start_cmd(message: Message):
    STATE.pop(message.from_user.id, None)
    await message.answer(
        text=START_MESSAGE,
        reply_markup=menu(),
    )


@dp.callback_query(F.data.startswith("mode:"))
async def mode_chosen(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    mode = callback.data.split(":", 1)[1]

    if mode not in ("song", "instrumental"):
        await callback.message.answer("Не понял режим. /start")
        STATE.pop(user_id, None)
        return

    STATE[user_id] = {"mode": mode, "step": "style", "style": None}
    await callback.message.answer("1/2) Введи жанры (style), например: `dark ambient, techno`", parse_mode="Markdown")


@dp.message(F.text)
async def text_flow(message: Message):
    user_id = message.from_user.id
    st = STATE.get(user_id)
    if not st:
        return

    text = (message.text or "").strip()
    if not text:
        return

    if st["step"] == "style":
        st["style"] = text
        st["step"] = "prompt"
        if st["mode"] == "instrumental":
            await message.answer(
                "2/2) Опиши трек (prompt), например:\n"
                "Dark ambient techno, 128 BPM, deep drones, industrial textures, distorted kick, no vocals"
            )
        else:
            await message.answer("2/2) Пришли текст песни (lyrics). Можно с [verse]/[chorus].")
        return

    if st["step"] == "prompt":
        mode = st["mode"]
        style = st["style"]
        prompt = text

        # 1) Сохраняем пользователя + заказ в БД
        async with SessionLocal() as session:
            user = await get_or_create_user(
                session=session,
                telegram_user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            order = await create_order(
                session=session,
                user=user,
                chat_id=message.chat.id,
                mode=mode,
                style=style,
                prompt=prompt,
                model=MODEL,
                price_stars=PRICE_STARS,
            )
            invoice_payload = f"order:{order.id}"  # гарантированно коротко и валидно
            await set_order_invoiced(session, order, invoice_payload)
            await session.commit()

        # 2) Высылаем инвойс (Stars)
        await message.answer("Ок. Отправляю счёт на оплату ⭐")

        await bot.send_invoice(
            chat_id=message.chat.id,
            title="AI Music Generation",
            description=f"Запуск генерации (Suno). Цена: {PRICE_STARS}⭐",
            payload=invoice_payload,
            provider_token="",     # Stars
            currency="XTR",         # Stars
            prices=[LabeledPrice(label=f"{PRICE_STARS} Stars", amount=PRICE_STARS)],  # для Stars 1 item
        )

        STATE.pop(user_id, None)
        return


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
        instrumental = (order.mode == "instrumental")
        api_payload = {
            "prompt": order.prompt,
            "customMode": True,
            "style": order.style,
            "title": "Paid via Telegram Stars",
            "instrumental": instrumental,
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


async def on_startup(dispatcher: Dispatcher):
    await init_db()

def main():
    dp.startup.register(on_startup)
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
