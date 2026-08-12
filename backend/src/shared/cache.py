import logging
from fastapi_cache import FastAPICache

logger = logging.getLogger(__name__)

async def clear_cache(namespace: str):
    """
    Утилита для принудительного сброса кэша по пространству имен (namespace).
    В fastapi-cache2 есть баг: метод FastAPICache.clear(namespace="...")
    ищет ключи без префикса, в то время как декоратор @cache сохраняет их с префиксом.
    Данный хелпер автоматически добавляет префикс, гарантируя очистку кэша.
    """
    try:
        prefix = FastAPICache.get_prefix()
        target_namespace = f"{prefix}:{namespace}" if prefix else namespace
        logger.info(f"Сброс кэша для namespace: {target_namespace}")
        await FastAPICache.clear(namespace=target_namespace)
    except Exception as e:
        logger.warning(f"Ошибка при очистке кэша namespace={namespace}: {e}")
