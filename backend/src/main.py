import os
from contextlib import asynccontextmanager
from logging import getLogger

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from src.shared.exceptions import register_exception_handlers
from src.products.routes import router as product_router
from src.orders.routes import router as order_router
from src.auth.routes import router as auth_router
from src.cdek.routes import router as cdek_router
from src.bot.webhooks.telegram import router as telegram_router
from src.payments.routes import router as payments_router
from src.products.promocodes_routes import router as promocodes_router
from src.bot.config import start_bot, stop_bot
from src.config import settings, BASE_DIR
import logging

logger = getLogger(__name__)

templates = Jinja2Templates(directory="templates")


origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Инициализация сервера...")

    os.makedirs(settings.media.dir, exist_ok=True)
    logger.info("Папка с медиа-файлами проинициализирована...")


    try:
        from fastapi_cache import FastAPICache
        if settings.DEBUG:
            from fastapi_cache.backends.inmemory import InMemoryBackend
            FastAPICache.init(InMemoryBackend(), enable=False)
        else:
            from redis.asyncio import Redis
            from fastapi_cache.backends.redis import RedisBackend
            redis_client = Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.databases.cache
            )
            await redis_client.ping()
            FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache", enable=True)
    except Exception as e:
        logger.error("Не удалось проинициализировать кэширование: {}".format(e))

    await start_bot(application)

    yield

    logger.info("Инициирован процесс остановки сервера...")

    await stop_bot(application)

    logger.info("Сервер успешно остановлен.")


app = FastAPI(title="GhostMarket Backend", debug=settings.DEBUG, lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(product_router, prefix="/api")
app.include_router(order_router, prefix="/api")
app.include_router(promocodes_router, prefix="/api")

register_exception_handlers(app)

app.include_router(auth_router, prefix="/api")
app.include_router(cdek_router)
app.include_router(telegram_router, prefix="/api/webhooks")
app.include_router(payments_router, prefix="/api/webhooks")


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
