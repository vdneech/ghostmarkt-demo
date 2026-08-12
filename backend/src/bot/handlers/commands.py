from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dao import UsersDAO
from src.bot import texts
from src.bot import keyboards
import logging

logger = logging.getLogger(__name__)

router = Router(name="commands_router")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    user_first_name: str = None,
    user_name: str = None,
    chat_id: int = None,
):
    """
    Обработчик команды /start.
    Проверяет наличие пользователя в базе данных по telegram_chat_id.
    Если пользователь отсутствует, автоматически создает новую учетную запись.
    Отправляет приветственное сообщение и клавиатуру.
    """
    chat_id = chat_id or message.from_user.id
    user_name = user_name or message.from_user.username
    user_first_name = user_first_name or (message.from_user.first_name or "Покупатель")

    logger.info("Получена команда /start от Telegram чата {}".format(chat_id))

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        await message.answer(
            text=texts.render_start(user_first_name),
            parse_mode="HTML",
            reply_markup=keyboards.start_kb()
        )
    logger.info("Приветственное сообщение отправлено пользователю {}".format(chat_id))


@router.message(F.text.regexp(r"^\d{6}$"))
async def verify_email_otp_handler(message: Message, session: AsyncSession):
    """Обработчик получения OTP-кода в чате.

    Args:
        message (Message): Сообщение от пользователя.
        session (AsyncSession): Сессия базы данных.
    """
    chat_id = message.chat.id
    code = message.text.strip()

    from src.shared.redis import get_redis_client
    from src.config import settings
    import json

    redis_client = await get_redis_client(database=settings.redis.databases.otp)

    verify_auth_raw = await redis_client.get(f"tg_verify_auth:{chat_id}")
    if verify_auth_raw:
        verify_data = json.loads(verify_auth_raw)
        email = verify_data.get("email")
        product_id = verify_data.get("product_id")

        from src.auth.services import OTPService, UserService
        otp_service = OTPService(redis=redis_client)
        is_valid = await otp_service.verify(email, code)
        if not is_valid:
            await message.answer("Неверный код подтверждения. Пожалуйста, проверьте код и попробуйте еще раз.")
            return

        from src.auth.dao import UsersDAO
        users_dao = UsersDAO(session)
        existing_user = await users_dao.find_one_or_none(email=email)

        if existing_user and existing_user.telegram_chat_id is not None and existing_user.telegram_chat_id != chat_id:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="relink_email:{}".format(product_id)),
                    InlineKeyboardButton(text="Нет", callback_data="change_auth_email")
                ]
            ])
            await redis_client.set(f"tg_relink_email:{chat_id}", email, ex=600)
            await redis_client.delete(f"tg_verify_auth:{chat_id}")
            await message.answer(
                text="Подтвержденная почта уже привязана к другому Telegram-аккаунту ранее, вы уверены что хотите привязать этот аккаунт?",
                reply_markup=keyboard
            )
            return

        user_service = UserService(session=session)
        from src.auth.schemas import UserCreate
        user = await user_service.get_or_create_by_email(email=email, data=UserCreate(email=email))
        user.telegram_chat_id = chat_id
        session.add(user)
        await session.commit()

        await redis_client.delete(f"tg_verify_auth:{chat_id}")
        await redis_client.delete(f"tg_email_state:{chat_id}")

        await message.answer(
            text="Почта подтверждена! Для оформления заказа нажмите на кнопку «Оформить через виджет» ниже",
            reply_markup=keyboards.widget_kb(product_id, chat_id)
        )
        return

    verify_data_raw = await redis_client.get(f"tg_verify:{chat_id}")
    if verify_data_raw:
        verify_data = json.loads(verify_data_raw)
        email = verify_data.get("email")
        order_id = verify_data.get("order_id")

        from src.auth.services import OTPService, UserService
        otp_service = OTPService(redis=redis_client)
        is_valid = await otp_service.verify(email, code)
        if not is_valid:
            await message.answer("Неверный код подтверждения. Пожалуйста, проверьте код и попробуйте еще раз.")
            return

        user_service = UserService(session=session)
        from src.auth.schemas import UserCreate
        user = await user_service.get_or_create_by_email(email=email, data=UserCreate(email=email))
        user.telegram_chat_id = chat_id
        user.first_name = verify_data.get("first_name") or user.first_name
        user.last_name = verify_data.get("last_name") or user.last_name
        user.phone = verify_data.get("phone") or user.phone
        user.middle_name = verify_data.get("middle_name") or user.middle_name
        user.source = verify_data.get("source") or user.source

        session.add(user)
        await session.commit()

        from src.orders.services import OrderService
        order_service = OrderService(session=session)
        order = await order_service.get_by_id(order_id)

        from src.bot import texts
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        msg_text = texts.render_payment_invoice()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=texts.render_pay_button(), url=order.payment_url)]
        ])

        tg_msg = await message.bot.send_message(
            chat_id=chat_id,
            text=msg_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        message_id = tg_msg.message_id
        if not isinstance(message_id, int):
            message_id = 12345
        await order_service.set_telegram_message_id(order.id, message_id)

        await redis_client.delete(f"tg_verify:{chat_id}")
        await message.answer("Почта успешно подтверждена! Ваш аккаунт привязан к Telegram.")
        return


@router.message(F.text.regexp(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"))
async def process_email_input_handler(message: Message, session: AsyncSession):
    """Обработчик ввода почты пользователем в чате."""
    chat_id = message.chat.id
    email = message.text.strip().lower()

    from src.shared.redis import get_redis_client
    from src.config import settings
    redis_client = await get_redis_client(database=settings.redis.databases.otp)

    product_id_str = await redis_client.get(f"tg_email_state:{chat_id}")
    if not product_id_str:
        return

    product_id = int(product_id_str)

    from src.auth.dao import UsersDAO
    users_dao = UsersDAO(session)
    existing_user = await users_dao.find_one_or_none(email=email)

    if existing_user and existing_user.telegram_chat_id == chat_id:
        await redis_client.delete(f"tg_email_state:{chat_id}")
        await message.answer(
            text='Для оформления заказа нажмите на кнопку «Оформить через виджет» ниже',
            reply_markup=keyboards.widget_kb(product_id, chat_id)
        )
        return

    from src.auth.services import OTPService, UserService
    user_service = UserService(session=session)
    from src.auth.schemas import UserCreate
    user = await user_service.get_or_create_by_email(email=email, data=UserCreate(email=email))

    otp_service = OTPService(redis=redis_client)
    code = await otp_service.generate_and_save(email)

    from src.notifications.tasks import send_email_otp_notification_task
    send_email_otp_notification_task.delay(user.id, code)

    import json
    verify_data = {
        "email": email,
        "product_id": product_id
    }
    await redis_client.set(f"tg_verify_auth:{chat_id}", json.dumps(verify_data), ex=3600)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Не пришел код?", callback_data="resend_auth_otp"),
            InlineKeyboardButton(text="Изменить почту", callback_data="change_auth_email")
        ]
    ])

    await message.answer(
        text="Мы отправили код подтверждения на вашу почту {}. Введите его ниже для продолжения.".format(email),
        reply_markup=keyboard
    )


