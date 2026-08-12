from typing import AsyncIterator, Union, Literal, Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from typing_extensions import overload

from src.auth.schemas import UserCreate
import logging

logger = logging.getLogger(__name__)
from src.shared.dao import BaseDAO
from src.auth.models import User

class UsersDAO(BaseDAO[User]):
    """
    Класс для управления доступом к данным пользователей (User).
    Наследует CRUD-операции из BaseDAO.
    """
    model = User

    async def find_one_or_none_by_telegram_chat_id(self, chat_id: int) -> User | None:
        """
        Ищет и возвращает пользователя по его ID чата в Telegram.
        Если пользователь не найден, возвращает None.
        """
        logger.info("Запрос на поиск пользователя по telegram_chat_id: {}".format(chat_id))
        try:
            query = select(self.model).filter_by(telegram_chat_id=chat_id)
            result = await self._session.execute(query)
            record = result.scalar_one_or_none()
            if record:
                logger.info("Пользователь с telegram_chat_id {} успешно найден.".format(chat_id))
            else:
                logger.info("Пользователь с telegram_chat_id {} не найден.".format(chat_id))
            return record
        except SQLAlchemyError as e:
            logger.error("Ошибка при поиске пользователя по telegram_chat_id {}: {}".format(chat_id, e))
            raise

    async def get_or_create_by_email(self, email: str, data: UserCreate) -> User:
        """
        Ищет пользователя по email. Если пользователь отсутствует, создает нового
        на основе предоставленных данных. Неявно выполняет commit текущей сессии.
        """
        logger.info("Запрос на получение или создание пользователя с email: {}".format(email))
        try:
            user = await self.find_one_or_none(email=email)
            if not user:
                logger.info("Пользователь с email {} не найден. Запуск создания нового пользователя.".format(email))
                user = await self.add(**data.model_dump())
            else:
                logger.info("Пользователь с email {} найден в базе данных.".format(email))

            await self._session.commit()
            logger.info("Транзакция успешно зафиксирована (commit) для пользователя.")
            return user
        except Exception as e:
            logger.error("Ошибка в процессе получения или создания пользователя с email {}: {}".format(email, e))
            raise

    @overload
    async def get_admins(self, sync: Literal[True]) -> list[User]:
        ...

    @overload
    async def get_admins(self, sync: Literal[False] = False) -> AsyncIterator[User]:
        ...

    async def get_admins(self, sync: bool = False) -> Union[list[User], AsyncIterator[User]]:
        """
        Возвращает список или асинхронный генератор всех администраторов системы.
        """
        logger.info("Запрос на получение администраторов. Режим синхронизации (sync): {}".format(sync))
        try:
            stmt = select(self.model).where(self.model.is_superuser == True)

            if sync:
                result = await self._session.scalars(stmt)
                admins_list = list(result.all())
                logger.info("Успешно извлечен список администраторов. Найдено: {}".format(len(admins_list)))
                return admins_list
            else:
                logger.info("Инициировано потоковое асинхронное получение администраторов.")
                return self._admin_stream_generator(stmt)

        except SQLAlchemyError as e:
            logger.error("Ошибка при получении списка администраторов: {}".format(e))
            raise

    async def _admin_stream_generator(self, stmt: Any) -> AsyncIterator[User]:
        """
        Вспомогательный асинхронный генератор для последовательного чтения администраторов.
        """
        logger.info("Запуск асинхронного генератора потокового чтения администраторов.")
        try:
            result = await self._session.stream_scalars(stmt)
            async for admin in result:
                yield admin
        except SQLAlchemyError as e:
            logger.error("Ошибка внутри асинхронного генератора администраторов: {}".format(e))
            raise

    async def check_full_registration_by_chat_id(self, chat_id: int) -> bool:
        """
        Проверяет, завершил ли пользователь регистрацию в Telegram-боте.
        Возвращает True, если заполнены все обязательные поля анкеты.
        """
        logger.info("Запрос на проверку полноты анкеты пользователя с telegram_chat_id: {}".format(chat_id))
        try:
            user = await self.find_one_or_none_by_telegram_chat_id(chat_id)
            if not user:
                logger.info("Пользователь с telegram_chat_id {} не найден. Проверка анкеты отклонена.".format(chat_id))
                return False

            required_fields = [
                user.email,
                user.first_name,
                user.last_name,
                user.specialty,
                user.source,
                user.phone,
            ]
            is_full = all(required_fields)
            logger.info("Результат проверки анкеты для telegram_chat_id {}: {}".format(chat_id, is_full))
            return is_full

        except Exception as e:
            logger.error("Ошибка при проверке заполнения анкеты для telegram_chat_id {}: {}".format(chat_id, e))
            raise