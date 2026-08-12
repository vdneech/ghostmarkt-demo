from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import existing_products_kb
from src.products.dao import ProductsDAO
import logging

logger = logging.getLogger(__name__)

router = Router(name="about_router")


def get_about_main_kb() -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру главного меню информационного раздела.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Информация о товаре", callback_data="about_info")],
        [InlineKeyboardButton(text="Примеры фотографий", callback_data="about_photos")]
    ])


def get_about_back_kb() -> InlineKeyboardMarkup:
    """
    Формирует кнопку возврата в предыдущее меню.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="about")]
    ])


@router.callback_query(F.data == "about")
async def redirect_to_about(callback: CallbackQuery):
    """
    Обрабатывает callback-кнопку возврата в главный информационный раздел.
    Перенаправляет вызов на command_about.
    """
    logger.info("Перенаправление в раздел 'О нас' по callback-запросу от чата {}".format(callback.message.chat.id))
    await callback.message.delete()
    await command_about(callback.message)


@router.message(Command("about"))
async def command_about(message: Message):
    """
    Отправляет пользователю приветственное сообщение информационного раздела и клавиатуру меню.
    """
    logger.info("Получена команда /about от чата {}".format(message.chat.id))
    await message.answer(
        text="<b>Добро пожаловать в информационный раздел!</b>\n\n"
             "Здесь вы можете ознакомиться с товаром и посмотреть примеры фотографий.",
        parse_mode="HTML",
        reply_markup=get_about_main_kb()
    )


@router.callback_query(F.data == "about_info")
async def process_about_info(callback: CallbackQuery, session: AsyncSession):
    """
    Получает список активных товаров из БД и выводит клавиатуру для выбора интересующего товара.
    """
    logger.info("Запрос информации о товарах от чата {}".format(callback.message.chat.id))
    await callback.answer()

    products_dao = ProductsDAO(session)
    products = await products_dao.find_all(is_active=True)
    count = len(products)

    keyboard = await existing_products_kb(to_buy=False, products=products)
    text = "Выберите интересующий вас товар" if count else "Доступных товаров пока нет"
    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("about:"))
async def process_product_description(callback: CallbackQuery, session: AsyncSession):
    """
    Выводит детальное описание выбранного товара по его идентификатору.
    """
    await callback.answer()
    product_id = int(callback.data.split(":")[1])
    logger.info("Запрос описания товара ID {} от чата {}".format(product_id, callback.message.chat.id))

    products_dao = ProductsDAO(session)
    product = await products_dao.find_one_or_none_by_id(product_id)

    if not product:
        logger.warning("Товар ID {} не найден при отображении в боте.".format(product_id))
        await callback.message.edit_text(
            "Извините, информация о товаре не найдена.",
            parse_mode="HTML",
            reply_markup=get_about_back_kb()
        )
        return

    await callback.message.edit_text(
        f"<b>{product.name}</b>\n"
        f"{product.description}",
        parse_mode="HTML"
    )
    await callback.message.edit_reply_markup(reply_markup=get_about_back_kb())


@router.callback_query(F.data == "about_photos")
async def process_about_photos(callback: CallbackQuery):
    """
    Показывает ссылки на примеры фотографий с рассеивателем.
    """
    logger.info("Запрос примеров фотографий от чата {}".format(callback.message.chat.id))
    await callback.answer()
    await callback.message.edit_text(
        text="Примеры фотографий\n\n"
             'Ознакомиться с примерами фотографий вы можете в нашем <a href="https://www.instagram.com/ghostmarkt">Instagram</a>',
        parse_mode="HTML",
        reply_markup=get_about_back_kb()
    )
