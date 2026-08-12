from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.security import CookieAuth
from src.auth.models import User
from src.auth.dao import UsersDAO
from src.shared.dependencies import get_db
from src.config import settings
from src.auth.services import OTPService, AuthService, UserService
from src.shared.redis import get_redis_client

async def get_user_service(
    session: AsyncSession = Depends(get_db),
) -> UserService:
    """
    Зависимость для получения экземпляра UserService.
    """
    return UserService(session=session)

async def get_auth_service(
    session: AsyncSession = Depends(get_db),
):

    redis = await get_redis_client(database=settings.redis.databases.otp)
    service = AuthService(session, redis=redis)
    return service

cookie_auth_scheme = CookieAuth(
    cookie_name=settings.authentication.access_token.cookie_key,
    auto_error=True,
)

optional_cookie_auth_scheme = CookieAuth(
    cookie_name=settings.authentication.access_token.cookie_key,
    auto_error=False,
)


async def get_otp_service():
    redis_client = await get_redis_client(database=settings.redis.databases.otp)

    otp_service = OTPService(redis=redis_client)
    return otp_service


async def get_users_dao(
    session: AsyncSession = Depends(get_db),
):
    users_dao = UsersDAO(session)
    return users_dao

async def get_current_user_or_none(
    dao: UsersDAO = Depends(get_users_dao),
    token: str | None = Depends(optional_cookie_auth_scheme),
) -> User | None:
    """Возвращает текущего пользователя или None. """
    if not token:
        return None

    try:
        email = AuthService.decode_and_verify(token)
    except Exception as e:
        return None

    user = await dao.find_one_or_none(email=email)

    return user


async def get_current_user(
    user: User = Depends(get_current_user_or_none),
) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

async def get_current_superuser(user: "User" = Depends(get_current_user)) -> "User":
    if not user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для выполнения этой операции."
        )
    return user
