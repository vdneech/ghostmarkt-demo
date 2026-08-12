from pydantic import BaseModel, ConfigDict, EmailStr, Field, PositiveInt
from typing import Optional
from datetime import datetime

from src.auth.models import Locale


class UserResponse(BaseModel):
    id: int = Field(..., description="Уникальный идентификатор пользователя", examples=[1])
    fullname: Optional[str] = Field(None, description="Полное имя пользователя", examples=["Иванов Иван Иванович"])
    email: Optional[EmailStr] = Field(None, description="Email адрес пользователя", examples=["user@example.com"])
    phone: Optional[str] = Field(None, description="Номер телефона в международном формате", examples=["+79991234567"])
    created_at: datetime = Field(..., description="Дата и время создания аккаунта", examples=["2026-07-07T12:00:00Z"])
    telegram_chat_id: Optional[PositiveInt] = Field(None, description="ID чата в Telegram (если привязан)", examples=[123456789])
    username: Optional[str] = Field(None, description="Имя пользователя в Telegram (если привязан)", examples=["telegram_user"])
    specialty: Optional[str] = Field(None, description="Специальность или род деятельности", examples=["Фотограф"])
    is_superuser: bool = Field(..., description="Флаг администратора", examples=[False])
    locale: Locale = Field(default=Locale.RU, description="Пользовательская локаль, код предпочитаемого языка", examples=[Locale.RU])
    first_name: Optional[str] = Field(None, description="Имя пользователя", examples=["Иван"])
    last_name: Optional[str] = Field(None, description="Фамилия пользователя", examples=["Иванов"])
    middle_name: Optional[str] = Field(None, description="Отчество пользователя", examples=["Иванович"])
    source: Optional[str] = Field(None, description="Источник привлечения", examples=["Telegram"])

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="Email адрес пользователя", examples=["user@example.com"])
    first_name: Optional[str] = Field(None, description="Имя пользователя", min_length=2, max_length=50, examples=["Иван"])
    last_name: Optional[str] = Field(None, description="Фамилия пользователя", min_length=2, max_length=50, examples=["Иванов"])
    phone: Optional[str] = Field(None, description="Номер телефона в международном формате", min_length=10, max_length=30, examples=["+79991234567"])
    specialty: Optional[str] = Field(None, description="Специальность или род деятельности", min_length=2, max_length=100, examples=["Фотограф"])
    middle_name: Optional[str] = Field(None, description="Отчество (если есть)", max_length=50, examples=["Иванович"])
    telegram_chat_id: Optional[PositiveInt] = Field(None, description="ID чата в Telegram", examples=[123456789])
    username: Optional[str] = Field(None, description="Имя пользователя в Telegram", examples=["telegram_user"])
    source: Optional[str] = Field(None, description="Источник регистрации", examples=["Telegram"])


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, description="Имя пользователя", min_length=2, max_length=50, examples=["Иван"])
    last_name: Optional[str] = Field(None, description="Фамилия пользователя", min_length=2, max_length=50, examples=["Иванов"])
    phone: Optional[str] = Field(None, description="Номер телефона", min_length=10, max_length=30, examples=["+79991234567"])
    specialty: Optional[str] = Field(None, description="Специальность или род деятельности", min_length=2, max_length=100, examples=["Фотограф"])
    middle_name: Optional[str] = Field(None, description="Отчество", max_length=50, examples=["Иванович"])
    locale: Optional[Locale] = Field(default=Locale.RU, description="Пользовательская локаль", examples=[Locale.RU])
    source: Optional[str] = Field(None, description="Источник регистрации", examples=["Telegram"])


class UserInfoResponse(BaseModel):
    id: int = Field(..., description="Идентификатор пользователя", examples=[1])
    fullname: Optional[str] = Field(None, description="Полное имя", examples=["Иванов Иван Иванович"])
    phone: str = Field(..., description="Номер телефона", examples=["+79991234567"])

    model_config = ConfigDict(from_attributes=True)


class AdminUserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, description="Имя", min_length=2, max_length=50, examples=["Иван"])
    last_name: Optional[str] = Field(None, description="Фамилия", min_length=2, max_length=50, examples=["Иванов"])
    middle_name: Optional[str] = Field(None, description="Отчество", max_length=50, examples=["Иванович"])
    phone: Optional[str] = Field(None, description="Номер телефона", min_length=10, max_length=30, examples=["+79991234567"])
    specialty: Optional[str] = Field(None, description="Специальность", min_length=2, max_length=100, examples=["Фотограф"])
    locale: Optional[Locale] = Field(None, description="Локаль", examples=[Locale.RU])
    is_superuser: Optional[bool] = Field(None, description="Права администратора", examples=[False])
    username: Optional[str] = Field(None, description="Имя в ТГ", examples=["telegram_user"])
    email: Optional[EmailStr] = Field(None, description="Email", examples=["user@example.com"])
    source: Optional[str] = Field(None, description="Источник регистрации", examples=["Telegram"])


class AdminUserReplace(BaseModel):
    first_name: str = Field(..., description="Имя", min_length=2, max_length=50, examples=["Иван"])
    last_name: str = Field(..., description="Фамилия", min_length=2, max_length=50, examples=["Иванов"])
    phone: str = Field(..., description="Номер телефона", min_length=10, max_length=30, examples=["+79991234567"])
    specialty: str = Field(..., description="Специальность", min_length=2, max_length=100, examples=["Фотограф"])
    email: EmailStr = Field(..., description="Email адрес", examples=["user@example.com"])
    is_superuser: bool = Field(default=False, description="Права администратора", examples=[False])
    locale: Locale = Field(default=Locale.RU, description="Локаль", examples=[Locale.RU])
    middle_name: Optional[str] = Field(None, description="Отчество", max_length=50, examples=["Иванович"])
    username: Optional[str] = Field(None, description="Имя в ТГ", examples=["telegram_user"])
    source: Optional[str] = Field(None, description="Источник регистрации", examples=["Telegram"])
