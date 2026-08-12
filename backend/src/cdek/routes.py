import logging
from fastapi import APIRouter, Depends, Request, Query, HTTPException, status

from src.cdek.providers import CDEKAction
from src.cdek.dependencies import get_cdek_service
from src.cdek.services import CDEKService
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/cdek",
    tags=[
        "CDEK",
    ]
)




PATH_TO_ACTION = {
    "deliverypoints": CDEKAction.OFFICES,
    "calculator/tarifflist": CDEKAction.CALCULATE,
    "calculator/tariff": CDEKAction.CALCULATE_TARIFF,
    "location/cities": CDEKAction.CITIES,
    "location/regions": CDEKAction.REGIONS,
}


@router.api_route(
    "/proxy/{path:path}",
    methods=["GET", "POST"],
    summary="Прокси-запросы к API СДЭК",
    responses={
        status.HTTP_200_OK: {
            "description": "Успешный ответ от API СДЭК"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Отсутствует или невалидный заголовок x-telegram-init-data"
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Некорректный запрос или отсутствующие параметры"
        }
    }
)
async def cdek_proxy(
    path: str,
    request: Request,
    service: CDEKService = Depends(get_cdek_service),
    action: CDEKAction | None = Query(None),
):
    """
    ### Проксирование запросов к CDEK API
    
    Маршрут принимает запросы от Telegram WebApp и перенаправляет их к официальному API СДЭК:
    * Защищен проверкой заголовка `x-telegram-init-data`.
    * Поддерживает автоматическое определение типа операции (`action`) по пути запроса или параметрам.
    * Производит автоматическое кэширование авторизационных токенов СДЭК в Redis.
    """
    tg_init_data = request.headers.get("x-telegram-init-data")

    is_tg_valid = False
    if tg_init_data:
        from src.bot.security import verify_telegram_webapp_data
        bot_token = settings.bot.token.get_secret_value()
        try:
            tg_user = verify_telegram_webapp_data(tg_init_data, bot_token)
            if tg_user is not None:
                is_tg_valid = True
        except Exception as e:
            logger.error("Error verifying Telegram WebApp data in proxy: %s", e)

    if not is_tg_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Telegram Init Data")

    try:
        payload = await request.json() if request.method == "POST" else {}
    except Exception:
        payload = {}
    query_params = dict(request.query_params)

    if not action:
        clean_path = path.strip("/")
        if clean_path in PATH_TO_ACTION:
            action = PATH_TO_ACTION[clean_path]
        else:
            raw_action = query_params.get("action") or payload.get("action")
            if raw_action:
                try:
                    action = CDEKAction(raw_action)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid CDEK Action")
            else:
                raise HTTPException(status_code=400, detail="Action is required to use CDEK proxy safely")

    query_params.pop("action", None)
    payload.pop("action", None)

    return await service.provider.proxy_request(
        path=path,
        action=action,
        payload={**query_params, **payload}
    )

