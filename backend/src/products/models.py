import decimal
import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Numeric, Boolean, JSON, CheckConstraint, ForeignKey, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.products.schemas import ProductMeta
from src.shared.schemas import Dimensions
from src.shared.database import Base
from src.shared.mixins import IntIdMixin

if TYPE_CHECKING:
    from src.orders.models import OrderItem


class PromoCode(Base, IntIdMixin):
    __tablename__ = "promocodes"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    max_usages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usages_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    discount_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(discount IS NOT NULL AND discount_percent IS NULL) OR (discount IS NULL AND discount_percent IS NOT NULL)",
            name="ck_promocode_discount_xor"
        ),
    )


class Product(Base, IntIdMixin):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), nullable=True)

    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description_en: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)



    price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    meta: Mapped[Optional[list[ProductMeta]]] = mapped_column(JSON, nullable=True, default=None)
    quantity: Mapped[int] = mapped_column(
        CheckConstraint("quantity >= 0"),
        default=0
    )
    weight: Mapped[int] = mapped_column(CheckConstraint("weight >= 0"), default=1)

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product")
    videos: Mapped[list["ProductVideo"]] = relationship(back_populates="product")

    length: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def volume(self) -> int:
        """Вычисляет объем товара в кубических сантиметрах."""
        return self.length * self.width * self.height

    @property
    def dimensions(self) -> Dimensions:
        """Собирает Pydantic-модель габаритов на лету для интеграции с API."""
        return Dimensions(
            length=self.length,
            width=self.width,
            height=self.height
        )

    @property
    def get_meta(self) -> list[ProductMeta]:
        """Возвращает метаданные в виде списка объектов ProductMeta."""
        if not self.meta:
            return []
        import json
        from src.products.schemas import ProductMeta

        data = self.meta
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                return []

        if not isinstance(data, list):
            return []

        result = []
        for item in data:
            if isinstance(item, dict):
                try:
                    result.append(ProductMeta.model_validate(item))
                except Exception:
                    pass
            elif isinstance(item, ProductMeta):
                result.append(item)
        return result

class ProductImage(Base, IntIdMixin):
    __tablename__ = "product_images"

    path: Mapped[str] = mapped_column(String(128), nullable=False)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    product: Mapped["Product"] = relationship(back_populates="images")


class ProductVideo(Base, IntIdMixin):
    __tablename__ = "product_videos"

    path: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    product: Mapped["Product"] = relationship(back_populates="videos")