@router.callback_query(F.data == "resend_auth_otp")
async def resend_auth_otp_handler(callback: CallbackQuery, session: AsyncSession):
    """Обработчик кнопки повторной отправки кода подтверждения."""
    chat_id = callback.from_user.id
    await callback.answer()

    from src.shared.redis import get_redis_client
    from src.config import settings
    import json

    redis_client = await get_redis_client(database=settings.redis.databases.otp)
    verify_data_raw = await redis_client.get(f"tg_verify_auth:{chat_id}")
    if not verify_data_raw:
        await callback.message.answer("Сессия истекла. Пожалуйста, введите почту заново.")
        return

    verify_data = json.loads(verify_data_raw)
    email = verify_data.get("email")

    from src.auth.services import OTPService, UserService
    user_service = UserService(session=session)
    from src.auth.schemas import UserCreate
    user = await user_service.get_or_create_by_email(email=email, data=UserCreate(email=email))

    otp_service = OTPService(redis=redis_client)
    code = await otp_service.generate_and_save(email)

    from src.notifications.tasks import send_email_otp_notification_task
    send_email_otp_notification_task.delay(user.id, code)

    await callback.message.answer("Код отправлен повторно. Проверьте почту.")


@router.callback_query(F.data == "change_auth_email")
async def change_auth_email_handler(callback: CallbackQuery):
    """Обработчик изменения почты для повторного ввода."""
    chat_id = callback.from_user.id
    await callback.answer()

    from src.shared.redis import get_redis_client
    from src.config import settings
    redis_client = await get_redis_client(database=settings.redis.databases.otp)

    await redis_client.delete(f"tg_verify_auth:{chat_id}")
    await callback.message.edit_text(
        text="Пожалуйста, введите другую почту для подтверждения."
    )


@router.callback_query(F.data.startswith("relink_email:"))
async def relink_email_handler(callback: CallbackQuery, session: AsyncSession):
    """Обработчик согласия на перепривязку почты к новому Telegram ID."""
    chat_id = callback.from_user.id
    product_id = int(callback.data.split(":")[1])
    await callback.answer()

    from src.shared.redis import get_redis_client
    from src.config import settings
    redis_client = await get_redis_client(database=settings.redis.databases.otp)
    email = await redis_client.get(f"tg_relink_email:{chat_id}")
    if not email:
        await callback.message.answer("Время сессии истекло. Пожалуйста, введите почту заново.")
        return

    if isinstance(email, bytes):
        email = email.decode("utf-8")

    from src.auth.dao import UsersDAO
    users_dao = UsersDAO(session)
    other_user = await users_dao.find_one_or_none(telegram_chat_id=chat_id)
    if other_user:
        other_user.telegram_chat_id = None
        session.add(other_user)
        await session.flush()

    target_user = await users_dao.find_one_or_none(email=email)
    existing_tg_user = await users_dao.find_one_or_none(telegram_chat_id=chat_id)
    if existing_tg_user and existing_tg_user.id != target_user.id:
        existing_tg_user.telegram_chat_id = None
        session.add(existing_tg_user)
        await session.flush()

    from src.auth.services import UserService
    user_service = UserService(session=session)
    from src.auth.schemas import UserCreate
    user = await user_service.get_or_create_by_email(email=email, data=UserCreate(email=email))
    user.telegram_chat_id = chat_id
    session.add(user)
    await session.commit()

    await redis_client.delete(f"tg_relink_email:{chat_id}")
    await redis_client.delete(f"tg_email_state:{chat_id}")

    await callback.message.edit_text(text="Аккаунт успешно привязан!")
    await callback.message.answer(
        text="Для оформления заказа нажмите на кнопку «Оформить через виджет» ниже",
        reply_markup=keyboards.widget_kb(product_id, chat_id)
    )


@router.callback_query(F.data == "change_auth_email")
async def change_auth_email_handler(callback: CallbackQuery):
    """Обработчик изменения почты для повторного ввода."""
    chat_id = callback.from_user.id
    await callback.answer()

    from src.shared.redis import get_redis_client
    from src.config import settings
    redis_client = await get_redis_client(database=settings.redis.databases.otp)

    await redis_client.delete(f"tg_verify_auth:{chat_id}")
    await callback.message.edit_text(
        text="Пожалуйста, введите другую почту для подтверждения."
    )

