import uuid
from datetime import datetime
from typing import Optional, Any
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.orders.exceptions import MissingDeliveryInfo
from src.orders.models import Delivery
from src.auth.schemas import UserCreate
from src.auth.schemas import UserResponse
from src.orders.models import PaymentStatus

from src.shared.types import Money


class OrderItemBase(BaseModel):
    product_id: int = Field(
        ...,
        gt=0,
        description="Уникальный идентификатор (ID) приобретаемого товара из каталога.",
        examples=[1],
    )
    quantity: int = Field(
        default=1,
        ge=0,
        description="Количество единиц товара в данной позиции заказа. Должно быть больше или равно нулю.",
        examples=[2],
    )
    meta: Optional[dict[str, str]] = Field(
        default=None,
        description="Кастомные характеристики конкретной позиции (например, выбранный цвет, размер или гравировка), заполненные на основе текстового ввода.",
        examples=[{"color": "черный", "size": "XL"}],
    )

    model_config = ConfigDict(from_attributes=True)


class OrderItemCreate(OrderItemBase):
    """Схема для добавления позиций при создании нового заказа."""
    pass


class OrderItemResponse(OrderItemBase):
    """Схема для детального чтения позиций внутри уже существующего заказа."""
    id: int = Field(
        description="Уникальный системный идентификатор (ID) конкретной позиции в таблице элементов заказа.",
        examples=[1],
    )
    order_id: int = Field(
        description="Идентификатор (ID) родительского заказа, к которому относится данная позиция.",
        examples=[10],
    )
    price_at_purchase: Money = Field(
        description="Цена за единицу товара на момент покупки.",
        examples=[Decimal("1500.00")]
    )

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    address: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Физический адрес доставки заказа. Может быть не указан, если подразумевается самовывоз или цифровой товар.",
        examples=["Москва, ул. Ленина, д. 5, кв. 10"],
    )


class OrderCreate(OrderBase):
    """Схема для создания нового заказа через API или Telegram-бота."""
    items: list[OrderItemCreate] = Field(
        ...,
        min_length=1,
        description="Список позиций (товаров), входящих в состав оформляемого заказа. Заказ должен содержать как минимум один товар."
    )
    promo_code: Optional[str] = Field(
        default=None,
        description="Applied promo code",
        examples=["SALE10"]
    )
    discount: Optional[Decimal] = Field(
        default=None,
        description="Discount amount"
    )
    delivery: Optional[Delivery] = Field(
        default=Delivery.CDEK,
        description="Выбранный способ доставки заказа. Если не указан, будет использован способ по умолчанию (CDEK).",
        examples=[Delivery.CDEK],
    )
    tariff_code: Optional[int] = Field(
        default=None,
        description="Код тарифа доставки в системе CDEK. Если не указан, будет использован тариф по умолчанию.",
        examples=[136],
    )
    delivery_point: Optional[str] = Field(
        default=None, 
        description="Код ПВЗ (если выбран ПВЗ)",
        examples=["MSK123"],
    )
    shipment_cost: Optional[Decimal] = Field(
        default=0,
        description="Стоимость доставки, назначенная компанией-доставщиком.",
        examples=[Decimal("350.00")],
    )

    @model_validator(mode='after')
    def validate_shipping_fields(self) -> 'OrderCreate':
        if self.delivery == Delivery.CDEK:
            if self.tariff_code is None:
                raise MissingDeliveryInfo("Для доставки через CDEK необходимо указать tariff_code", missing_fields={"tariff_code"})

            if self.delivery_point is None:
                raise MissingDeliveryInfo("Для доставки через CDEK необходимо указать delivery_point (код ПВЗ)", missing_fields={"delivery_point"})
            if self.shipment_cost is None:
                raise MissingDeliveryInfo(
                    "Для доставки через CDEK необходимо указать delivery_point (код ПВЗ)",
                    missing_fields={"shipment_cost"})
            if self.delivery_point is None:
                raise MissingDeliveryInfo(
                    "Для доставки через CDEK необходимо указать delivery_point (код ПВЗ)",
                    missing_fields={"delivery_point"})
        return self


