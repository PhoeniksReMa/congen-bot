import enum
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"         # собрали данные, ещё не оплатили
    INVOICED = "INVOICED"   # отправили инвойс
    PAID = "PAID"           # оплатили
    SUBMITTED = "SUBMITTED" # отправили на генерацию, получили task_id
    FAILED = "FAILED"       # не смогли отправить/ошибка


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[int] = mapped_column(Integer)  # куда слать сообщения/инвойсы

    mode: Mapped[str] = mapped_column(String(32))          # "song" | "instrumental"
    style: Mapped[str] = mapped_column(String(1000))
    prompt: Mapped[str] = mapped_column(Text)

    model: Mapped[str] = mapped_column(String(32), default="V4_5ALL")

    price_stars: Mapped[int] = mapped_column(Integer, default=6)
    currency: Mapped[str] = mapped_column(String(8), default="XTR")

    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.DRAFT)

    invoice_payload: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="orders")
