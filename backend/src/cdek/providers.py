from json import JSONDecodeError
from typing import TYPE_CHECKING, Optional, Any
from httpx import AsyncClient

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from pydantic import BaseModel

from httpx import Response
from src.config import settings
from src.cdek.schemas import CDEKAuthorizationToken
import logging

logger = logging.getLogger(__name__)
from src.cdek.exceptions import (
    CDEKRequestError,
    CDEKApiError,
    CDEKAuthenticationError,
)

from enum import Enum


class CDEKAction(str, Enum):
    OFFICES = "offices"
    CALCULATE = "calculate"
    CALCULATE_TARIFF = "calculate_tariff"
    CITIES = "cities"
    REGIONS = "regions"
    TARIFFS = "tariffs"

    @property
    def mapping(self):
        mapping = {
            "offices": ("GET", "deliverypoints"),
            "calculate": ("POST", "calculator/tarifflist"),
            "calculate_tariff": ("POST", "calculator/tariff"),
            "cities": ("GET", "location/cities"),
            "regions": ("GET", "location/regions"),
            "tariffs": ("POST", "calculator/tarifflist"),
        }
        return mapping[self.value]


class CDEKProvider:
    """
    Провайдер для прямого взаимодействия с HTTP API службы доставки CDEK.
    Отвечает за проксирование запросов виджета, отправку GET/POST запросов
    и кэширование токена авторизации OAuth2 в Redis.
    """

    def __init__(
        self,
        redis: "Redis",
        http_client: "AsyncClient",
    ):
        """
        Инициализирует провайдер с Redis клиентом, HTTP клиентом и авторизационными ключами.
        """
        self._redis = redis
        self._redis_key = "cdek_token"
        self.token_model = CDEKAuthorizationToken

        self._client_id = settings.cdek.client_id.get_secret_value()
        self._client_secret = settings.cdek.client_secret.get_secret_value()

        self.base_url = settings.cdek.base_url.get_secret_value().rstrip("/") + "/"
        self._client = http_client

    async def proxy_request(
        self, path: str, action: CDEKAction | None, payload: dict
    ) -> dict:
        if action:
            method, endpoint = action.mapping
        else:
            raise CDEKRequestError("Action is required to determine endpoint")

        url = f"{self.base_url}{endpoint.lstrip('/')}"
        headers = await self._get_auth_header()

        response = await self._client.request(
            method=method,
            url=url,
            json=payload if method == "POST" else None,
            params=payload if method == "GET" else None,
            headers=headers,
        )

        await self._handle_response(response)
        return response.json()

    async def get(
        self, url: str, payload: "BaseModel" = None, params: dict[str, Any] = None
    ) -> dict:
        """
        Выполняет авторизованный GET-запрос к API CDEK с передачей параметров из Pydantic-модели.
        """
        logger.info("Запуск GET-запроса к CDEK. URL: {}".format(url))
        headers = await self._get_auth_header()
        full_url = self.base_url + url.lstrip("/")
        if payload:
            params = (payload.model_dump(exclude_none=True),)
        try:
            response = await self._client.get(
                url=full_url,
                params=params,
                headers=headers,
            )
            logger.warning(response.json())
        except Exception as e:
            logger.error("Сбой HTTP GET запроса к CDEK: {}".format(e))
            raise CDEKRequestError(f"Сбой GET-запроса к CDEK: {e}")

        logger.info("GET-запрос к CDEK {} завершен со статусом {}".format(full_url, response.status_code))

        if not response.is_success:
            logger.error("CDEK API GET ошибка: {}".format(response.text[:500]))
            raise CDEKApiError(status_code=response.status_code, detail=response.json())

        return response.json()

    async def post(self, url: str, payload: dict) -> dict:
        headers = await self._get_auth_header()
        full_url = self.base_url + url.lstrip("/")

        try:
            response = await self._client.post(
                url=full_url,
                json=payload,
                headers=headers,
                timeout=30,
            )
            return await self._handle_response(response)
        except Exception as e:
            if isinstance(e, CDEKApiError):
                raise e
            logger.error("Сбой HTTP POST запроса к CDEK: {}".format(e))
            raise CDEKRequestError(f"Сбой POST-запроса: {e}")

    async def delete(self, url: str, params: dict[str, Any] = None) -> dict:

        headers = await self._get_auth_header()
        full_url = self.base_url + url.lstrip("/")

        try:
            response = await self._client.delete(
                url=full_url,
                params=params,
                headers=headers,
                timeout=30,
            )
            return await self._handle_response(response)
        except Exception as e:
            if isinstance(e, CDEKApiError):
                raise e
            logger.error("Сбой HTTP DELETE запроса к CDEK: {}".format(e))
            raise CDEKRequestError(f"Сбой DELETE-запроса: {e}")

    @staticmethod
    async def _handle_response(response: Response) -> dict:
        """Централизованная обработка ответов CDEK."""
        if response.is_success:
            return response.json()
        try:
            error_data = response.json()
        except (JSONDecodeError, TypeError):
            error_data = {"message": response.text}

        logger.error("CDEK API Error {}: {}".format(response.status_code, error_data))
        raise CDEKApiError(status_code=response.status_code, detail=error_data)

    async def _get_token(self) -> "CDEKAuthorizationToken":
        """
        Возвращает кэшированный токен авторизации из Redis.
        При отсутствии кэша запрашивает новый токен через OAuth2 API CDEK и кэширует его.
        """
        logger.info("Запрос токена авторизации CDEK")
        token = await self._get_from_redis()
        if token:
            logger.info("Токен авторизации успешно извлечен из кэша Redis.")
            return token

        logger.info(
            "Токен в кэше не найден. Запрос нового токена через CDEK OAuth2 API."
        )
        try:
            response = await self._client.post(
                url=self.base_url + "oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        except Exception as e:
            logger.error("Сбой сети при получении токена CDEK: {}".format(e))
            raise CDEKAuthenticationError(f"Сбой сети при авторизации CDEK: {e}")

        if not response.is_success:
            logger.error("Ошибка авторизации CDEK API: {}".format(response.text))
            raise CDEKAuthenticationError(
                "Не удалось получить токен CDEK (неверные credentials или ошибка API)"
            )

        token_data = self.token_model.model_validate(response.json())
        await self._save_token(token_data)
        logger.info("Новый токен CDEK успешно получен и сохранен в кэш.")
        return token_data

    async def _save_token(self, token: "CDEKAuthorizationToken") -> None:
        """
        Сохраняет полученный токен в Redis с указанием времени его жизни.
        """
        logger.info("Сохранение токена CDEK в Redis на время: {} сек.".format(token.expires_in))
        try:
            await self._redis.set(
                name=self._redis_key,
                value=token.model_dump_json(),
                ex=token.expires_in,
            )
        except Exception as e:
            logger.error("Не удалось сохранить токен CDEK в кэш Redis: {}".format(e))

    async def _get_from_redis(self) -> Optional["CDEKAuthorizationToken"]:
        """
        Пытается прочесть токен авторизации из кэша Redis.
        """
        logger.info("Попытка получения токена CDEK из Redis")
        try:
            raw = await self._redis.get(self._redis_key)
            if not raw:
                return None

            token = self.token_model.model_validate_json(raw)
            token.expires_in = await self._redis.ttl(self._redis_key)
            return token
        except Exception as e:
            logger.error("Ошибка при обращении к кэшу Redis для получения токена CDEK: {}".format(e))
            return None

    async def _get_auth_header(self) -> dict[str, str]:
        """
        Формирует словарь заголовка Authorization с актуальным Bearer токеном.
        """
        token = await self._get_token()
        return {"Authorization": f"Bearer {token.access_token}"}
