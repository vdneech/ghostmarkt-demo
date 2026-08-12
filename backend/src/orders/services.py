from src.orders.schemas import OrderUpdate
from src.cdek.services import CDEKService
from src.shared.cache import clear_cache
from src.orders.schemas import UserOrderCreate
from src.orders.models import OrderItem
from src.products.dao import ProductsDAO
from src.orders.dao import OrderItemsDAO
from src.payments.services import PaymentService
from src.orders.exceptions import OutOfStockError, MetadataValidationError
from src.auth.models import Locale

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.orders.dao import OrdersDAO
from src.orders.models import Order, PaymentStatus
from src.orders.schemas import OrderCreate, OrderResponse
from src.orders.exceptions import (
    OrderNotFoundError,
    ProductNotFoundError,
    OutOfStockError,
    MetadataValidationError,
    OrderDomainError,
)
from src.products.models import Product
from src.shared.services import SessionService

from aiogram.exceptions import TelegramBadRequest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.notifications.services import NotificationService
    from src.auth.models import User


class OrderService(SessionService):
    """
    Сервис для работы с заказами (Order).
    Реализует бизнес-логику создания заказа, проведения оплаты,
    отмены заказа и отправки уведомлений администраторам и пользователям.
    """
    def __init__(self, session: "AsyncSession", cdek_service: Optional[CDEKService] = None):
        """
        Инициализирует сервис заказа с сессией базы данных, платежным сервисом, CDEK-сервисом и DAO.
        """
        self._session = session
        self.dao = OrdersDAO(session)
        self.payment_service = PaymentService()
        self.items_dao = OrderItemsDAO(session)
        self.products_dao = ProductsDAO(session)
        self._cdek_service = cdek_service

    async def get_many(self, user_id: int = None) -> list[OrderResponse]:
        """
        Получает список заказов в системе. Если передан параметр user_id,
        возвращаются заказы только указанного пользователя.
        """
        logger.info("Запрос на получение списка заказов. Фильтр user_id: {}".format(user_id))
        if user_id:
            orders = await self.dao.find_all(
                selectinload(self.dao.model.items),
                selectinload(self.dao.model.user),
                user_id=user_id
            )
        else:
            orders = await self.dao.find_all(
                selectinload(self.dao.model.items),
                selectinload(self.dao.model.user)
            )

        logger.info("Успешно извлечено {} заказов.".format(len(orders)))
        return [OrderResponse.model_validate(order) for order in orders]

    async def get_by_id(self, order_id: int) -> OrderResponse:
        """
        Получает детальную информацию о заказе по его уникальному идентификатору ID.
        При отсутствии заказа возбуждает доменное исключение OrderNotFoundError.
        """
        logger.info("Запрос на получение деталей заказа по ID: {}".format(order_id))
        order = await self.dao.find_one_or_none_by_id(
            order_id,
            selectinload(self.dao.model.items),
            selectinload(self.dao.model.user),
        )
        if not order:
            logger.warning("Заказ с ID {} не найден.".format(order_id))
            raise OrderNotFoundError("Заказ не найден")
        logger.info("Заказ с ID {} успешно получен.".format(order_id))

        if order.delivery_id and not order.delivery_code:
            logger.info("Попытка узнать номер заказа CDEK API")
            try:
                delivery_code = await self._cdek_service.get_info_about_order_by_uuid(
                    order.delivery_id
                )
                if delivery_code and getattr(delivery_code, 'entity', None) and getattr(delivery_code.entity, 'cdek_number', None):
                    order.delivery_code = delivery_code.entity.cdek_number
                    await self._session.commit()
            except Exception as e:
                logger.error("Не удалось получить cdek_number из API CDEK: {}".format(e))

        return OrderResponse.model_validate(order)

    async def create_order(
        self,
        user: "User",
        data: OrderCreate | UserOrderCreate
    ) -> OrderResponse:
        """
        Создает новый заказ в системе, рассчитывает суммарную стоимость,
        формирует ссылку на оплату в Робокассе и регистрирует доставку в CDEK при необходимости.
        Неявно фиксирует изменения в БД (commit) при успехе или откатывает сессию (rollback) при ошибках.
        """
        logger.info("Запуск создания заказа для пользователя {}".format(user.id))
        try:
            from src.products.services import InventoryService
            inventory_service = InventoryService(self._session)

            products = await self.products_dao.find_all_by_ids(
                [item.product_id for item in data.items]
            )

            products_map = {product.id: product for product in products}
            total = 0

            order = await self.dao.add(
                user_id=user.id,
                address=data.address,
                total_amount=0,
                items=[],
                shipment_cost=data.shipment_cost,
                tariff_code=data.tariff_code,
                delivery_point=data.delivery_point,
                delivery=data.delivery,
            )

            for item in data.items:
                product = products_map.get(item.product_id)

                if not product:
                    logger.warning("Позиция заказа содержит несуществующий товар с ID {}".format(item.product_id))
                    raise ProductNotFoundError(item.product_id)

                if not product.is_active:
                    logger.warning("Попытка заказа деактивированного товара: ID {}".format(item.product_id))
                    raise OrderDomainError(f"Товар с ID {item.product_id} деактивирован и недоступен для заказа.")

                if product.quantity <= 0:
                    logger.warning("Попытка заказа товара с нулевым остатком на складе: ID {}".format(item.product_id))
                    raise OutOfStockError(
                        product_id=item.product_id,
                        requested=item.quantity,
                        available=product.quantity,
                    )

                if product.quantity < item.quantity:
                    logger.warning("Недостаточно товара с ID {} на складе при попытке создания заказа. Требуется: {}, доступно: {}".format(
                        item.product_id, item.quantity, product.quantity
                    ))
                    raise OutOfStockError(
                        product_id=item.product_id,
                        requested=item.quantity,
                        available=product.quantity,
                    )

                item_cost = product.price * item.quantity
                total += item_cost

                if product.meta:
                    if not item.meta:
                        if isinstance(product.meta, dict):
                            required_labels = list(product.meta.values())
                        else:
                            required_labels = []
                            for meta_item in product.meta:
                                if isinstance(meta_item, dict):
                                    values = meta_item.get("values", {})
                                else:
                                    values = meta_item.values
                                ru_label = values.get("ru") or values.get(Locale.RU) or (list(values.values())[0] if values else None)
                                required_labels.append(ru_label or "Неизвестный параметр")
                        raise MetadataValidationError(
                            message="Отсутствуют обязательные параметры: {}".format(", ".join(required_labels)),
                            missing_fields=set(required_labels),
                        )
                    
                    if isinstance(product.meta, dict):
                        required_keys = set(product.meta.keys())
                        missing_keys = required_keys - set(item.meta.keys())
                        if missing_keys:
                            required_labels = [product.meta[k] for k in missing_keys]
                            raise MetadataValidationError(
                                message="Отсутствуют обязательные параметры: {}".format(", ".join(required_labels)),
                                missing_fields=set(required_labels),
                            )
                    else:
                        missing_labels = []
                        for meta_item in product.meta:
                            if isinstance(meta_item, dict):
                                key = meta_item.get("key")
                                values = meta_item.get("values", {})
                            else:
                                key = meta_item.key
                                values = meta_item.values
                            if key not in item.meta:
                                ru_label = values.get("ru") or values.get(Locale.RU) or (list(values.values())[0] if values else None)
                                missing_labels.append(ru_label or key)
                        if missing_labels:
                            raise MetadataValidationError(
                                message="Отсутствуют обязательные параметры: {}".format(", ".join(missing_labels)),
                                missing_fields=set(missing_labels),
                            )

                await inventory_service.subtract(product_id=item.product_id, count=item.quantity)

                order.items.append(
                    OrderItem(
                        product=product,
                        quantity=item.quantity,
                        price_at_purchase=product.price,
                        meta=item.meta,
                    )
                )

            discount_amount = Decimal("0")
            promo_code_applied = None

            if getattr(data, "promo_code", None):
                from src.products.models import PromoCode
                stmt = select(PromoCode).where(PromoCode.code == data.promo_code)
                result = await self._session.execute(stmt)
                promo = result.scalar_one_or_none()

                if not promo:
                    raise OrderDomainError("Промокод не найден")

                if promo.expires_at is not None:
                    now = datetime.now(promo.expires_at.tzinfo or timezone.utc)
                    if now > promo.expires_at:
                        raise OrderDomainError("Срок действия промокода истек")

                if promo.max_usages is not None and promo.usages_count >= promo.max_usages:
                    raise OrderDomainError("Промокод полностью использован")

                if promo.discount is not None:
                    if promo.discount > total:
                        raise OrderDomainError(f"Сумма заказа ({total} ₽) меньше суммы скидки ({promo.discount} ₽)")
                    discount_amount = promo.discount
                else:
                    discount_amount = (total * Decimal(promo.discount_percent) / Decimal(100)).quantize(Decimal("1.00"))

                promo.usages_count += 1
                promo_code_applied = promo.code

            if getattr(data, "discount", None) is not None:
                if Decimal(str(data.discount)) != discount_amount:
                    raise OrderDomainError("Указанная сумма скидки не совпадает с расчетной")

            if order.shipment_cost is None:
                order.shipment_cost = Decimal("0")
            
            final_products_total = max(Decimal("0"), total - discount_amount)
            order.total_amount = final_products_total + order.shipment_cost
            order.promo_code = promo_code_applied
            order.discount = discount_amount

            url = self.payment_service.generate_payment_url(
                order_id=order.id,
                cost=order.total_amount,
                shp_user_id=order.user_id,
            )
            order.payment_url = url

            logger.info("Создан черновик заказа {}. Общая сумма: {}".format(order.id, total))

            await self._session.commit()
            await self._session.refresh(order, attribute_names=["user", "items"])
            logger.info("Заказ {} успешно создан и зафиксирован в БД (commit).".format(order.id))

            try:
                from src.orders.tasks import cancel_expired_order_task
                from src.config import settings
                exp_seconds = settings.order.expiration_time
                cancel_expired_order_task.apply_async(args=[order.id], countdown=exp_seconds)
                logger.info("Celery-таска на авто-отмену заказа {} через {} сек. запланирована.".format(order.id, exp_seconds))
            except Exception as cel_err:
                logger.error("Не удалось запланировать Celery-таску на авто-отмену заказа {}: {}".format(order.id, cel_err))

            response = OrderResponse.model_validate(order)
            response.payment_url = url
            return response

        except (OutOfStockError, ProductNotFoundError, MetadataValidationError) as e:
            logger.warning("Ошибка валидации при создании заказа: {}".format(e))
            await self._session.rollback()
            raise
        except Exception as e:
            logger.error("Критическая непредвиденная ошибка при создании заказа: {}".format(e))
            await self._session.rollback()
            raise

    async def set_telegram_message_id(self, order_id: int, message_id: int) -> None:
        """
        Устанавливает идентификатор сообщения Telegram для созданного заказа.
        """
        try:
            await self.dao.update_returning(
                filters={"id": order_id},
                values={"telegram_message_id": message_id}
            )
            await self._session.commit()
            logger.info("Для заказа {} успешно установлен telegram_message_id: {}".format(order_id, message_id))
        except Exception as e:
            await self._session.rollback()
            logger.error("Не удалось сохранить telegram_message_id {} для заказа {}: {}".format(message_id, order_id, e))

    @staticmethod
    def validate_and_parse_meta(text: str, product: Product) -> dict[str, str]:
        """
        Парсит текстовые мета-данные о характеристиках товара, присланные пользователем,
        и сверяет их со списком требуемых параметров в карточке товара.
        Возбуждает MetadataValidationError, если обязательные параметры отсутствуют.
        """
        if not product.meta:
            return {}

        parsed_data = {}
        for line in text.split("\n"):
            if ":" in line:
                label, value = line.split(":", 1)
                if value.strip():
                    parsed_data[label.strip().lower()] = value.strip()

        result_meta = {}
        missing_fields = []

        if isinstance(product.meta, dict):
            for key, val in product.meta.items():
                val_clean = val.strip().lower()
                if val_clean in parsed_data:
                    result_meta[key] = parsed_data[val_clean]
                else:
                    missing_fields.append(val)
        else:
            for item in product.meta:
                if isinstance(item, dict):
                    key = item.get("key")
                    values = item.get("values", {})
                else:
                    key = item.key
                    values = item.values

                ru_label = values.get("ru") or values.get(Locale.RU) or (list(values.values())[0] if values else None)
                en_label = values.get("en") or values.get(Locale.EN)

                matched_value = None
                if ru_label and ru_label.strip().lower() in parsed_data:
                    matched_value = parsed_data[ru_label.strip().lower()]
                elif en_label and en_label.strip().lower() in parsed_data:
                    matched_value = parsed_data[en_label.strip().lower()]

                if matched_value is not None:
                    result_meta[key] = matched_value
                else:
                    display_label = ru_label or en_label or key
                    missing_fields.append(display_label)

        if missing_fields:
            raise MetadataValidationError(
                message="Отсутствуют обязательные параметры: {}".format(", ".join(missing_fields)),
                missing_fields=set(missing_fields),
            )

        return result_meta

    async def cancel_order(self, order_id: int) -> None:
        """
        Отменяет оформленный заказ и переводит его статус оплаты в CANCELED.
        Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Запрос на отмену заказа ID: {}".format(order_id))
        try:
            order = await self.dao.find_one_or_none_by_id(
                order_id,
                selectinload(self.dao.model.items)
            )
            if not order:
                raise OrderNotFoundError(f"Заказ с ID {order_id} не найден.")

            if order.payment_status == PaymentStatus.CANCELED:
                logger.info("Заказ {} уже находится в статусе CANCELED.".format(order_id))
                return

            from src.products.services import InventoryService
            inventory_service = InventoryService(self._session)
            for item in order.items:
                await inventory_service.add(product_id=item.product_id, count=item.quantity)

            await self.dao.update_order_status_by_id(
                order_id=order_id, status=PaymentStatus.CANCELED
            )
            await self._session.commit()
            await clear_cache("products")
            logger.info("Заказ {} успешно отменен и зафиксирован (commit).".format(order_id))
        except OrderNotFoundError:
            await self._session.rollback()
            raise
        except Exception as e:
            logger.error("Не удалось отменить заказ {}: {}".format(order_id, e))
            await self._session.rollback()
            raise

    async def delete(self, order_id: int) -> None:
        """
        Удаляет заказ из системы. Предварительно выполняет проверку его существования.
        Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Запрос на удаление заказа ID: {}".format(order_id))
        try:
            await self.get_by_id(order_id)
            await self.dao.delete(id=order_id)
            await self._session.commit()
            await clear_cache("products")
            logger.info("Заказ {} успешно удален (commit).".format(order_id))
        except OrderNotFoundError:
            await self._session.rollback()
            raise
        except Exception as e:
            logger.error("Не удалось удалить заказ {}: {}".format(order_id, e))
            await self._session.rollback()
            raise

    async def finalize_order(self, message_id: int, order_id: int) -> None:
        """
        Присваивает созданному заказу ID соответствующего сообщения в Telegram
        для отслеживания состояния оплаты. Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Финальное закрепление telegram_message_id {} за заказом {}".format(message_id, order_id))
        await self.dao.update(
            filters={"id": order_id}, values={"telegram_message_id": message_id}
        )
        await self._session.commit()
        logger.info("Заказ {} успешно привязан к сообщению {} (commit).".format(order_id, message_id))

    async def update_order(
        self,
        data: OrderUpdate,
        order_id: int
    ) -> Order:
        """
        Обновляет статус оплаты заказа. При переходе в статус PAID
        автоматически выставляет дату и время совершения платежа.
        Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Обновление заказа {}, данными {}".format(order_id, data.model_dump()))

        to_update = {
            **data.model_dump(exclude_unset=True),
        }
        if data.payment_status == PaymentStatus.PAID:
            to_update["payment_date"] = datetime.now(timezone.utc)

        try:
            order = await self.dao.find_one_or_none_by_id(
                order_id,
                selectinload(self.dao.model.items),
            )
            if not order:
                raise OrderNotFoundError(f"Заказ с ID {order_id} не найден.")



            updated = await self.dao.update_returning(
                selectinload(self.dao.model.items).joinedload(OrderItem.product),
                selectinload(self.dao.model.user),
                filters={"id": order_id}, values=to_update,
            )
            if not updated:
                raise OrderNotFoundError(f"Заказ с ID {order_id} не найден.")
            await self._session.commit()
            await clear_cache("products")
            logger.info("Заказ {} изменен. Данные {} (commit).".format(order_id, data.model_dump()))
            return updated
        except Exception as e:
            logger.error("Ошибка при обновлении статуса оплаты заказа {}: {}".format(order_id, e))
            await self._session.rollback()
            raise


    async def process_success_payment(
        self, order: Order, notification_service: "NotificationService"
    ) -> None:
        """
        Запускает бизнес-процедуры после получения подтверждения оплаты:
        удаляет платежные виджеты, рассылает сообщения администраторам и пользователю.
        """
        logger.info("Запуск процедур постоплаты для успешного заказа {}".format(order.id))
        await self._delete_payment_message(order)

        if order.user.telegram_chat_id:
            from src.bot.config import bot
            from src.config import settings
            from src.bot import texts
            try:
                msg_text = texts.render_order_paid(settings.frontend.base_url)
                await bot.send_message(
                    chat_id=order.user.telegram_chat_id,
                    text=msg_text,
                    parse_mode="HTML"
                )
                logger.info("Отправлено сообщение об оплате пользователю с telegram_chat_id: {}".format(order.user.telegram_chat_id))
            except Exception as tg_err:
                logger.error("Не удалось отправить сообщение об успешной оплате пользователю {}: {}".format(order.user.telegram_chat_id, tg_err))

        await self._notify_admins(order, notification_service)

    @staticmethod
    async def _delete_payment_message(order: Order) -> None:
        """
        Удаляет интерактивное сообщение об оплате в чате пользователя.
        """
        if not order.telegram_message_id:
            return

        from src.bot.config import bot
        logger.info("Попытка удаления сообщения {} у пользователя {}".format(order.telegram_message_id, order.user.telegram_chat_id))
        try:
            await bot.delete_message(
                order.user.telegram_chat_id, order.telegram_message_id
            )
            logger.info("Сообщение {} удалено успешно.".format(order.telegram_message_id))
        except TelegramBadRequest as e:
            logger.warning("Не удалось удалить сообщение {} для заказа {} (уже удалено или не существует): {}".format(order.telegram_message_id, order.id, e))
        except Exception as e:
            logger.error("Критический сбой API Telegram при удалении сообщения для заказа {}: {}".format(order.id, e))

    async def _notify_admins(
        self, order: Order, notification_service: "NotificationService"
    ) -> None:
        """
        Рассылает оповещения о новом оплаченном заказе администраторам магазина в Telegram.
        """
        if not notification_service:
            return
        logger.info("Отправка уведомления администраторам о заказе {}".format(order.id))
        try:
            from src.bot import texts

            message = texts.render_order_notification(order)
            await notification_service.send_admins(
                session=self._session, message=message
            )
            logger.info("Уведомление успешно доставлено администраторам.")
        except Exception as e:
            logger.error("Ошибка рассылки уведомлений администраторам об оплате заказа {}: {}".format(order.id, e))

    @staticmethod
    async def _notify_user(
        order: Order, notification_service: "NotificationService"
    ) -> None:
        """
        Отправляет пользователю квитанцию и подтверждение об успешной оплате заказа в Telegram.
        """
        if not notification_service:
            return
        logger.info("Отправка чека/квитанции пользователю ID {} в Telegram".format(order.user.id))
        try:
            text = (
                f"Ваш заказ №{order.id} успешно оплачен!\n"
                f"Сумма: {order.total_amount} руб.\n"
                f"Мы уже начали собирать вашу посылку."
            )
            await notification_service.send(order.user, text)
            logger.info("Пользователь успешно уведомлен об оплате.")
        except TelegramBadRequest as e:
            logger.error("Не удалось уведомить пользователя {} (пользователь заблокировал бота): {}".format(order.user.id, e))
        except Exception as e:
            logger.error("Критическая ошибка при отправке уведомления пользователю {}: {}".format(order.user.id, e))





