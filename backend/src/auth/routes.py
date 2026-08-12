from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from typing import TYPE_CHECKING
from pydantic import EmailStr
import logging

from src.auth.schemas import UserCreate, UserResponse, UserUpdate, AdminUserUpdate, AdminUserReplace
from src.auth.services import UserService
from src.config import settings
from src.auth.dependencies import (
    get_current_user,
    get_otp_service,
    get_users_dao,
    get_auth_service,
    get_current_superuser,
    get_user_service,
    get_current_user_or_none
)
from src.auth.models import User
from src.notifications.services import NotificationService, EmailChannel
from src.notifications.renderer import EmailTemplateRenderer

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.auth.services import AuthService, OTPService
    from src.auth.dao import UsersDAO

router = APIRouter(
    prefix="/auth",
    tags=["Auth"])

@router.post(
    "/login/",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запросить код авторизации (OTP)",
    responses={
        status.HTTP_202_ACCEPTED: {
            "description": "Запрос принят, код отправлен на почту"
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Некорректный формат email"
        }
    }
)
async def login_by_email(
    email: EmailStr,
    otp_service: "OTPService" = Depends(get_otp_service),
    user_service: "UserService" = Depends(get_user_service),
):
    """
    ### Запрос одноразового пароля (OTP) для входа
    
    Выполняет следующие действия:
    1. Генерирует и сохраняет в Redis **OTP-код** для указанного `email`.
    2. Проверяет наличие пользователя в БД; если пользователя нет – **создает** новую запись.
    3. Отправляет письмо с кодом подтверждения на `email` через Celery-воркер.
    """
    logger.info("Вход в роут запроса OTP для email: {}".format(email))
    code = await otp_service.generate_and_save(email)
    user = await user_service.get_or_create_by_email(email=email, data=UserCreate(email=email))

    from src.notifications.tasks import send_email_otp_notification_task
    send_email_otp_notification_task.delay(user.id, code)
    logger.info("Код подтверждения отправлен на почту для {}".format(email))