class UserOrderCreate(OrderCreate):
    """Схема для создания нового заказа через API или Telegram-бота."""
    user: UserCreate


class OrderUpdate(BaseModel):
    """Схема для изменения параметров существующего заказа (все поля опциональны)."""
    payment_status: Optional[PaymentStatus] = Field(
        default=None,
        description="Актуальный статус оплаты заказа (например: PAID, CANCELED, PENDING).",
        examples=[PaymentStatus.PAID],
    )
    payment_date: Optional[datetime] = Field(
        default=None,
        description="Дата и время фактического совершения оплаты. Заполняется автоматически при переходе в статус PAID.",
        examples=["2026-07-07T12:05:00Z"],
    )
    address: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Новый или скорректированный адрес доставки заказа.",
        examples=["Москва, ул. Ленина, д. 5, кв. 10"],
    )
    telegram_message_id: Optional[int] = Field(
        default=None,
        description="Обновленный ID сообщения инвойса в Telegram-боте.",
        examples=[987654321],
    )
    delivery_id: Optional[uuid.UUID] = Field(
        default=None, 
        description="Идентификатор в ИС СДЕК",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    delivery_code: Optional[str] = Field(
        default=None,
        description="Код заказа в ИС доставки (CDEK / Russian Post).",
        examples=["10270717213"],
    )


class OrderResponse(OrderBase):
    """Схема для возврата информации о заказе клиенту (API/Витрина/Бот)."""
    id: int = Field(
        description="Уникальный системный идентификатор (ID) заказа в базе данных.",
        examples=[10],
    )
    promo_code: Optional[str] = Field(
        default=None,
        description="Примененный промокод"
    )
    discount: Optional[Decimal] = Field(
        default=None,
        description="Сумма скидки по промокоду"
    )
    code: str = Field(
        description="Код заказа в формате XXX-XXX",
        examples=["000-014"]
    )
    user: UserResponse | None = Field(
        description="Пользователь, совершивший заказ."
    )

    items: list[OrderItemResponse] = Field(
        description="Позиции в заказе."
    )

    delivery: Optional[Delivery] = Field(
        default=Delivery.CDEK,
        description="Выбранный способ доставки заказа. Если не указан, будет использован способ по умолчанию (CDEK).",
        examples=[Delivery.CDEK],
    )

    total_amount: Money = Field(
        description="Итоговая сумма заказа с учетом цен всех позиций и их количества.",
        examples=[Decimal("4500.00")]
    )
    payment_status: PaymentStatus = Field(
        description="Текущий статус оплаты и обработки заказа.",
        examples=[PaymentStatus.PENDING],
    )
    created_at: datetime = Field(
        description="Дата и время автоматического создания заказа системой.",
        examples=["2026-07-07T12:00:00Z"],
    )
    payment_date: Optional[datetime] = Field(
        default=None,
        description="Дата и время успешной оплаты заказа (null, если заказ еще не оплачен).",
        examples=["2026-07-07T12:05:00Z"],
    )

    payment_url: Optional[str] = Field(
        default=None,
        description="Ссылка для оплаты заказа.",
        examples=["https://auth.robokassa.ru/Merchant/..."],
    )

    shipment_cost: Optional[Decimal] = Field(
        default=0,
        description="Стоимость доставки, назначенная компанией-доставщиком.",
        examples=[Decimal("350.00")],
    )

    delivery_code: Optional[Any] = Field(
        default=None,
        description="Код заказа в ИС доставки.",
        examples=["10270717213"],
    )

    model_config = ConfigDict(from_attributes=True)


class ProductTranslation(BaseModel):
    name: str = Field(..., description="Название товара на английском языке", examples=["Flashlight"])
    description: str = Field(..., description="Описание товара на английском языке", examples=["Compact flash for cameras"])