from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, Order, OrderStatus, State


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> User:
    res = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = res.scalar_one_or_none()
    if user:
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
    function: str,
    instrumental: bool | None,
    mode: str,
    style: str,
    prompt: str,
    model: str,
    price_stars: int,
) -> Order:
    order = Order(
        user_id=user.id,
        chat_id=chat_id,
        function=function,
        instrumental=instrumental,
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


async def get_state(session: AsyncSession, user_id: int) -> State | None:
    return await session.get(State, user_id)

async def get_or_create_state(session: AsyncSession, user: User) -> State:
    st = await session.get(State, user.id)
    if st:
        return st
    st = State(user_id=user.id, step=None)
    session.add(st)
    return st

async def set_state(
    session: AsyncSession,
    user: User,
    *,
    step: str | None = None,
    function: str | None = None,
    mode: str | None = None,
    instrumental: bool | None = None,
    style: str | None = None,
    prompt: str | None = None,
) -> State:
    st = await get_or_create_state(session, user)

    if step is not None:
        st.step = step
    if function is not None:
        st.function = function
    if mode is not None:
        st.mode = mode
    if instrumental is not None:
        st.instrumental = instrumental
    if style is not None:
        st.style = style
    if prompt is not None:
        st.prompt = prompt

    return st

async def clear_state(session: AsyncSession, user: User) -> None:
    st = await session.get(State, user.id)
    if st:
        await session.delete(st)
