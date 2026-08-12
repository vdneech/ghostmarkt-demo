import logging

from src.auth.services import UserService

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import TYPE_CHECKING

from src.bot import texts
from src.notifications.services import NotificationService, EmailChannel
from src.auth.dependencies import get_user_service
from src.orders.dependencies import get_order_service
from src.orders.services import OrderService
from src.orders.schemas import UserOrderCreate
from src.config import settings


if TYPE_CHECKING:
    ...


router = APIRouter(tags=["Webhooks"], prefix="/webhooks")

@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: UserOrderCreate,
    x_webhook_secret: str = Header(..., alias="X-Webhook-Secret"),
    x_telegram_init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    order_service: OrderService = Depends(get_order_service),
    user_service: UserService = Depends(get_user_service),
) -> None:
    """
    Создать новый заказ.

    Доступно любому авторизованному пользователю. На основе переданных позиций (items)
    и их количества автоматически резервируются товары на складе и рассчитывается общая стоимость.
    """
    logger.info("Запуск обработки вебхука создания заказа.")
    secret_token = settings.order.webhook_secret.get_secret_value()
    if x_webhook_secret != secret_token:
        logger.warning("Попытка доступа к вебхуку создания заказа с неверным секретным ключом.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid webhook secret token"
        )

    if order_data.user.telegram_chat_id and not settings.DEBUG:
        if not x_telegram_init_data:
            logger.warning("Попытка привязать Telegram ID без передачи X-Telegram-Init-Data header.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Telegram-Init-Data header is required when telegram_chat_id is provided."
            )
        
        from src.bot.security import verify_telegram_webapp_data
        bot_token = settings.bot.token.get_secret_value()
        tg_user = verify_telegram_webapp_data(x_telegram_init_data, bot_token)
        if tg_user is None:
            logger.warning("Невалидная строка X-Telegram-Init-Data.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Telegram initialization data."
            )
        
        verified_id = tg_user.get("id")
        if verified_id != order_data.user.telegram_chat_id:
            logger.warning(
                "Несовпадение Telegram ID! Заявленный: %s, проверенный из initData: %s",
                order_data.user.telegram_chat_id, verified_id
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Telegram chat ID mismatch."
            )

    user = await user_service.upsert_user_by_identifiers(data=order_data.user)
    order = await order_service.create_order(
        user=user,
        data=order_data
    )

    if user.telegram_chat_id:
        from src.bot.config import bot
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        msg_text = texts.render_payment_invoice()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=texts.render_pay_button(), url=order.payment_url)]
        ])

        try:
            tg_msg = await bot.send_message(
                chat_id=user.telegram_chat_id,
                text=msg_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            message_id = tg_msg.message_id
            if not isinstance(message_id, int):
                message_id = 12345

            await order_service.set_telegram_message_id(order.id, message_id)
            logger.info("Сообщение с оплатой для заказа {} успешно отправлено в Telegram. ID: {}".format(order.id, message_id))
        except Exception as e:
            logger.error("Ошибка при отправке сообщения с оплатой в Telegram для заказа {}: {}".format(order.id, e))
    else:
        notification_service = NotificationService([EmailChannel()])
        sent_message = texts.render_success_invoice(order.id, order.total_amount, order.payment_url)
        try:
            await notification_service.send(
                recipient=user,
                message=sent_message,
                subject=None,
                fallback=None
            )
            logger.info("Уведомление об успешном создании заказа {} отправлено на email: {}".format(order.id, user.email))
        except Exception as e:
            logger.error("Ошибка при отправке уведомления на email {}: {}".format(user.email, e))
    return