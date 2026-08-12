from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr





class Authentication(BaseModel):
    grant_type: str = "client_credentials"
    client_id: str
    client_secret: str


class CDEKAuthorizationToken(BaseModel):
    access_token: str
    token_type: str
    scope: str
    expires_in: int
    jti: str = Field(
        description="Уникальный идентификатор токена"
    )

class Phone(BaseModel):
    number: str = Field(
        description="Номер телефона в международном формате (например, +79991112233)",
        max_length=255
    )
    additional: Optional[str] = Field(
        default=None,
        description="Добавочный номер",
        max_length=255
    )


class Recipient(BaseModel):
    name: str = Field(
        description="Имя получателя"
    )
    phones: Optional[list[Phone]] = Field(
        description="Список телефонов получателя"
    )
    email: Optional[EmailStr] = Field(
        description="Email получателя"
    )

class Payment(BaseModel):
    value: Decimal = Field(
        description="Сумма оплаты в рублях",
        le=50000000,
    )

class Item(BaseModel):
    name: str = Field(
        description="Полное и понятное наименование товара, возмозможно с описанием",
        max_length=255,
    )
    ware_key: str = Field(
        description="Уникальный идентификатор товара в системе магазина",
        max_length=50,
    )
    cost: Decimal = Field(
        description="Стоимость единицы товара в рублях",
        ge=0,
    )
    payment: Payment = Field(
        description="Информация об оплате товара"
    )
    weight: int = Field(
        description="Вес единицы товара в граммах"
    )
    amount: int = Field(
        description="Количество единиц товара в упаковке",
        ge=0,
        le=999,
    )

class Package(BaseModel):
    number: str = Field(
        description="Номер упаковки в заказе"
    )
    weight: int = Field(
        description="Вес посылки в граммах"
    )
    length: int = Field(
        description="Длина коробки в сантиметрах"
    )
    width: int = Field(
        description="Ширина коробки в сантиметрах"
    )
    height: int = Field(
        description="Высота коробки в сантиметрах"
    )
    items: list[Item] = Field(
        description="Список товаров в упаковке"
    )



class CDEKOrderCreate(BaseModel):
    type: int = 1
    number: str = Field(
        description="Номер заказа в системе магазина (уникальный для каждого заказа)"
    )
    tariff_code: int = Field(
        description="Код тарифа доставки в системе CDEK."
    )
    comment: Optional[str] = Field(
        default=None,
        description="Комментарий к заказу, который будет отображаться в системе CDEK.",
        max_length=255,
    )

    shipment_point: str = Field(
        description="Код пункта отправления заказа (ПВЗ) в системе CDEK, если доставка осуществляется через ПВЗ.",
        max_length = 255,
    )

    delivery_point: str = Field(
        description="Код пункта выдачи заказа (ПВЗ) в системе CDEK, если доставка осуществляется через ПВЗ.",
        max_length = 255,
    )
    recipient: Recipient = Field(
        description="Информация о получателе заказа"
    )

    packages: list[Package] = Field(
        description="Список информации по местам (упаковкам). Количество мест в заказе может быть от 1 до 255",
        min_length=1,
        max_length=255,
    )

class CDEKOrderUpdate(BaseModel):
    type: int = 1
    recipient: Recipient = Field(
        description="Информация о получателе заказа"
    )

class CDEKOrderBase(BaseModel):
    uuid: UUID = Field(
        description="Уникальный идентификатор заказа в системе CDEK"
    )
    cdek_number: Optional[Any] = Field(
        default=None,
        description="Уникальный ключ заказа CDEK"
    )


class SellerDto(BaseModel):
    name: Optional[str] = None
    inn: Optional[str] = None
    phone: Optional[str] = None
    ownership_form: Optional[str] = None
    address: Optional[str] = None


class ContactDto(BaseModel):
    name: str
    company: Optional[str] = None
    contragent_type: Optional[str] = None
    email: Optional[EmailStr] = None
    phones: Optional[list[Phone]] = None
    passport_series: Optional[str] = None
    passport_number: Optional[str] = None



class CDEKEntity(BaseModel):
    uuid: Optional[UUID] = None
    cdek_number: Optional[str] = None
    number: Optional[str] = None

    type: Optional[int] = None
    is_return: Optional[bool] = None
    is_reverse: Optional[bool] = None

    tariff_code: Optional[int] = None
    comment: Optional[str] = None
    shipment_point: Optional[str] = None
    delivery_point: Optional[str] = None

    recipient: Optional[ContactDto] = None
    sender: Optional[ContactDto] = None
    seller: Optional[SellerDto] = None

    packages: Optional[list[Package]] = None

    statuses: Optional[list[Any]] = None




class RequestState(str, Enum):
    ACCEPTED = "ACCEPTED"
    WAITING = "WAITING"
    SUCCESSFUL = "SUCCESSFUL"
    INVALID = "INVALID"

class CDEKError(BaseModel):
    code: str
    message: str

class RequestDTO(BaseModel):
    type: str = Field(
        description="Тип запроса (например, 'CREATE_ORDER', 'UPDATE_ORDER', 'RETURN_ORDER')"
    )
    date_time: datetime = Field(
        description="Дата и время создания запроса в формате ISO 8601"
    )
    state: RequestState = Field(
        description="Текущее состояние запроса"
    )
    errors: Optional[list[CDEKError]] = None

class CDEKProxyRequest(BaseModel):
    action: Optional[str] = None
    path: Optional[str] = None
    extra_params: dict = Field(default_factory=dict)

class CDEKOrderResponse(BaseModel):
    entity: CDEKEntity = Field(
        description="Идентификатор сущности в ИС СДЭК"
    )
    requests: list[RequestDTO] = Field(
        description="Список запросов, связанных с созданием заказа"
    )