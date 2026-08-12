import hmac
import hashlib
import json
from urllib.parse import parse_qsl
import logging

logger = logging.getLogger(__name__)

def verify_telegram_webapp_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет валидность строки initData от Telegram WebApp с помощью bot_token.
    Возвращает словарь с данными пользователя при успехе, или None при невалидности.
    """
    try:
        logger.info("Запуск верификации initData от Telegram WebApp")
        vals = dict(parse_qsl(init_data))
        if "hash" not in vals:
            logger.warning("Отсутствует хэш в данных initData")
            return None
        
        data_hash = vals.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(vals.items()))
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(calculated_hash, data_hash):
            user_data_str = vals.get("user")
            if user_data_str:
                user_data = json.loads(user_data_str)
                logger.info("Telegram WebApp initData успешно валидирован для пользователя: %s", user_data.get("id"))
                return user_data
            logger.warning("Данные пользователя отсутствуют в валидном initData")
            return {}
        
        logger.warning("Несовпадение хэшей в Telegram WebApp initData")
        return None
    except Exception as e:
        logger.error("Ошибка при проверке initData Telegram: %s", e)
        return None
