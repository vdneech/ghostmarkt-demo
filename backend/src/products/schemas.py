from decimal import Decimal
from typing import Optional

import json
from pydantic import BaseModel, Field, ConfigDict, StrictStr, field_validator, AliasChoices

from src.shared.schemas import Locale
from src.shared.schemas import Dimensions

class ProductMeta(BaseModel):
    key: str = Field(
        description="Обязательный уникальный ключ метаданных товара",
        examples=["camera_model", ]
    )
    values: dict[Locale, Optional[str]] = Field(
        description="Человекочитаемые значения ключей, используются для UI пользователя",
        examples=[
            {
                Locale.RU: "Модель камеры",
                Locale.EN: "Camera model",
            }
        ]
    )

class ProductMetaList(BaseModel):
    metas: list[ProductMeta] = Field(description="Список сгенерированных метаданных")

class ProductImageResponse(BaseModel):
    id: int = Field(
        description="Уникальный идентификатор фотографии",
        examples=[1],
    )
    path: str = Field(
        description="Относительный путь к фотографии товара",
        examples=["/media/test_image.png"],
    )

    model_config = ConfigDict(from_attributes=True)


class ProductVideoResponse(BaseModel):
    id: int = Field(
        description="Уникальный идентификатор видео",
        examples=[1],
    )
    path: str = Field(
        description="Относительный путь к видео товара",
        examples=["/media/test_video.mp4"],
    )
    description: Optional[str] = Field(
        default=None,
        description="Краткое описание видео",
        examples=["Распаковка товара"],
    )

    model_config = ConfigDict(from_attributes=True)


class ProductVideoUpdate(BaseModel):
    description: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Обновленное описание видео",
    )


class ProductBase(BaseModel):
    name: str = Field(
        max_length=128,
        description="Полное наименование товара. Должно быть понятным для покупателя (например, бренд, модель, ключевые свойства).",
        examples=["Фотоаппарат"],
    )

    name_en: Optional[str] = Field(
        max_length=128,
        default=None,
        description="Полное наименование товара на английском языке.",
        examples=["Camera"],
    )

    description: str = Field(
        max_length=512,
        description="Подробное текстовое описание товара, его преимуществ и ключевых особенностей.",
        examples=["Полноценное описание товара."]
    )

    description_en: Optional[str] = Field(
        max_length=512,
        default=None,
        description="Подробное текстовое описание товара, его преимуществ и ключевых особенностей на английском языке.",
        examples=["Capture the world through a nostalgic lens with this authentic Vintage Camera. Perfect for photography."]
    )

    price: Decimal = Field(
        gt=0,
        le=99999999.99,
        description="Стоимость товара. Принимается в формате десятичной дроби (максимум 2 знака после запятой). Должна быть строго больше нуля.",
        examples=[Decimal("1000.99")],
    )

    quantity: int = Field(
        ge=0,
        description="Доступное количество товара на складе для продажи. Должно быть больше нуля.",
        examples=[10],
    )
    weight: int = Field(
        ge=0,
        description="Вес товара в граммах. Должен быть больше нуля.",
        examples=[500],
    )
    dimensions: Dimensions = Field(
        description="Габариты товара в сантиметрах. Должны быть больше нуля.",
    )


class ProductCreate(ProductBase):
    meta: Optional[list[StrictStr]] = Field(
        default=None,
        description="Характеристики товара. После обработки запроса возвращается meta на двух языках системы.",
        examples=[["Модель вспышки фотоаппарата", ]]
    )
    is_active: bool = Field(
        description="Флаг видимости товара. Если true, товар сразу публикуется в каталоге и доступен для покупки.",
        examples=[True],
    )


class ProductPartiallyUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=128,
        description="Новое наименование товара",
        examples=["Новое имя товара"],
    )
    description: str | None = Field(
        default=None,
        max_length=512,
        description="Обновленное текстовое описание товара.",
        examples=["Обновленное описание товара."],
    )

    name_en: str | None = Field(
        default=None,
        max_length=128,
        description="Новое наименование товара на английском",
        examples=["New Name of Product"],
    )
    description_en: str | None = Field(
        default=None,
        max_length=512,
        description="Обновленное текстовое описание товара на английском.",
        examples=["Updated English description of the product."],
    )

    price: Decimal | None = Field(
        default=None,
        gt=0,
        le=99999999.99,
        description="Новая стоимость товара (если требуется изменить).",
        examples=[Decimal("1200.50")],
    )

    meta: Optional[list[str]] = Field(
        default=None,
        description="Характеристики товара, опрашиваемые в анкетировании, влияют на метаданные позиции в заказе.",
        examples=["Модель вспышки фотоаппарата"],
    )
    quantity: int | None = Field(
        default=None,
        gt=0,
        description="Актуальное количество товара на складе (например, после инвентаризации).",
        examples=[12],
    )
    is_active: bool | None = Field(
        default=None,
        description="Управление видимостью товара (можно скрыть из каталога, передав false).",
        examples=[False],
    )
    dimensions: Dimensions | None = Field(
        default=None,
        description="Габариты товара в сантиметрах. Должны быть больше нуля.",
    )


