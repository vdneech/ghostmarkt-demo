import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import PlainTextResponse

from src.payments.services import PaymentService
from src.payments.dependencies import get_payment_service
from src.cdek.dependencies import get_cdek_service
from src.orders.dependencies import get_order_service
from src.cdek.services import CDEKService
from src.orders.services import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/robokassa", tags=["Payments"])

from fastapi import Request

@router.post(
    "/result",
    response_class=PlainTextResponse,
    summary="Обработать платежный вебхук от Робокассы",
    responses={
        status.HTTP_200_OK: {
            "description": "Платеж успешно обработан, возвращает строку OK{InvId}",
            "content": {"text/plain": {"example": "OK123"}}
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Неверная подпись или отсутствуют обязательные параметры"
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера при обработке платежа"
        }
    }
)
async def robokassa_result_webhook(
    request: Request,
    cdek_service: CDEKService = Depends(get_cdek_service),
    order_service: OrderService = Depends(get_order_service),
    payment_service: PaymentService = Depends(get_payment_service)
) -> PlainTextResponse:
    """
    ### Обработчик ResultURL от Робокассы
    
    Выполняет следующие шаги:
    1. Получает форму запроса от Робокассы.
    2. Проверяет контрольную подпись по **Паролю №2** для обеспечения безопасности.
    3. При совпадении подписи переводит статус заказа в `PAID` (Оплачен).
    4. При необходимости регистрирует отправление в службе доставки СДЭК.
    """
    data = await request.form()

    def get_val(key_name: str) -> str | None:
        for k, v in data.items():
            if k.lower() == key_name.lower():
                return v
        return None

    out_sum_str = get_val("OutSum")
    inv_id_str = get_val("InvId")
    signature_value = get_val("SignatureValue")
    shp_user_id_str = get_val("shp_user_id")

    if not all([out_sum_str, inv_id_str, signature_value, shp_user_id_str]):
        logger.error("Робокасса прислала неполный набор параметров: {}".format(list(data.keys())))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Отсутствуют обязательные параметры платежа"
        )

    try:
        inv_id = int(inv_id_str)
        shp_user_id = int(shp_user_id_str)
    except Exception as parse_err:
        logger.error("Ошибка парсинга параметров Робокассы: {}".format(parse_err))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный формат параметров платежа"
        )

    logger.info("Получен вебхук оплаты от Робокассы для заказа ID (InvId): {}, сумма: {}".format(inv_id, out_sum_str))
    
    payment_service.order_service = order_service
    payment_service.cdek_service = cdek_service
    
    try:
        response = await payment_service.process_webhook(
            out_sum=out_sum_str,
            inv_id=inv_id,
            shp_user_id=shp_user_id,
            signature_value=signature_value
        )
        return response
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Ошибка при обработке платежа Робокассы: {}".format(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка обработки платежа")
