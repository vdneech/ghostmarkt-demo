import enum
import uuid
from typing import Optional, TYPE_CHECKING
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    BigInteger,
    ForeignKey,
    Enum,
    UUID,
    JSON,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database import Base

if TYPE_CHECKING:
    from src.auth.models import User

from src.products.models import Product


class PaymentStatus(enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class Delivery(enum.Enum):
    CDEK = "CDEK"
    RUSSIAN_POST = "RUSSIAN_POST"
    URBAN = "URBAN"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False), nullable=False, default=PaymentStatus.PENDING, index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payment_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    
    promo_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    discount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    
    delivery: Mapped[Delivery] = mapped_column(
        Enum(Delivery, native_enum=False), nullable=False, default=Delivery.CDEK
    )
    delivery_point: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tariff_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    delivery_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    delivery_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipment_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    @property
    def code(self) -> str:
        if self.id is None:
            return ""
        return f"{self.id // 1000:03d}-{self.id % 1000:03d}"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    price_at_purchase: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")
