from src.shared.schemas import Locale
from src.auth.dao import UsersDAO
from src.notifications.renderer import EmailTemplateRenderer
from src.notifications.services import NotificationService, EmailChannel
import asyncio
from src.shared.celery import app
from src.shared.celery import celery_session_maker




@app.task(
    default_retry_delay=120,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
)
def send_email_otp_notification_task(recipient_id: int, code: str):
    """
    Синхронная обертка для Celery, которая запускает асинхронный контекст
    """
    return asyncio.run(async_send_otp_email(recipient_id, code))


async def async_send_otp_email(recipient_id: int, code: str):

    async with celery_session_maker() as session:
        users_dao = UsersDAO(session)
        recipient = await users_dao.find_one_or_none_by_id(recipient_id)

        renderer = EmailTemplateRenderer(locale=Locale(recipient.locale))
        message = renderer.generate_otp_email(code)
        subject = renderer.generate_otp_subject()
        fallback = renderer.generate_fallback_text()

        notification_service = NotificationService(
            [EmailChannel(),]
        )
        await notification_service.send(recipient, message=message, subject=subject, fallback=fallback)
    pass