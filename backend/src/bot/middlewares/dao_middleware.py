import re
from typing import Callable, Dict, Any, Awaitable, List, Tuple, Type

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)
from src.shared.dao import BaseDAO

def _to_snake_case(name: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

DAO_REGISTRY: List[Tuple[Type[BaseDAO], str]] = [
    (dao_class, _to_snake_case(dao_class.__name__))
    for dao_class in BaseDAO.get_all_subclasses()
]


class DAOMiddleware(BaseMiddleware):
    """
    Middleware, который автоматически находит всех наследников BaseDAO,
    инициализирует их с текущей сессией БД и пробрасывает в хендлеры.
    """

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        session: AsyncSession = data.get("session")

        if session:
            for dao_class, key_name in DAO_REGISTRY:
                logger.debug("Регистрация DAO внутри бота: {}".format(key_name))
                data[key_name] = dao_class(session)

        return await handler(event, data)
