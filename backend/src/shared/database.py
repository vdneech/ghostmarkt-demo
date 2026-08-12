from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from src.config import db_settings
import logging


logger = logging.getLogger(__name__)

engine = create_async_engine(
    db_settings.async_url,
    echo=db_settings.echo,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)



class Base(DeclarativeBase):
    pass