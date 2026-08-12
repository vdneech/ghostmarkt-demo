from uuid import UUID
from src.cdek.exceptions import CDEKDataError, CDEKError, CDEKApiError
from src.cdek.providers import CDEKProvider
from src.shared.services import Service
from typing import TYPE_CHECKING, Any
from httpx import AsyncClient
from src.orders.utils import calculate_dimensions
from src.cdek.schemas import CDEKOrderCreate, CDEKOrderResponse, Recipient, Package, Item, Payment, Phone, RequestState
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from src.orders.models import Order
    from sqlalchemy.orm import Mapped

class CDEKService(Service):
    """
    Сервис для работы с интеграцией CDEK.
    Предоставляет методы для подготовки данных заказа и его регистрации в личном кабинете CDEK.
    """
    def __init__(self, redis: "Redis"):
        """
        Инициализирует CDEK-сервис с Redis клиентом и провайдером CDEK.
        """
        self.provider = CDEKProvider(
            redis=redis,
            http_client=AsyncClient()
        )

    async def register_order(self, data: CDEKOrderCreate) -> CDEKOrderResponse:
        try:
            logger.info("Попытка регистрации заказа в CDEK")
            data_response = await self.provider.post("orders/", data.model_dump(mode="json"))

            response = CDEKOrderResponse.model_validate(data_response)

            last_request = response.requests[-1]
            if last_request.state == RequestState.INVALID:
                logger.info("Заказ CDEK не создан: статус INVALID")
                raise CDEKDataError(
                    message=f"Ошибка: {last_request.state}",
                    errors=last_request.errors
                )
            logger.info("Заказ CDEK создан успешно, со статусом {}".format(last_request.state))
            return response
        except CDEKApiError as e:
            logger.error("API CDEK вернул ошибку: {}".format(e.detail))
            raise CDEKDataError("СДЭК отклонил запрос")

    async def get_info_about_order_by_uuid(self, cdek_uuid: UUID | str) -> CDEKOrderResponse:
        """Узнает информацию о заказе в ИС СДЕК"""
        logger.info("Произведена попытка посмотреть заказ {}".format(cdek_uuid))

        if not cdek_uuid:
            logger.warning("Попытка проверить информацию без данных заказа.")
            raise CDEKDataError("Данные для регистрации заказа в CDEK не предоставлены.")

        try:
            url = f"orders/{cdek_uuid}"
            response = await self.provider.get(
                url=url,
            )
            response = CDEKOrderResponse.model_validate(response)
            return response

        except CDEKApiError as e:
            logger.error("Ошибка при просмотре заказа в CDEK: {}".format(e))
            raise CDEKDataError(
                message="Ошибка при просмотре заказа в CDEK: {}".format(e)
            )

    async def get_info_about_order(
        self,
        cdek_number: str = None,
        im_number: int = None,
    ) -> CDEKOrderResponse:
        """
        Узнает информацию о заказе в ИС СДЕК

        Args:
            cdek_number (str): Номер заказа СДЭК, по которому необходима информация.
            im_number (int): Номер заказа в ИС Клиента, по которому необходима информация (исп. типы из моделей).
        Returns:
            CDEKOrderResponse
        """
        logger.info("Произведена попытка посмотреть заказ по номеру {}".format(cdek_number or im_number))

        if (not cdek_number) and (not im_number):
            logger.warning("Попытка проверить информацию без данных заказа.")
            raise CDEKDataError("Данные для регистрации заказа в CDEK не предоставлены.")

        try:
            url = f"orders/"
            params = {
                "cdek_number": cdek_number,
                "im_number": im_number,
            }
            response = await self.provider.get(
                url=url,
                params=params,
            )
            response = CDEKOrderResponse.model_validate(response)
            return response

        except CDEKApiError as e:
            logger.error("Ошибка при просмотре заказа в CDEK: {}".format(e))
            raise CDEKDataError(
                message="Ошибка при просмотре заказа в CDEK: {}".format(e)
            )

    async def delete_order(self, _uuid: str | UUID = None) -> CDEKOrderResponse:
        logger.info("Произведена попытка удалить заказ по номеру {}".format(_uuid))

        if not _uuid:
            logger.warning("Попытка удалить заказ без данных.")
            raise CDEKDataError("Данные для удаления заказа в CDEK не предоставлены.")

        try:
            url = f"orders/{_uuid}"
            response = await self.provider.delete(
                url=url,
            )
            response = CDEKOrderResponse.model_validate(response)
            return response
        except CDEKApiError as e:
            logger.error("Ошибка при удалении заказа в CDEK: {}".format(e))
            raise CDEKDataError(
                message="Ошибка при удалении заказа в CDEK: {}".format(e)
            )





    @staticmethod
    def prepare_order_to_cdek(
        order: "Order",
        shipment_point: str = None,
        delivery_point: str = None,
        tariff_code: int = None,
    ) -> CDEKOrderCreate:
        """
        Преобразует доменный объект заказа в схему CDEKOrderCreate для последующей отправки в API.
        Автоматически рассчитывает габариты и суммарный вес позиций заказа.
        """
        logger.info("Запуск подготовки данных заказа {} для CDEK".format(order.id))
        try:
            recipient = Recipient(
                name=order.user.fullname,
                phones=[
                    Phone(number=order.user.phone)
                ],
                email=order.user.email,
            )

            items = [
                Item(
                    name=item.product.name,
                    ware_key=str(item.product.id),
                    cost=item.price_at_purchase,
                    weight=item.product.weight,
                    amount=item.quantity,
                    payment=Payment(value=0)
                )
                for item in order.items
            ]

            dimensions = calculate_dimensions(order.items)
            total_weight = sum(item.product.weight * item.quantity for item in order.items)

            package = Package(
                number="1",
                weight=total_weight,
                length=dimensions.length,
                width=dimensions.width,
                height=dimensions.height,
                items=items,
            )

            cdek_order = CDEKOrderCreate(
                number=f"XYZ-VBE-{order.id}",
                shipment_point=shipment_point,
                delivery_point=delivery_point,
                recipient=recipient,
                packages=[
                    package
                ],
                tariff_code=tariff_code,
            )
            logger.info("Подготовка данных заказа {} для CDEK завершена успешно.".format(order.id))
            return cdek_order

        except Exception as e:
            logger.error("Ошибка при подготовке данных заказа для CDEK: {}".format(e))
            raise CDEKDataError(f"Ошибка при подготовке данных заказа для CDEK: {e}")






