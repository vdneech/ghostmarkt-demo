import asyncio
import logging
from sqlalchemy.orm import selectinload
from src.orders.services import OrderService
from src.orders.models import Order, PaymentStatus
from src.shared.celery import celery_session_maker, app

logger = logging.getLogger(__name__)

@app.task(
    default_retry_delay=60,
    max_retries=2,
)
def cancel_expired_order_task(order_id: int):
    """Celery task to automatically cancel unpaid order after inactivity window.

    Args:
        order_id (int): System ID of the order to check and cancel.

    Returns:
        None
    """
    return asyncio.run(cancel_expired_order(order_id))

async def cancel_expired_order(order_id: int):
    """Checks order payment status and cancels it if still pending.

    Retrieves order details with user relationship, switches its status
    to CANCELED if unpaid, and sends email notification to the user.

    Args:
        order_id (int): Database identifier of the order.

    Returns:
        None
    """
    async with celery_session_maker() as session:
        order_service = OrderService(session)
        try:
            order_db = await order_service.dao.find_one_or_none_by_id(
                order_id,
                selectinload(Order.user)
            )

            if not order_db:
                logger.warning(f"Order {order_id} not found in database for expiration check.")
                return

            if order_db.payment_status == PaymentStatus.PENDING:
                await order_service.cancel_order(order_id=order_id)
                logger.info(f"Order {order_id} automatically canceled after inactivity window.")

                if order_db.user and order_db.user.email:
                    try:
                        from src.notifications.renderer import EmailTemplateRenderer
                        from src.notifications.services import NotificationService, EmailChannel
                        from src.shared.schemas import Locale
                        from src.config import settings

                        recipient_locale = order_db.user.locale or Locale.RU
                        catalog_url = f"{settings.frontend.base_url}/catalog"

                        renderer = EmailTemplateRenderer(locale=recipient_locale)
                        email_html = renderer.generate_order_expired_email(
                            order_code=order_db.code,
                            catalog_url=catalog_url,
                            expire_minutes=settings.order.expiration_time // 60
                        )
                        subject = renderer.generate_order_expired_subject(order_code=order_db.code)
                        fallback = renderer.generate_fallback_text()

                        notification_service = NotificationService([EmailChannel()])
                        await notification_service.send(order_db.user, message=email_html, subject=subject, fallback=fallback)
                        logger.info(f"Sent order_expired notification email to user {order_db.user.email} for order {order_db.code}")
                    except Exception as notify_err:
                        logger.error(f"Failed to send expiration notification to user for order {order_id}: {notify_err}")
            else:
                logger.info(f"Order {order_id} is in status {order_db.payment_status.value}, skipping automatic cancellation.")
        except Exception as e:
            logger.error(f"Error during automatic cancellation of order {order_id}: {e}")


class CdekNumberNotFoundError(Exception):
    """Exception raised when CDEK order tracking number is not found."""
    pass


async def fetch_cdek_tracking_code(order_id: int) -> None:
    """Fetch CDEK tracking number for an order by its delivery UUID.

    Args:
        order_id: System identifier of the order.

    Raises:
        CdekNumberNotFoundError: If the tracking number is missing in CDEK's database.
    """
    async with celery_session_maker() as session:
        from src.cdek.services import CDEKService
        from src.shared.redis import get_redis_client
        from src.config import settings

        order_service = OrderService(session)
        order = await order_service.dao.find_one_or_none_by_id(order_id)
        if not order:
            logger.warning("Order {} not found for CDEK tracking fetch".format(order_id))
            return

        if order.delivery_code:
            logger.info("Order {} already has CDEK tracking code: {}".format(order_id, order.delivery_code))
            return

        if not order.delivery_id:
            logger.warning("Order {} has no CDEK delivery ID".format(order_id))
            return

        redis_client = await get_redis_client(database=settings.redis.databases.cdek)
        cdek_service = CDEKService(redis_client)
        cdek_response = await cdek_service.get_info_about_order_by_uuid(order.delivery_id)
        cdek_number = None
        if cdek_response and getattr(cdek_response, "entity", None):
            cdek_number = getattr(cdek_response.entity, "cdek_number", None)

        if cdek_number:
            order.delivery_code = cdek_number
            await session.commit()
            logger.info("Successfully updated order {} with CDEK tracking number {}".format(order_id, cdek_number))
        else:
            logger.warning("CDEK tracking number not assigned yet for order {}".format(order_id))
            raise CdekNumberNotFoundError("Tracking number not assigned yet")


@app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=180,
)
def fetch_cdek_tracking_code_task(self, order_id: int) -> None:
    """Celery task to fetch CDEK tracking number and assign it to an order.

    Args:
        order_id: System ID of the order.

    Raises:
        self.retry: Triggers Celery task retry.
    """
    try:
        return asyncio.run(fetch_cdek_tracking_code(order_id))
    except Exception as exc:
        logger.warning("Retrying fetch_cdek_tracking_code_task for order {} due to: {}".format(order_id, exc))
        raise self.retry(exc=exc)