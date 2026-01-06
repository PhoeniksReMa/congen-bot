from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, Order, OrderStatus


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> User:
    res = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = res.scalar_one_or_none()
    if user:
        # обновим данные
        user.username = username
        user.first_name = first_name
        return user

    user = User(
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
    )
    session.add(user)
    await session.flush()
    return user


async def create_order(
    session: AsyncSession,
    user: User,
    chat_id: int,
    mode: str,
    style: str,
    prompt: str,
    model: str,
    price_stars: int,
) -> Order:
    order = Order(
        user_id=user.id,
        chat_id=chat_id,
        mode=mode,
        style=style,
        prompt=prompt,
        model=model,
        price_stars=price_stars,
        status=OrderStatus.DRAFT,
    )
    session.add(order)
    await session.flush()
    return order


async def set_order_invoiced(session: AsyncSession, order: Order, invoice_payload: str) -> None:
    order.invoice_payload = invoice_payload
    order.status = OrderStatus.INVOICED
    await session.flush()


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    res = await session.execute(select(Order).where(Order.id == order_id))
    return res.scalar_one_or_none()


async def mark_paid(
    session: AsyncSession,
    order: Order,
    telegram_payment_charge_id: str | None,
) -> None:
    order.status = OrderStatus.PAID
    order.telegram_payment_charge_id = telegram_payment_charge_id
    order.paid_at = datetime.utcnow()
    await session.flush()


async def mark_submitted(session: AsyncSession, order: Order, task_id: str) -> None:
    order.status = OrderStatus.SUBMITTED
    order.task_id = task_id
    await session.flush()


async def mark_failed(session: AsyncSession, order: Order) -> None:
    order.status = OrderStatus.FAILED
    await session.flush()
