import logging
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)
from src.shared.services import Service
from src.config import settings
import hashlib
from decimal import Decimal

from src.orders.schemas import OrderUpdate
from src.orders.models import PaymentStatus, Delivery
from src.notifications.services import NotificationService, TelegramChannel, EmailChannel

class PaymentService(Service):

    def __init__(self, order_service=None, cdek_service=None):
        self.password_1 = settings.robokassa.password_1.get_secret_value()
        self.password_2 = settings.robokassa.password_2.get_secret_value()
        self.merchant_login = settings.robokassa.merchant_login.get_secret_value()
        self.is_test = int(settings.robokassa.is_test)
        self.order_service = order_service
        self.cdek_service = cdek_service

    def generate_payment_url(
        self, order_id: int, cost: Decimal, shp_user_id: int
    ) -> str:
        """
        Генерирует платежную ссылку Робокассы по Паролю №1 с уникальным InvId (равным order_id).
        """
        logger.info(
            "Начало генерации платежной ссылки: order_id=%s, cost=%s, shp_user_id=%s",
            order_id, cost, shp_user_id
        )
        if (not cost) or (cost <= 0):
            raise ValueError("Сумма платежа должна быть больше 0.")

        inv_id = order_id
        cost_str = "{:.2f}".format(cost)
        signature = self.calculate_signature(
            cost=cost,
            inv_id=inv_id,
            shp_user_id=shp_user_id,
        )

        base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
        url = (
            "{}?MerchantLogin={}&OutSum={}&InvId={}&SignatureValue={}&shp_user_id={}&IsTest={}".format(
                base_url, self.merchant_login, cost_str, inv_id, signature, shp_user_id, self.is_test
            )
        )
        logger.info("Сгенерирована платежная ссылка: %s", url)
        return url

    def check_signatures(self, out_sum: str, inv_id: int, shp_user_id: int, signature_value: str) -> bool:
        signature_str = "{}:{}:{}:shp_user_id={}".format(
            out_sum, inv_id, self.password_2, shp_user_id
        )
        calculated_signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

        p2_len = len(self.password_2)
        p2_masked = f"{self.password_2[:2]}...{self.password_2[-2:]}" if p2_len > 4 else "***"
        logged_str = "{}:{}:{}:shp_user_id={}".format(
            out_sum, inv_id, p2_masked, shp_user_id
        )
        logger.info(
            "Проверка подписи вебхука (Password 2): строка='%s', ожидаемая подпись=%s, принятая подпись=%s",
            logged_str, calculated_signature, signature_value
        )

        if calculated_signature.lower() != signature_value.lower():
            logger.warning(
                "Подпись вебхука Робокассы НЕ совпала! Ожидалось: %s, принято: %s",
                calculated_signature, signature_value
            )
            return False
        logger.info("Подпись вебхука Робокассы для заказа %s успешно верифицирована.", inv_id)
        return True

    def calculate_signature(self, cost: Decimal | str, inv_id: int | str, shp_user_id: int | str) -> str:
        cost_str = "{:.2f}".format(Decimal(str(cost)))
        signature_str = "{}:{}:{}:{}:shp_user_id={}".format(
            self.merchant_login, cost_str, inv_id, self.password_1, shp_user_id
        )
        signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

        p1_len = len(self.password_1)
        p1_masked = f"{self.password_1[:2]}...{self.password_1[-2:]}" if p1_len > 4 else "***"
        logged_str = "{}:{}:{}:{}:shp_user_id={}".format(
            self.merchant_login, cost_str, inv_id, p1_masked, shp_user_id
        )
        logger.info(
            "Расчет подписи для ссылки (Password 1): строка='%s', результат=%s",
            logged_str, signature
        )
        return signature

    async def process_webhook(self, out_sum: str, inv_id: int, shp_user_id: int, signature_value: str) -> PlainTextResponse:
        """
        Обрабатывает вебхук от Робокассы: валидирует подпись, обновляет статус заказа и инициирует доставку CDEK.
        Возвращает PlainTextResponse в формате "OK{inv_id}" или вызывает ошибку.
        """
        if not self.order_service:
            raise Exception("OrderService is not provided to PaymentService")

        order = await self.order_service.get_by_id(inv_id)

        if order.payment_status in [PaymentStatus.PAID, PaymentStatus.CANCELED, PaymentStatus.FAILED]:
            return PlainTextResponse("OK{}".format(inv_id))

        if not self.check_signatures(
            out_sum=out_sum,
            inv_id=inv_id,
            shp_user_id=shp_user_id,
            signature_value=signature_value
        ):
            raise ValueError("Неверная подпись платежа")

        if Decimal(str(out_sum)) != Decimal(str(order.total_amount)):
            logger.error(
                "Сумма платежа не совпадает с суммой заказа. Ожидалось: {}, получено: {}".format(
                    order.total_amount, out_sum
                )
            )
            raise ValueError("Сумма платежа не совпадает со стоимостью заказа")

        try:
            order = await self.order_service.update_order(
                data=OrderUpdate(payment_status=PaymentStatus.PAID),
                order_id=inv_id
            )

            notification_service = NotificationService([TelegramChannel()])
            await self.order_service.process_success_payment(order, notification_service)
            logger.info("Заказ {} успешно оплачен и обработан.".format(inv_id))

            if order.delivery == Delivery.CDEK and self.cdek_service:
                logger.info("Инициирована отправка заказа {} в службу CDEK".format(order.id))
                try:
                    cdek_data = self.cdek_service.prepare_order_to_cdek(
                        order=order,
                        shipment_point=settings.cdek.shipment_point,
                        delivery_point=order.delivery_point,
                        tariff_code=order.tariff_code,
                    )
                    cdek_order = await self.cdek_service.register_order(data=cdek_data)
                    if cdek_order:
                        cdek_number = getattr(cdek_order.entity, "cdek_number", None)
                        update_params = {"delivery_id": cdek_order.entity.uuid}
                        if cdek_number:
                            update_params["delivery_code"] = cdek_number
                        order = await self.order_service.update_order(
                            data=OrderUpdate(**update_params),
                            order_id=inv_id
                        )
                        order.delivery_id = cdek_order.entity.uuid
                        if cdek_number:
                            order.delivery_code = cdek_number

                        from src.cdek.schemas import RequestState
                        last_req = cdek_order.requests[-1] if cdek_order.requests else None
                        if last_req and last_req.state == RequestState.ACCEPTED and not cdek_number:
                            from src.orders.tasks import fetch_cdek_tracking_code_task
                            fetch_cdek_tracking_code_task.apply_async(args=[order.id], countdown=180)
                            logger.info("Запущена Celery-таска на получение cdek_number для заказа {}".format(order.id))
                    else:
                        logger.error("Не удалось зарегистрировать заказ {} в CDEK".format(order.id))
                except Exception as cdek_exc:
                    logger.error("Ошибка при регистрации в CDEK для заказа {}: {}".format(order.id, cdek_exc))

            return PlainTextResponse("OK{}".format(inv_id), status_code=200)

        except Exception as e:
            logger.error("Ошибка при обработке успешной оплаты заказа {}: {}".format(inv_id, e))
            raise
