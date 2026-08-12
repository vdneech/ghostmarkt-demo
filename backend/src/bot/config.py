import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.middlewares.dao_middleware import DAOMiddleware
import logging

logger = logging.getLogger(__name__)
from src.config import settings
from src.shared.database import async_session
from src.bot.middlewares.db import DbSessionMiddleware
from src.bot.handlers.commands import router as commands_router
from src.bot.handlers.order import router as order_router
from src.bot.handlers.about import router as about_router

bot = Bot(
    token=settings.bot.token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp: Dispatcher = Dispatcher(storage=MemoryStorage())


async def setup_dispatcher(dispatcher: Dispatcher) -> Dispatcher:
    """Настраивает переданный диспетчер."""
    dispatcher.include_router(commands_router)
    dispatcher.include_router(order_router)
    dispatcher.include_router(about_router)
    dispatcher.update.middleware(DbSessionMiddleware(session_pool=async_session))
    dispatcher.update.middleware(DAOMiddleware())

    return dispatcher


async def start_bot(app) -> None:
    """Настройка бота и запуск диспетчера."""
    await setup_dispatcher(dp)

    if settings.ON_WEBHOOKS:
        logger.info("Режим: ВЕБХУКИ. Настройка эндпоинта: {}".format(settings.WEBHOOK_URL))
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            drop_pending_updates=True,
            secret_token=settings.bot.webhook_secret_token.get_secret_value(),
        )
    else:
        logger.info("Режим: LONG POLLING.")
        await bot.delete_webhook(drop_pending_updates=True)
        polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        app.state.polling_task = polling_task


async def stop_bot(app) -> None:
    """Корректное завершение работы."""
    if settings.ON_WEBHOOKS:
        try:
            await bot.delete_webhook()
        except Exception as e:
            logger.error("Ошибка при удалении вебхука: {}".format(e))
    else:
        logger.info("Остановка фонового Long Polling...")
        polling_task = getattr(app.state, 'polling_task', None)
        if polling_task:
            polling_task.cancel()

    await dp.storage.close()
    await bot.session.close()
    logger.info("Ресурсы освобождены.")

