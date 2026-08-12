from fastapi import Depends
from src.payments.services import PaymentService
from src.orders.dependencies import get_order_service
from src.cdek.dependencies import get_cdek_service
from src.orders.services import OrderService
from src.cdek.services import CDEKService

def get_payment_service(
    order_service: OrderService = Depends(get_order_service),
    cdek_service: CDEKService = Depends(get_cdek_service),
) -> PaymentService:
    """
    Зависимость для получения экземпляра PaymentService.
    """
    return PaymentService(order_service=order_service, cdek_service=cdek_service)
