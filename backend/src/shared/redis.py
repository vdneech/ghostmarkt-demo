from redis import asyncio as aioredis
from src.config import settings

_redis_clients: dict[int, aioredis.Redis] = {}

async def get_redis_client(database: int) -> aioredis.Redis:
    global _redis_clients
    if database not in _redis_clients:
        _redis_clients[database] = aioredis.from_url(
            url=settings.redis.get_url(database),
            decode_responses=settings.redis.decode_responses
        )
    return _redis_clients[database]