class ProductUpdate(ProductBase):
    meta: Optional[list[StrictStr]] = Field(
        default=None,
        description="Характеристики товара...",
        examples=[["Модель вспышки фотоаппарата", ]]
    )
    is_active: bool = Field(
        default=None,
        description="Управление видимостью товара (можно скрыть из каталога, передав false).",
        examples=[True],
    )


class ProductResponse(ProductBase):
    id: int = Field(
        description="Уникальный системный идентификатор (ID) товара в базе данных.",
        examples=[1],
    )

    images: list[ProductImageResponse] = Field(
        description="Доступные фотографии товара",
        default=[],
    )

    videos: list[ProductVideoResponse] = Field(
        description="Доступные видео товара",
        default=[],
    )

    is_active: bool = Field(
        description="Флаг активности товара (доступен ли для покупки)",
        examples=[True],
    )

    meta: Optional[list[ProductMeta]] = Field(default=None, description="Список сгенерированных метаданных", validation_alias=AliasChoices("get_meta", "meta"))

    @field_validator("meta", mode="before")
    @classmethod
    def decode_meta(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                pass
        return v

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    products: list[ProductResponse] = Field(
        description="Список найденных товаров, соответствующих критериям запроса и пагинации."
    )
    total: int = Field(
        description="Общее количество товаров в базе данных, удовлетворяющих фильтрам (используется для построения пагинации на фронтенде).",
        examples=[1],
    )


class ProductAdminResponse(ProductResponse):
    is_active: bool = Field(
        description="Статус активности товара (доступен только для администраторов и менеджеров магазина).",
        examples=[True],
    )


class ProductFilter(BaseModel):
    name: str | None = Field(
        default=None,
        description="Фильтрация по названию товара. Обычно ищет частичное совпадение (LIKE) без учета регистра.",
        examples=["Фотоаппарат"],
    )
    quantity: int | None = Field(
        default=None,
        description="Фильтр для поиска товаров с конкретным количеством на складе.",
        examples=[5],
    )
    is_active: bool | None = Field(
        default=None,
        description="Фильтр по статусу активности: true – только активные, false – только скрытые, null – все товары.",
        examples=[True],
    )

    model_config = ConfigDict(extra="forbid")


import datetime
from pydantic import model_validator

class PromoCodeCreate(BaseModel):
    code: str = Field(..., description="Unique promo code", max_length=64)
    expires_at: Optional[datetime.datetime] = Field(None, description="Expiration time")
    max_usages: Optional[int] = Field(None, description="Max usages limit")
    discount: Optional[Decimal] = Field(None, description="Absolute discount amount")
    discount_percent: Optional[int] = Field(None, description="Discount percentage")

    @model_validator(mode="after")
    def validate_discount_xor(self) -> "PromoCodeCreate":
        has_discount = self.discount is not None
        has_percent = self.discount_percent is not None
        if not (has_discount ^ has_percent):
            raise ValueError("Either discount or discount_percent must be provided, but not both")
        if self.discount is not None and self.discount <= 0:
            raise ValueError("Discount must be greater than 0")
        if self.discount_percent is not None and not (0 < self.discount_percent <= 100):
            raise ValueError("Discount percent must be between 1 and 100")
        if self.max_usages is not None and self.max_usages <= 0:
            raise ValueError("Max usages must be greater than 0")
        return self


class PromoCodeResponse(BaseModel):
    id: int
    code: str
    expires_at: Optional[datetime.datetime]
    max_usages: Optional[int]
    usages_count: int
    discount: Optional[Decimal]
    discount_percent: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class PromoCodeValidateResponse(BaseModel):
    valid: bool
    discount_amount: Decimal
    message: Optional[str] = None