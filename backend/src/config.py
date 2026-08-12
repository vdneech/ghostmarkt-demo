import logging
from pathlib import Path
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging.config

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

class DatabaseSettings(BaseSettings):
    """Настройки базы данных PostgreSQL. Описывают пути и url подключения."""

    db: SecretStr = Field(description="Название базы", default="db")
    user: SecretStr = Field(description="Пользователь базы", default="db_user")
    password: SecretStr = Field(description="Пароль базы", default="db_password")
    host: str = "localhost"
    port: int = 5432
    echo: bool = False

    @property
    def async_url(self) -> str:
        """Генерирует асинхронный URL для подключения SQLAlchemy."""
        return "postgresql+asyncpg://{}:{}@{}/{}".format(
            self.user.get_secret_value(),
            self.password.get_secret_value(),
            f"{self.host}:{self.port}",
            self.db.get_secret_value(),
        )

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


class RobokassaSettings(BaseModel):
    """Настройки интеграции с платежной системой Робокасса."""

    merchant_login: SecretStr = Field(default=SecretStr(""), description="Идентификатор магазина")
    password_1: SecretStr = Field(default=SecretStr(""), description="Пароль #1 для формирования ссылок")
    password_2: SecretStr = Field(default=SecretStr(""), description="Пароль #2 для проверки вебхуков")
    is_test: int = Field(default=1, description="Флаг тестового режима (1 - включен, 0 - выключен)")


class LegalSettings(BaseModel):
    """Настройки для юридической информации и документов."""

    offer_url: str = Field(
        default="https://your_policy_url.com",
        description="Ссылка на публичную оферту"
    )
    google_docs_url: str = Field(
        default="https://your_policy_url.com",
        description="Ссылка на документацию в Google Docs"
    )


class BotSettings(BaseModel):
    """Настройки телеграм-бота."""

    webhook_secret_token: SecretStr = Field(..., description="Секретный токен для проверки вебхуков от Telegram")
    token: SecretStr = Field(..., description="Токен Telegram бота")


class RedisDatabaseSettings(BaseModel):
    """Индексы баз данных в Redis для разных нужд."""
    
    fsm: int = Field(default=0, description="БД для машины состояний")
    otp: int = Field(default=1, description="БД для хранения одноразовых паролей")
    cdek: int = Field(default=2, description="БД для кеширования токенов СДЭК")

    celery: int = Field(default=3, description="БД для Celery")
    celery_backend: int = Field(default=4, description="БД для Celery Backend")
    cache: int = Field(default=5, description="БД для Celery Backend")


class RedisSettings(BaseModel):
    """Настройки подключения к Redis-серверу."""

    host: str = Field(..., description="Хост Redis")
    port: int = Field(..., description="Порт Redis")
    decode_responses: bool = Field(default=True, description="Декодировать ответы в строки")
    databases: RedisDatabaseSettings = Field(default_factory=RedisDatabaseSettings, description="Индексы БД Redis")

    def get_url(self, db: int) -> str:
        """Возвращает URL для подключения к конкретной БД Redis."""
        return "redis://{}:{}/{}".format(self.host, self.port, db)


class CookieSettings(BaseModel):
    """Настройки файлов cookie (например, для JWT токенов)."""
    
    max_age: SecretStr = Field(..., description="Время жизни куки")
    httponly: SecretStr = Field(..., description="Флаг HttpOnly для защиты от XSS")
    path: SecretStr = Field(..., description="Путь, для которого валидна кука")
    domain: SecretStr = Field(default=None, description="Домен для куки")
    secure: SecretStr = Field(..., description="Флаг Secure (передача только по HTTPS)")
    name: str = Field(default="ghost-markt-cookie", description="Название куки по умолчанию")


class AccessTokenSettings(BaseModel):
    """Настройки короткоживущего токена доступа."""
    
    lifetime: int = Field(default=300, description="Время жизни Access токена в секундах")
    cookie_key: str = Field(default="access_token", description="Имя куки для хранения Access токена")
    secret: SecretStr = Field(..., description="Секретный ключ для подписи Access токена")


class RefreshTokenSettings(BaseModel):
    """Настройки долгоживущего токена обновления."""

    lifetime: int = Field(default=1296 * 1000, description="Время жизни Refresh токена в секундах")
    cookie_key: str = Field(default="refresh_token", description="Имя куки для хранения Refresh токена")
    secret: SecretStr = Field(..., description="Секретный ключ для подписи Refresh токена")


class AuthenticationSettings(BaseModel):
    """Общие настройки аутентификации JWT."""

    access_token: AccessTokenSettings = Field(default_factory=AccessTokenSettings, description="Настройки Access Token")
    refresh_token: RefreshTokenSettings = Field(default_factory=RefreshTokenSettings, description="Настройки Refresh Token")
    algorithm: str = Field(default="HS256", description="Алгоритм подписи JWT")


class OTPSettings(BaseModel):
    """Настройки системы одноразовых паролей (OTP)."""

    expiration_delta: int = Field(default=120, description="Время жизни OTP кода в секундах")


