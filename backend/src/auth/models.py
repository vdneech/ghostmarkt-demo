import enum
from datetime import datetime, timezone
from typing import Optional, List
from src.shared.schemas import Locale
from sqlalchemy import BigInteger, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database import Base
from src.shared.mixins import IntIdMixin
from src.orders.models import Order





class User(Base, IntIdMixin):

    __tablename__ = "users"

    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, autoincrement=False, nullable=True, index=True,
                                                  unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email: Mapped[str] = mapped_column(String(64), nullable=True, unique=True, index=True)

    first_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    middle_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_superuser: Mapped[bool] = mapped_column(nullable=False, default=False)
    locale: Mapped[Locale] = mapped_column(nullable=False, default=Locale.RU)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    phone: Mapped[str] = mapped_column(String(20), nullable=True, index=True)

    orders: Mapped[List[Order]] = relationship(back_populates="user")

    @property
    def fullname(self) -> str | None:
        if not self.first_name and not self.last_name:
            return None
        if self.middle_name:
            fullname = f"{self.last_name} {self.first_name} {self.middle_name}"
        if not self.middle_name:
            fullname = f"{self.first_name} {self.last_name}"
        return fullname


