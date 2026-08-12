from decimal import Decimal

from src.orders.schemas import OrderItemCreate
import logging

logger = logging.getLogger(__name__)
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.exc import SQLAlchemyError

from src.shared.dao import BaseDAO
from src.orders.models import Order, PaymentStatus, OrderItem
from src.orders.exceptions import (
    OrderNotFoundError,
)

class OrderItemsDAO(BaseDAO[OrderItem]):
    """
    Класс для управления доступом к позициям заказов (OrderItem).
    Наследует CRUD-операции из BaseDAO.
    """
    model = OrderItem

class OrdersDAO(BaseDAO[Order]):
    """
    Класс для управления доступом к заказам (Order).
    Наследует CRUD-операции из BaseDAO.
    """
    model = Order

    async def update_order_status_by_id(
        self, order_id: int, status: PaymentStatus
    ) -> int:
        """
        Обновляет статус оплаты заказа по его идентификатору ID.
        Неявно вызывает метод flush для фиксации изменений в текущей сессии БД.
        В случае отсутствия заказа генерирует доменное исключение OrderNotFoundError.
        """
        logger.info("Запуск обновления статуса оплаты заказа с ID {} на {}".format(order_id, status.value))
        try:
            query = (
                sqlalchemy_update(self.model)
                .filter_by(id=order_id)
                .values(payment_status=status)
            )
            result = await self._session.execute(query)
            rowcount = result.rowcount

            if rowcount == 0:
                logger.warning("Заказ с ID {} для обновления статуса не найден.".format(order_id))
                raise OrderNotFoundError(
                    f"Заказ с ID {order_id} не найден в базе данных."
                )

            logger.info("Статус заказа {} успешно изменен. Затронуто строк: {}".format(order_id, rowcount))
            await self._session.flush()
            return rowcount

        except SQLAlchemyError as e:
            logger.error("Ошибка SQLAlchemy при обновлении статуса оплаты заказа с ID {}: {}".format(order_id, e))
            raise
