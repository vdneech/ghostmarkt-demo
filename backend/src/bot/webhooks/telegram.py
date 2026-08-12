import logging
logger = logging.getLogger(__name__)
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, status
from src.bot import bot, dp
from src.config import settings

router = APIRouter(tags=["Telegram Webhook"])


@router.post("/telegram")
async def telegram_webhook(
        update: dict,
        x_telegram_bot_api_secret_token: str = Header(None)
):
    secret_token = settings.bot.webhook_secret_token.get_secret_value()
    if x_telegram_bot_api_secret_token != secret_token:
        logger.warning("Попытка несанкционированного доступа к вебхуку Telegram!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized access"
        )

    try:
        aiogram_update = Update.model_validate(update, context={"bot": bot})
        await dp.feed_update(bot, aiogram_update)
    except Exception as e:
        logger.error("Ошибка при обработке апдейта Telegram: {}".format(e))

    return {"status": "ok"}