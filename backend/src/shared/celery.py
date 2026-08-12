from celery import Celery
from src.config import settings
from src.config import db_settings
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

app = Celery(
    main="ghost",
    broker=settings.redis.get_url(
        settings.redis.databases.celery,
    ),
    backend=settings.redis.get_url(
        settings.redis.databases.celery_backend,
    ),
    include=[
        "src.notifications.tasks",
        "src.orders.tasks",
    ]
)

celery_engine = create_async_engine(
    db_settings.async_url,
    poolclass=NullPool
)

celery_session_maker = async_sessionmaker(bind=celery_engine, expire_on_commit=False)


from celery.signals import setup_logging

@setup_logging.connect
def setup_celery_logging(*args, **kwargs) -> None:
    """Disable Celery's default logging setup to keep dictConfig active."""
    pass

