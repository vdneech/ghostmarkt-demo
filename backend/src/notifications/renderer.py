from asyncio import selector_events
from datetime import datetime
from logging import getLogger
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.shared.schemas import Locale
from src.config import settings
from src.auth.models import User

logger = getLogger(__name__)

class EmailTemplateRenderer:
    def __init__(self, templates_dir: str = settings.mailings.templates_folder, locale: "Locale" = Locale.RU):
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self._locale = locale

    def _render(self, template_name: str, context: dict) -> str:
        context = {
            **self._get_base_context(),
            **context
        }

        localized_template = f"{self._locale.value}/{template_name}"

        return self._env.get_template(localized_template).render(
            **context,
        )

    def generate_welcome_email(self, user: User) -> str:
        return self._render('welcome.html', {"user": user})

    def generate_otp_email(self, code: str) -> str:
        logger.info("Генерация OTP-письма, код языка {}".format(self._locale.value))
        return self._render('otp.html', {"code": code})

    def generate_otp_subject(self) -> str:
        """Генерирует тему письма для OTP-кода."""
        logger.info("Генерация темы OTP-письма, код языка {}".format(self._locale.value))
        return self._render('otp_subject.html', {}).strip()

    def generate_order_expired_email(self, order_code: str, catalog_url: str, expire_minutes: int) -> str:
        logger.info("Генерация письма об отмене заказа {}, код языка {}".format(order_code, self._locale.value))
        return self._render('order_expired.html', {"order_code": order_code, "catalog_url": catalog_url, "expire_minutes": expire_minutes})

    def generate_order_expired_subject(self, order_code: str) -> str:
        """Генерирует тему письма об отмене заказа."""
        logger.info("Генерация темы письма об отмене заказа {}, код языка {}".format(order_code, self._locale.value))
        return self._render('order_expired_subject.html', {"order_code": order_code}).strip()

    def generate_fallback_text(self) -> str:
        """Генерирует альтернативный текст для клиентов без поддержки HTML."""
        logger.info("Генерация альтернативного текста письма, код языка {}".format(self._locale.value))
        return self._render('fallback.html', {}).strip()

    @staticmethod
    def _get_base_context() -> dict:
        """Динамическое формирование базового контекста."""
        return {
            "logo": settings.frontend.base_url + "/favicon.svg",
            "current_year": datetime.now().year,
        }