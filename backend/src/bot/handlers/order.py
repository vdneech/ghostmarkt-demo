from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards
from src.bot.keyboards import existing_products_kb, policy_agreement_kb
import logging

logger = logging.getLogger(__name__)
from src.config import settings
from src.products.dao import ProductsDAO

router = Router(name="order_router")


@router.callback_query(F.data == "create_order")
async def accept_policy(callback: CallbackQuery):
    """
    Высылает пользователю публичную оферту и запрашивает согласие с ее условиями.
    """
    logger.info("Запрос оферты пользователем {}".format(callback.from_user.id))
    await callback.answer()

    first_name = callback.from_user.first_name or "Покупатель"
    await callback.message.edit_text(
        text=f'{first_name}, перед оформлением заказа, пожалуйста, ознакомьтесь с нашей <a href="{settings.legal.offer_url}"> публичной офертой</a> и подтвердите согласие с ее условиями.',
    )
    await callback.message.edit_reply_markup(reply_markup=policy_agreement_kb())


@router.callback_query(F.data == "policy-accepted")
async def choose_product(callback: CallbackQuery, products_dao: ProductsDAO):
    """
    Показывает пользователю список доступных товаров после подтверждения согласия с офертой.
    """
    logger.info("Пользователь {} согласился с офертой".format(callback.from_user.id))
    await callback.answer()

    products = await products_dao.find_all(is_active=True)
    count = len(products)

    keyboard = await existing_products_kb(to_buy=True, repeat=False, products=products)
    text = "Выберите интересующий вас товар" if count else "Доступных товаров пока нет"
    await callback.message.edit_text(text=text)
    await callback.message.edit_reply_markup(reply_markup=keyboard)


@router.callback_query(F.data.startswith("buy:"))
async def process_buy_product(callback: CallbackQuery, session: AsyncSession):
    """Обрабатывает выбор товара для покупки."""
    product_id = int(callback.data.split(":")[1])
    logger.info("Пользователь {} выбрал товар {} для покупки.".format(callback.from_user.id, product_id))
    await callback.answer()

    await callback.message.edit_reply_markup(reply_markup=None)

    from src.auth.dao import UsersDAO
    users_dao = UsersDAO(session)
    user = await users_dao.find_one_or_none_by_telegram_chat_id(callback.from_user.id)

    if user and user.email:
        await callback.message.edit_text(
            text='Для оформления заказа нажмите на кнопку «Оформить через виджет» ниже',
            parse_mode="HTML",
            reply_markup=keyboards.widget_kb(product_id, callback.from_user.id)
        )
    else:
        from src.shared.redis import get_redis_client
        from src.config import settings
        redis_client = await get_redis_client(database=settings.redis.databases.otp)
        await redis_client.set(f"tg_email_state:{callback.from_user.id}", str(product_id), ex=3600)

        await callback.message.edit_text(
            text="Для заказа нам необходима ваша почта. Введите ее, чтобы мы смогли Вас идентифицировать."
        )
