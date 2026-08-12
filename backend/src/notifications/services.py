import asyncio
import logging
from email.message import EmailMessage
from typing import TYPE_CHECKING
from abc import abstractmethod, ABC

import aiosmtplib

from src.config import settings
from src.shared.services import Service
from src.auth.dao import UsersDAO
from src.auth.models import User
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, recipient: User, message: str, subject: str = None, fallback: str = None):
        pass


class NotificationService(Service):
    def __init__(self, channels: list[NotificationChannel]):
        self._channels = channels

    async def send_admins(self, session: "AsyncSession", message: str):
        users_dao = UsersDAO(session)
        admins = await users_dao.get_admins()

        async for admin in admins:
            for channel in self._channels:
                await channel.send(admin, message=message)

    async def send(self, recipient: User, message: str, subject: str = None, fallback: str = None):
        for channel in self._channels:
            await channel.send(recipient, message=message, subject=subject, fallback=fallback)


class TelegramChannel(NotificationChannel):
    def __init__(self):
        from src.bot.config import bot
        self._bot = bot

    async def send(self, recipient: User, message: str):
        if recipient.telegram_chat_id:
            await self._bot.send_message(recipient.telegram_chat_id, text=message, parse_mode="HTML")

class EmailChannel(NotificationChannel):
    def __init__(self):
        self._hostname = settings.mailings.hostname.get_secret_value()
        self._port = settings.mailings.port.get_secret_value()
        self._use_tls = settings.mailings.ust_tls.get_secret_value()
        self._username = settings.mailings.username.get_secret_value()
        self._password = settings.mailings.password.get_secret_value()
        self._from_address = settings.mailings.from_address.get_secret_value()


    async def send(self, recipient: User, message: str, subject: str = None, fallback: str = None):
        try:
            logger.info("Попытка отправить сообщение {} по Email".format(recipient.email))
            if not recipient.email:
                raise
            email_message = EmailMessage()
            email_message["From"] = self._from_address
            email_message["To"] = recipient.email
            email_message["Subject"] = subject or "Message from Ghost!"
            email_message.set_content(fallback or "Для просмотра этого письма нужен HTML-клиент.")
            email_message.add_alternative(message, subtype="html")


            use_tls_bool = self._use_tls.lower() in ("true", "1", "yes")
            port_int = int(self._port)
            is_ssl_port = port_int == 465
            username_val = self._username if self._username != "-" else None
            password_val = self._password if self._password != "-" else None

            await aiosmtplib.send(
                email_message,
                hostname=self._hostname,
                port=port_int,
                username=username_val,
                password=password_val,
                use_tls=is_ssl_port if use_tls_bool else False,
                start_tls=not is_ssl_port if use_tls_bool else False
            )
            logger.info("Сообщение для пользователя {} успешно отправлено".format(recipient.email))
        except Exception as e:
            logger.error("При отправке Email-письма произошла ошибка, {}".format(e))