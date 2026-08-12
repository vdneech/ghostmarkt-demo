from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)
from src.shared.dao import BaseDAO
from src.products.models import Product

class ProductsDAO(BaseDAO[Product]):
    """
    Класс для управления доступом к данным товаров (Product).
    Наследует базовые CRUD-операции из BaseDAO.
    """
    model = Product

    async def decrease_quantity(self, product_id: int, count: int) -> int:
        """
        Уменьшает количество товара на складе на заданную величину count.
        Неявно вызывает метод flush для фиксации изменений в текущей сессии БД.
        """
        logger.info("Запрос на уменьшение остатков товара с ID {} на {} единиц".format(product_id, count))
        try:
            query = (
                update(Product)
                .where(Product.id == product_id, Product.quantity >= count)
                .values(quantity=Product.quantity - count)
            )
            result = await self._session.execute(query)
            rowcount = result.rowcount
            await self._session.flush()
            logger.info("Остатки товара {} успешно уменьшены. Изменено строк в БД: {}".format(product_id, rowcount))
            return rowcount
        except SQLAlchemyError as e:
            logger.error("Ошибка при обновлении остатков товара с ID {}: {}".format(product_id, e))
            raise

    async def increase_quantity(self, product_id: int, count: int) -> int:
        """
        Увеличивает количество товара на складе на заданную величину count.
        Неявно вызывает метод flush для фиксации изменений в текущей сессии БД.
        """
        logger.info("Запрос на увеличение остатков товара с ID {} на {} единиц".format(product_id, count))
        try:
            query = (
                update(Product)
                .where(Product.id == product_id)
                .values(quantity=Product.quantity + count)
            )
            result = await self._session.execute(query)
            rowcount = result.rowcount
            await self._session.flush()
            logger.info("Остатки товара {} успешно увеличены. Изменено строк в БД: {}".format(product_id, rowcount))
            return rowcount
        except SQLAlchemyError as e:
            logger.error("Ошибка при обновлении остатков товара с ID {}: {}".format(product_id, e))
            raise