@router.post(
    "/login/otp/",
    status_code=status.HTTP_200_OK,
    summary="Подтвердить вход по OTP",
    responses={
        status.HTTP_200_OK: {
            "description": "Успешная авторизация, JWT токены записаны в cookies"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Невалидный код подтверждения или неверный Email",
            "content": {"application/json": {"example": {"detail": "Невалидный код подтверждения или неверный Email."}}}
        }
    }
)
async def verify_otp(
    email: EmailStr,
    code: str,
    response: Response,
    auth_service: "AuthService" = Depends(get_auth_service),
    otp_service: "OTPService" = Depends(get_otp_service),
):
    """
    ### Верификация OTP кода
    
    Выполняет верификацию переданного **OTP-кода**:
    * Генерирует пару JWT токенов: `access_token` и `refresh_token`.
    * Записывает их в **HTTP-only cookies** клиента со следующими свойствами:
      * `httponly=True` (защита от XSS)
      * `secure` (включается на продакшене для HTTPS)
      * `samesite="lax"`
    """
    logger.info("Вход в роут верификации OTP для email: {}".format(email))
    if not await otp_service.verify(email, code):
        logger.warning("Неудачная авторизация: невалидный OTP код для email {}".format(email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный код подтверждения или неверный Email."
        )

    access_token = auth_service.create_token(
        email, expires=settings.authentication.access_token.lifetime
    )
    refresh_token = auth_service.create_token(
        email,
        expires=settings.authentication.refresh_token.lifetime,
        refresh=True,
    )

    response.set_cookie(
        key=settings.authentication.access_token.cookie_key,
        value=access_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.authentication.access_token.lifetime
    )

    response.set_cookie(
        key=settings.authentication.refresh_token.cookie_key,
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.authentication.refresh_token.lifetime
    )
    logger.info("Пользователь {} успешно авторизован. Куки установлены.".format(email))
    return



@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    summary="Обновить токены доступа",
    responses={
        status.HTTP_200_OK: {
            "description": "Токены успешно обновлены в cookies"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Недействительный Refresh токен",
            "content": {"application/json": {"example": {"detail": "Невалидный токен обновления."}}}
        }
    }
)
async def refresh_tokens(
    request: Request,
    response: Response,
    auth_service: "AuthService" = Depends(get_auth_service),
):
    """
    ### Обновление токенов доступа
    
    Считывает `refresh_token` из cookies и выполняет его декодирование и проверку:
    * При успешной проверке генерирует новый `access_token`.
    * Перезаписывает cookie с новым временем жизни.
    """
    logger.info("Вход в роут обновления токенов доступа")
    refresh_token = request.cookies.get(settings.authentication.refresh_token.cookie_key)
    if not refresh_token:
        logger.warning("Попытка обновления токена отклонена: отсутствует кука refresh_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия устарела или токен обновления отсутствует."
        )

    try:
        email = auth_service.decode_and_verify(refresh_token, refresh=True)
        new_access_token = auth_service.create_token(
            email, expires=settings.authentication.access_token.lifetime
        )

        response.set_cookie(
            key=settings.authentication.access_token.cookie_key,
            value=new_access_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            max_age=settings.authentication.access_token.lifetime
        )
        logger.info("Токен доступа успешно обновлен для пользователя: {}".format(email))
        return
    except Exception as e:
        logger.error("Не удалось обновить токен доступа: {}".format(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен обновления."
        )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Выйти из системы",
    responses={
        status.HTTP_200_OK: {
            "description": "Сессия завершена, cookies удалены",
            "content": {"application/json": {"example": {"message": "Вы успешно вышли из системы."}}}
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        }
    }
)
async def logout(
    response: Response,
    user: User = Depends(get_current_user)
):
    """
    ### Выход из системы
    
    Завершает сессию пользователя путем **удаления** кук авторизации (`access_token` и `refresh_token`) из браузера.
    """
    logger.info("Вход в роут выхода из системы. Пользователь: {}".format(user.id))
    response.delete_cookie(key=settings.authentication.access_token.cookie_key)
    response.delete_cookie(key=settings.authentication.refresh_token.cookie_key)
    logger.info("Сессия пользователя {} успешно завершена (куки удалены).".format(user.id))
    return {"message": "Вы успешно вышли из системы."}


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    summary="Получить текущий профиль",
    responses={
        status.HTTP_200_OK: {
            "description": "Информация о профиле успешно получена"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        }
    }
)
async def get_profile(
    service: UserService = Depends(get_user_service),
    user: User = Depends(get_current_user),
):
    """
    ### Получение профиля текущего пользователя
    
    Возвращает детальную информацию о профиле авторизованного пользователя на основе его `user_id`.
    """
    logger.info("Вход в роут получения собственного профиля для пользователя ID: {}".format(user.id))
    response = await service.get_by_id(user_id=user.id)
    logger.info("Профиль пользователя ID {} успешно возвращен.".format(user.id))
    return response


