from typing import Type, TYPE_CHECKING, TypeVar
from fastapi import Depends, Response

from src.shared.services import SessionService
from src.shared.services import MediaService
from src.shared.exceptions import DAONotFoundError
from src.shared.dao import BaseDAO
from src.shared.database import Base
from src.shared.services import Service


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from aiogram import Bot

async def get_db():
    """Зависимость, поставляющая асинхронную сессию SQLAlchemy в эндпоинты FastAPI"""
    from src.shared.database import async_session
    async with async_session() as session:
        yield session



async def get_bot() -> "Bot":
    """Зависимость, поставляющая экземпляр бота в эндпоинты FastAPI"""
    from src.bot.config import bot
    return bot



DAO_MAP = {
    dao.model: dao
    for dao in BaseDAO.get_all_subclasses()
}



def get_dao(model: Type[Base]):
    def _dependency(session: "AsyncSession" = Depends(get_db)) -> BaseDAO:
        dao_class = DAO_MAP.get(model)
        if not dao_class:
            raise DAONotFoundError()
        return dao_class(session=session)
    return _dependency

def get_media_service() -> MediaService:
    return MediaService()


def clear_browser_cache(response: Response):
    """
    Зависимость FastAPI для принудительного сброса локального кэша в браузере клиента.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Clear-Site-Data"] = '"cache"'