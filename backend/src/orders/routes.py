import logging
from fastapi import APIRouter, Depends, status, Query

from src.orders.schemas import OrderUpdate
from src.orders.dependencies import get_order_service
from src.orders.models import PaymentStatus
from src.auth.dependencies import get_current_superuser, get_current_user
from src.orders.exceptions import OrderDomainError
from src.orders.schemas import OrderCreate, OrderResponse
from src.orders.services import OrderService
from src.auth.models import User
from src.orders.webhooks.create_order import router as create_order_webhook_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["Orders"])
router.include_router(create_order_webhook_router)

@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заказ",
    responses={
        status.HTTP_201_CREATED: {
            "description": "Заказ успешно создан",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Ошибка валидации или нехватка товаров на складе",
            "content": {"application/json": {"example": {"detail": "Недостаточно товара с ID 1 на складе. Запрошено: 2, доступно: 1"}}}
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
            "content": {"application/json": {"example": {"detail": "Сессия устарела или токен отсутствует"}}}
        }
    }
)
async def create_order(
    order_data: OrderCreate,
    order_service: OrderService = Depends(get_order_service),
    user: User = Depends(get_current_user),
) -> OrderResponse:
    """
    Создает новый заказ в системе для авторизованного пользователя на основе позиций корзины.
    Автоматически списывает товары со склада и резервирует доставку.
    """
    logger.info("Вход в роут создания заказа. Пользователь: {}".format(user.id))
    order = await order_service.create_order(
        user=user,
        data=order_data
    )
    logger.info("Заказ успешно создан. ID заказа: {}".format(order.id))
    return order


@router.get(
    "/",
    response_model=list[OrderResponse],
    status_code=status.HTTP_200_OK,
    summary="Получить список заказов",
    responses={
        status.HTTP_200_OK: {
            "description": "Список заказов успешно получен",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        }
    }
)
async def get_all_orders(
    service: OrderService = Depends(get_order_service),
    user: User = Depends(get_current_user),
) -> list[OrderResponse]:
    """
    Возвращает список всех заказов. 
    Администратор получает вообще все заказы в системе, обычный пользователь – только свои собственные.
    """
    logger.info("Вход в роут списка заказов. Запрос от пользователя: {}, роль superuser: {}".format(user.id, user.is_superuser))
    
    if user.is_superuser:
        orders = await service.get_many()
    else:
        orders = await service.get_many(user.id)

    logger.info("Возвращено {} заказов в роуте.".format(len(orders)))
    return [OrderResponse.model_validate(order) for order in orders]


@router.patch(
    "/{order_id}/",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Обновить статус заказа",
    responses={
        status.HTTP_200_OK: {
            "description": "Статус заказа успешно обновлен",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав (не админ)",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Заказ не найден",
            "content": {"application/json": {"example": {"detail": "Заказ с ID 123 не найден"}}}
        }
    }
)
async def update_order_status(
    order_id: int,
    status_val: PaymentStatus | None = Query(None, alias="status"),
    delivery_code: str | None = None,
    service: OrderService = Depends(get_order_service),
    admin: User = Depends(get_current_superuser),
) -> OrderResponse:
    """
    Обновляет статус оплаты и/или трэк-номер (код доставки) заказа.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут обновления статуса заказа {} от администратора {}. Статус: {}, Код доставки: {}".format(
        order_id, admin.id, status_val, delivery_code
    ))
    
    update_data = OrderUpdate()
    if status_val is not None:
        update_data.payment_status = status_val
    if delivery_code is not None:
        update_data.delivery_code = delivery_code

    order = await service.update_order(
        data=update_data,
        order_id=order_id,
    )
    logger.info("Заказ {} успешно обновлен.".format(order_id))
    return OrderResponse.model_validate(order)


@router.get(
    "/{order_id}/",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Получить заказ по ID",
    responses={
        status.HTTP_200_OK: {
            "description": "Информация о заказе получена",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Отказ в доступе (попытка просмотра чужого заказа)",
            "content": {"application/json": {"example": {"detail": "Вы не имеете прав на просмотр этого заказа."}}}
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Заказ не найден",
            "content": {"application/json": {"example": {"detail": "Заказ не найден"}}}
        }
    }
)
async def get_order(
    order_id: int,
    order_service: OrderService = Depends(get_order_service),
    user: User = Depends(get_current_user),
) -> OrderResponse:
    """
    Возвращает детальную информацию о конкретном заказе.
    Обычный пользователь имеет право видеть только свои собственные заказы. Администратор видит любые.
    """
    logger.info("Вход в роут получения деталей заказа {} от пользователя {}".format(order_id, user.id))
    order = await order_service.get_by_id(order_id)

    if not (user.is_superuser or (order.user and order.user.id == user.id)):
        logger.warning("Отказ в доступе: пользователь {} пытался посмотреть чужой заказ {}".format(user.id, order_id))
        raise OrderDomainError("Вы не имеете прав на просмотр этого заказа.")

    logger.info("Детали заказа {} успешно получены.".format(order_id))
    return order


@router.delete(
    "/{order_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить заказ",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Заказ успешно удален",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Заказ не найден",
            "content": {"application/json": {"example": {"detail": "Заказ не найден"}}}
        }
    }
)
async def delete_order(
    order_id: int,
    service: OrderService = Depends(get_order_service),
    admin: User = Depends(get_current_superuser),
) -> None:
    """
    Удаляет заказ из системы по его идентификатору.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут удаления заказа {} от администратора {}".format(order_id, admin.id))
    await service.delete(order_id)
    logger.info("Заказ {} успешно удален через роут.".format(order_id))
    return


