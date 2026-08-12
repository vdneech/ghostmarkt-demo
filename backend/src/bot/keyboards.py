from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from src.config import settings
from src.products.models import Product


async def existing_products_kb(
    products: list[Product],
    to_buy: bool = False,
    repeat: bool = False
) -> InlineKeyboardMarkup:

    builder = InlineKeyboardBuilder()

    if not products:
        builder.row(
            InlineKeyboardButton(
                text="На главную",
                callback_data="about"
            )
        )
    for product in products:
        callback_data = f"buy:{product.id}" if to_buy else f"about:{product.id}"

        if repeat:
            callback_data = f"repeat:{product.id}"

        builder.row(
            InlineKeyboardButton(
                text=product.name,
                callback_data=callback_data
            )
        )

    return builder.as_markup()


def start_kb() -> InlineKeyboardMarkup:
    """Клавиатура для главного меню (/start)"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text='Оформить заказ',
            callback_data="create_order",
            icon_custom_emoji_id="5258204546391351475",
            style="success",
        ))
    builder.row(
        InlineKeyboardButton(
            text="О нас",
            icon_custom_emoji_id="5258474669769497337",
            style="primary",
            callback_data="about",
        )
    )

    return builder.as_markup()

def widget_kb(product_id: int, chat_id: int = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для перехода в WebApp оформления заказа с привязкой к конкретному товару.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text='Кнопка вебаппа',
            callback_data=f"widget-placeholder:{product_id}"
        )
    )
    return builder.as_markup()

def phone_share_kb() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой шеринга контакта"""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Поделиться контактом", request_contact=True))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def source_suggestions_kb() -> ReplyKeyboardMarkup:
    """Клавиатура с подсказками источников"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="Instagram"),
        KeyboardButton(text="Друзья"),
        KeyboardButton(text="Коллеги")
    )
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def payment_button_kb(pay_url: str, inv_id) -> InlineKeyboardMarkup:
    """Генерирует инлайн-кнопку для перехода на сайт Робокассы"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Оплатить заказ", url=pay_url, style="success"))
    builder.row(InlineKeyboardButton(text="Отменить", callback_data=f"cancel-order:{inv_id}", style="danger"))
    return builder.as_markup()


def policy_agreement_kb() -> InlineKeyboardMarkup:
    """Клавиатура для согласия с политикой конфиденциальности"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Согласен с условиями оферты", callback_data="policy-accepted"))
    builder.row(InlineKeyboardButton(text="Оферта в Google Docs", url="https://example.com"))
    return builder.as_markup()
