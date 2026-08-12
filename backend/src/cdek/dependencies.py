from src.cdek.services import CDEKService
from src.config import settings
from src.shared.redis import get_redis_client


async def get_cdek_service():
    redis_client = await get_redis_client(database=settings.redis.databases.cdek)

    otp_service = CDEKService(redis=redis_client)
    return otp_service