class MailingSettings(BaseModel):
    """Настройки SMTP клиента для отправки email сообщений."""

    hostname: SecretStr = Field(..., description="Хост SMTP сервера")
    port: SecretStr = Field(..., description="Порт SMTP сервера")
    ust_tls: SecretStr = Field(..., description="Использовать TLS (true/false)")
    username: SecretStr = Field(..., description="Имя пользователя SMTP")
    password: SecretStr = Field(..., description="Пароль SMTP")
    from_address: SecretStr = Field(..., description="Адрес отправителя")
    templates_folder: str = Field(default=str(BASE_DIR / "templates" / "mailings"), description="Путь к шаблонам писем")


class MediaSettings(BaseModel):
    """Настройки хранилища медиафайлов."""

    dir: str = Field(default="media", description="Имя папки с медиафайлами")
    path: str = Field(default=str(BASE_DIR / "media"), description="Полный путь к папке медиафайлов")
    max_file_size: int = Field(default=500 * 1024 * 1024, description="Максимальный размер файла в байтах")
    extensions: set[str] = Field(default={"image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime", "video/webm"}, description="Разрешенные MIME-типы")


class CDEKSettings(BaseModel):
    """Настройки интеграции со СДЭК."""

    client_id: SecretStr = Field(default=SecretStr(""), description="Client ID (Account) от CDEK")
    client_secret: SecretStr = Field(default=SecretStr(""), description="Client Secret (Secure) от CDEK")
    webhook_secret: SecretStr = Field(..., description="Секретный токен вебхуков CDEK")
    base_url: SecretStr = Field(..., description="Базовый URL API CDEK")
    shipment_point: str = Field(default="KSD271", description="Пункт отгрузки по умолчанию")


class AlltokensSettings(BaseModel):
    """Настройки сервиса AllTokens для генерации переводов с помощью ИИ."""
    model: str = "deepseek-v4-flash"
    api_key: SecretStr = Field(..., description="API-ключ AllTokens")


class OrderSettings(BaseModel):
    """Настройки заказов."""
    expiration_time: int = Field(default=15*60, description="Время экспирации заказа в секундах (по умолчанию 15 минут)")
    webhook_secret: SecretStr = Field(default=SecretStr("secret"), description="Секретный токен для вебхука создания заказов")


class FrontendSettings(BaseModel):
    """Настройки фронтенда."""
    base_url: str = Field(default="http://localhost:5173", description="Базовый URL фронтенда")


class Settings(BaseSettings):
    """
    Главные настройки приложения GhostServer.
    Читают значения из файла .env и переменных окружения.
    """

    DEBUG: bool = Field(default=True, description="Режим отладки")
    ON_WEBHOOKS: bool = Field(default=True, description="Использовать вебхуки вместо polling'а для Telegram бота")
    WEBHOOK_URL: str = Field(default="https://yourdomain.com/api/webhooks/telegram/", description="Внешний URL для вебхуков")

    bot: BotSettings = Field(default_factory=BotSettings)
    robokassa: RobokassaSettings = Field(default_factory=RobokassaSettings)
    legal: LegalSettings = Field(default_factory=LegalSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    cookie: CookieSettings = Field(default_factory=CookieSettings)
    authentication: AuthenticationSettings = Field(default_factory=AuthenticationSettings)
    mailings: MailingSettings = Field(default_factory=MailingSettings)
    otp: OTPSettings = Field(default_factory=OTPSettings)
    media: MediaSettings = Field(default_factory=MediaSettings)
    cdek: CDEKSettings = Field(default_factory=CDEKSettings)
    alltokens: AlltokensSettings = Field(default_factory=AlltokensSettings)
    order: OrderSettings = Field(default_factory=OrderSettings)
    frontend: FrontendSettings = Field(default_factory=FrontendSettings)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )






try:
    settings = Settings()
    db_settings = DatabaseSettings()
    import logging
    import logging.config
    from pathlib import Path

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    import os
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
            },
        },

        "handlers": {
            "users_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "users.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "orders_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "orders.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "products_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "products.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "cdek_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "cdek.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "bot_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "bot.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "payments_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "payments.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "notifications_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "notifications.log",
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
                "filename": log_dir / "app.log",
                "maxBytes": 15 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "standard",
            },
        },

        "loggers": {
            "src.auth": {
                "handlers": ["users_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "src.orders": {
                "handlers": ["orders_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "src.products": {
                "handlers": ["products_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "src.cdek": {
                "handlers": ["cdek_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "src.bot": {
                "handlers": ["bot_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "src.payments": {
                "handlers": ["payments_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
            "src.notifications": {
                "handlers": ["notifications_file", "console"],
                "level": LOG_LEVEL,
                "propagate": False,
            },
        },

        "root": {
            "handlers": ["app_file", "console"],
            "level": LOG_LEVEL,
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)
except Exception as e:
    logging.critical("Критическая ошибка при инициализации config.py: {}".format(e))
    raise e