@router.patch(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    summary="Обновить профиль",
    responses={
        status.HTTP_200_OK: {
            "description": "Профиль успешно обновлен"
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверные входные данные"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        }
    }
)
async def update_profile(
    data: UserUpdate,
    service: UserService = Depends(get_user_service),
    user: User = Depends(get_current_user),
):
    """
    ### Обновление профиля текущего пользователя
    
    Позволяет частично изменить информацию о себе:
    * `first_name` / `last_name` / `middle_name`
    * Номер телефона `phone`
    * Локаль/язык интерфейса `locale`
    """
    logger.info("Вход в роут обновления собственного профиля для пользователя ID: {}".format(user.id))
    response = await service.update(
        user_id=user.id,
        data=data,
    )
    logger.info("Профиль пользователя ID {} успешно обновлен.".format(user.id))
    return response



@router.get(
    "/users/",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Получить список пользователей",
    responses={
        status.HTTP_200_OK: {
            "description": "Список пользователей успешно получен"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав (доступно только администраторам)"
        }
    }
)
async def list_users(
    request: Request,
    service: UserService = Depends(get_user_service),
    current_user: User | None = Depends(get_current_user_or_none),
):
    """
    ### Получение списка пользователей (Админ)
    
    * Если передан заголовок `x-telegram-init-data`, возвращает профиль соответствующего пользователя Telegram.
    * В остальных случаях требует права **суперпользователя** (`is_superuser=True`) и возвращает список **всех пользователей** системы.
    """
    tg_init_data = request.headers.get("x-telegram-init-data")
    if tg_init_data:
        from src.bot.security import verify_telegram_webapp_data
        bot_token = settings.bot.token.get_secret_value()
        tg_user = verify_telegram_webapp_data(tg_init_data, bot_token)
        if tg_user is not None and "id" in tg_user:
            user = await service.dao.find_one_or_none_by_telegram_chat_id(tg_user["id"])
            if user:
                return [UserResponse.model_validate(user)]
            return []
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные данные Telegram Init Data"
        )

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация"
        )

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для выполнения этой операции."
        )

    response = await service.get_all_users()
    return response


@router.get(
    "/users/{user_id}/",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Получить информацию о пользователе",
    responses={
        status.HTTP_200_OK: {
            "description": "Информация о пользователе успешно получена"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав"
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Пользователь не найден"
        }
    }
)
async def get_user_detail(
    user_id: int,
    service: UserService = Depends(get_user_service),
    admin: User = Depends(get_current_superuser),
):
    """
    ### Детальная информация о пользователе (Админ)
    
    Возвращает полную информацию о пользователе по его `user_id`. Доступно только **администраторам**.
    """
    logger.info("Администратор ID {} запросил информацию о пользователе ID {}.".format(admin.id, user_id))
    response = await service.get_by_id(user_id=user_id)
    logger.info("Информация о пользователе ID {} успешно получена.".format(user_id))
    return response


@router.patch(
    "/users/{user_id}/",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Частично обновить пользователя (админ)",
    responses={
        status.HTTP_200_OK: {
            "description": "Данные пользователя успешно обновлены"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав"
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Пользователь не найден"
        }
    }
)
async def partial_update_user(
    user_id: int,
    data: AdminUserUpdate,
    service: UserService = Depends(get_user_service),
    admin: User = Depends(get_current_superuser),
):
    """
    ### Частичное обновление данных пользователя (Админ)
    
    Позволяет администратору точечно изменить любые поля пользователя (за исключением `telegram_chat_id`).
    """
    logger.info("Администратор ID {} запросил PATCH-обновление пользователя ID {}.".format(admin.id, user_id))
    response = await service.admin_update_user(user_id=user_id, data=data)
    logger.info("Пользователь ID {} успешно обновлен (PATCH) администратором ID {}.".format(user_id, admin.id))
    return response


@router.put(
    "/users/{user_id}/",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Полностью обновить пользователя (админ)",
    responses={
        status.HTTP_200_OK: {
            "description": "Данные пользователя успешно обновлены"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован"
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав"
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Пользователь не найден"
        }
    }
)
async def full_update_user(
    user_id: int,
    data: AdminUserReplace,
    service: UserService = Depends(get_user_service),
    admin: User = Depends(get_current_superuser),
):
    """
    ### Полное обновление данных пользователя (Админ)
    
    Выполняет перезапись всех полей пользователя переданными значениями (кроме `telegram_chat_id`).
    """
    logger.info("Администратор ID {} запросил PUT-обновление пользователя ID {}.".format(admin.id, user_id))
    response = await service.admin_update_user(user_id=user_id, data=data)
    logger.info("Пользователь ID {} успешно обновлен (PUT) администратором ID {}.".format(user_id, admin.id))
    return response