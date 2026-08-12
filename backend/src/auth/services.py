from datetime import datetime, timezone, timedelta
from random import randint
from typing import TYPE_CHECKING, Any
import jwt
import phonenumbers
from email_validator import validate_email, EmailNotValidError, EmailUndeliverableError, EmailSyntaxError
from jwt import ExpiredSignatureError, PyJWTError
from phonenumbers import PhoneNumberFormat
from phonenumbers.phonenumberutil import NumberParseException

from src.auth.schemas import UserCreate
from src.auth.exceptions import UserNotFoundError, InvalidPhoneNumber, OTPCodeAlreadySent
from src.auth.schemas import UserUpdate, UserResponse, AdminUserUpdate, AdminUserReplace
from src.config import settings
from src.shared.services import SessionService
import logging

logger = logging.getLogger(__name__)
from src.auth.dao import UsersDAO
from src.auth.models import User
from src.auth.exceptions import FullnameValidationError
from pydantic import EmailStr
if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

class UserService(SessionService):
    """
    Сервис для работы с учетными записями пользователей (User).
    Отвечает за регистрацию, обновление данных профилей и валидацию данных.
    """
    def __init__(self, session: "AsyncSession"):
        """
        Инициализирует сервис пользователя с сессией базы данных и DAO пользователей.
        """
        self._session = session
        self.dao = UsersDAO(session)

    async def create(self, data: UserCreate, raw: bool = False) -> UserResponse | User:
        """
        Создает нового пользователя или возвращает существующего по email.
        Автоматически форматирует номер телефона в формат E.164.
        Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Запуск регистрации/получения пользователя с email: {}".format(data.email))
        data.phone = self.validate_and_format_phone(data.phone)
        user = await self.dao.get_or_create_by_email(
            email=data.email,
            data=data
        )
        await self._session.commit()
        logger.info("Регистрация пользователя завершена (commit). ID пользователя: {}".format(user.id))
        if raw:
            return user
        return UserResponse.model_validate(user)

    async def get_or_create_by_email(self, email: EmailStr, data: UserCreate):
        try:
            user = await self.dao.get_or_create_by_email(email, data)
            await self._session.commit()
            return user
        except Exception as e:
            raise


    async def get_by_id(
        self,
        user_id: int,
    ) -> UserResponse:
        """
        Получает профиль пользователя по его идентификатору ID.
        Возбуждает UserNotFoundError, если пользователь отсутствует.
        """
        logger.info("Запрос на получение данных пользователя по ID: {}".format(user_id))
        user = await self.dao.find_one_or_none_by_id(
            user_id,
        )
        if not user:
            logger.warning("Пользователь с ID {} не найден.".format(user_id))
            raise UserNotFoundError
        logger.info("Профиль пользователя ID {} успешно получен.".format(user_id))
        return UserResponse.model_validate(user)

    async def update(
        self,
        user_id: int,
        data: UserUpdate,
    ) -> UserResponse:
        """
        Обновляет данные профиля пользователя.
        Форматирует номер телефона перед сохранением, если он был передан.
        Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Запуск обновления профиля для пользователя ID: {}".format(user_id))
        if data.phone is not None:
            data.phone = self.validate_and_format_phone(data.phone)

        user = await self.dao.update_returning(
            filters={
                "id": user_id,
            },
            values=data.model_dump(exclude_unset=True)
        )
        if not user:
            logger.warning("Пользователь с ID {} не найден для обновления.".format(user_id))
            raise UserNotFoundError
        await self._session.commit()
        logger.info("Профиль пользователя ID {} успешно сохранен (commit).".format(user_id))
        return UserResponse.model_validate(user)

    async def get_all_users(self) -> list[UserResponse]:
        """
        Получает список всех зарегистрированных пользователей в системе.
        """
        logger.info("Запрос администратора на получение списка всех пользователей.")
        users = await self.dao.find_all()
        logger.info("Успешно извлечено {} пользователей.".format(len(users)))
        return [UserResponse.model_validate(user) for user in users]

    async def admin_update_user(
        self,
        user_id: int,
        data: AdminUserUpdate | AdminUserReplace,
    ) -> UserResponse:
        """
        Обновляет все или часть атрибутов пользователя администратором (кроме telegram_chat_id).
        Форматирует номер телефона, если он передан.
        Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Запуск административного обновления пользователя ID: {}".format(user_id))
        
        if isinstance(data, AdminUserReplace):
            update_values = data.model_dump()
        else:
            update_values = data.model_dump(exclude_unset=True)

        if "phone" in update_values and update_values["phone"] is not None:
            update_values["phone"] = self.validate_and_format_phone(update_values["phone"])

        user = await self.dao.update_returning(
            filters={
                "id": user_id,
            },
            values=update_values
        )
        if not user:
            logger.warning("Пользователь с ID {} не найден при административном обновлении.".format(user_id))
            raise UserNotFoundError
            
        await self._session.commit()
        logger.info("Данные пользователя ID {} успешно изменены администратором (commit).".format(user_id))
        return UserResponse.model_validate(user)

    async def upsert_user_by_identifiers(self, data: UserCreate) -> User:
        """
        Ищет пользователя по email или telegram_chat_id.
        Если пользователь найден по одному из идентификаторов, обновляет его данные.
        Если передан telegram_chat_id и найден пользователь с полученным email, 
        то telegram_chat_id привязывается к этому пользователю (с освобождением у других аккаунтов).
        Если не найден, создает нового пользователя.
        """
        logger.info("Запрос на поиск или обновление пользователя. Email: {}, Telegram Chat ID: {}".format(data.email, data.telegram_chat_id))
        user = None

        if data.email:
            user = await self.dao.find_one_or_none(email=data.email)
            if user:
                logger.info("Пользователь найден по email: {}".format(data.email))
                if data.telegram_chat_id and user.telegram_chat_id != data.telegram_chat_id:
                    existing_tg_user = await self.dao.find_one_or_none(telegram_chat_id=data.telegram_chat_id)
                    if existing_tg_user and existing_tg_user.id != user.id:
                        existing_tg_user.telegram_chat_id = None
                        self._session.add(existing_tg_user)
                        await self._session.flush()
                        logger.info("Освобожден telegram_chat_id {} у пользователя ID {}".format(data.telegram_chat_id, existing_tg_user.id))
                    user.telegram_chat_id = data.telegram_chat_id

        if not user and data.telegram_chat_id:
            user = await self.dao.find_one_or_none(telegram_chat_id=data.telegram_chat_id)
            if user:
                logger.info("Пользователь найден по telegram_chat_id: {}".format(data.telegram_chat_id))

        update_values = data.model_dump(exclude_unset=True)
        if "phone" in update_values and update_values["phone"] is not None:
            update_values["phone"] = self.validate_and_format_phone(update_values["phone"])

        if user:
            for key, val in update_values.items():
                if val is not None:
                    setattr(user, key, val)
            self._session.add(user)
            await self._session.flush()
            await self._session.commit()
            logger.info("Пользователь ID {} успешно обновлен при заказе.".format(user.id))
        else:
            user = await self.dao.add(**update_values)
            await self._session.commit()
            logger.info("Создан новый пользователь с ID: {} при заказе.".format(user.id))

        return user

    @staticmethod
    def validate_and_split_fullname(fullname_str: str) -> tuple[str, str, str | None]:
        """
        Разделяет полное имя (ФИО) на Фамилию, Имя и Отчество.
        Возбуждает FullnameValidationError при неверном формате ввода.
        """
        words = [w.strip() for w in fullname_str.split() if w.strip()]

        if len(words) < 2:
            raise FullnameValidationError("Пожалуйста, введите как минимум Имя и Фамилию через пробел")

        last_name = words[0]
        first_name = words[1]
        middle_name = words[2] if len(words) > 2 else None
        return last_name, first_name, middle_name

    async def finalize_user_profile(
        self,
        chat_id: int,
        data: dict[str, str],
    ) -> User:
        """
        Заполняет анкетные данные профиля пользователя (для Telegram-бота)
        на основе переданного словаря. Неявно фиксирует изменения в БД (commit).
        """
        logger.info("Запуск финального заполнения профиля пользователя по чату: {}".format(chat_id))
        try:
            last_name, first_name, middle_name = self.validate_and_split_fullname(data.get("fullname", ""))

            user = await self.dao.update_returning(
                filters={"telegram_chat_id": chat_id},
                values={
                    "first_name": first_name,
                    "middle_name": middle_name,
                    "last_name": last_name,
                    "source": data.get("source"),
                    "specialty": data.get("specialty"),
                    "phone": data.get("phone"),
                    "email": data.get("email"),
                }
            )
            if not user:
                logger.warning("Пользователь с telegram_chat_id {} не найден для обновления анкеты.".format(chat_id))
                raise UserNotFoundError

            await self._session.commit()
            logger.info("Анкета пользователя {} успешно сохранена (commit).".format(chat_id))
            return user
        except Exception as e:
            logger.error("Не удалось добавить профиль пользователя {} в базу: {}".format(chat_id, e))
            await self._session.rollback()
            raise


    @staticmethod
    def validate_and_format_phone(phone_str: str) -> str:
        """
        Проверяет номер телефона на валидность (для РФ и международных номеров).
        Поддерживает любые форматы: +7 (312) 898-32-13, 8(312)8983213 и международные.
        Возвращает номер в международном формате E.164.
        """
        try:
            cleaned_phone = phone_str.strip()

            default_region = None if cleaned_phone.startswith('+') else "RU"

            parsed_number = phonenumbers.parse(cleaned_phone, default_region)

            if not phonenumbers.is_valid_number(parsed_number):
                raise InvalidPhoneNumber

            return phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164)

        except NumberParseException:
            raise InvalidPhoneNumber

    @staticmethod
    def check_email(email: str) -> bool:
        """
        Выполняет валидацию синтаксиса и доступности email.
        """
        try:
            validate_email(email, check_deliverability=True)
            return True
        except (EmailNotValidError, EmailUndeliverableError, EmailSyntaxError):
            return False


class OTPService(SessionService):
    """
    Сервис генерации и валидации одноразовых паролей (OTP) для авторизации.
    Пароли сохраняются во временном хранилище Redis.
    """
    def __init__(self, redis: "Redis"):
        """
        Инициализирует OTP-сервис с Redis клиентом.
        """
        self._redis = redis
        self._key = "otp:{}"

    async def generate_and_save(self, email: str) -> str:
        """
        Генерирует новый 6-значный OTP код и сохраняет его в Redis.
        Если предыдущий код еще активен, возбуждает OTPCodeAlreadySent.
        """
        logger.info("Запрос генерации OTP кода для email: {}".format(email))
        ttl = await self._redis.ttl(name=self._key.format(email))

        if ttl > 0:
            logger.warning("Повторный запрос OTP кода для {} отклонен. TTL: {} сек.".format(email, ttl))
            raise OTPCodeAlreadySent(ttl)

        code = str(randint(100000, 999999))
        key = self._key.format(email)
        await self._redis.set(
            name=key,
            value=code,
            ex=settings.otp.expiration_delta,
        )
        logger.info("Новый OTP код для {} сохранен в Redis.".format(email))
        return code

    async def verify(self, email: str, code: str) -> bool:
        """
        Сверяет присланный пользователем код с сохраненным в Redis.
        При успешном совпадении удаляет код из Redis.
        Ограничивает количество попыток проверки до 5.
        """
        logger.info("Верификация OTP кода для email: {}".format(email))
        key = self._key.format(email)
        attempts_key = "otp_attempts:{}".format(email)

        attempts_raw = await self._redis.get(attempts_key)
        attempts = int(attempts_raw) if attempts_raw else 0

        if attempts >= 5:
            await self._redis.delete(key)
            await self._redis.delete(attempts_key)
            logger.warning("OTP код для {} заблокирован: превышено число попыток верификации.".format(email))
            return False

        true_code = await self._redis.get(key)
        if not true_code:
            logger.warning("OTP код для {} не найден или устарел.".format(email))
            return False

        if true_code == code:
            await self._redis.delete(key)
            await self._redis.delete(attempts_key)
            logger.info("OTP код для {} успешно подтвержден.".format(email))
            return True

        await self._redis.set(
            name=attempts_key,
            value=attempts + 1,
            ex=settings.otp.expiration_delta,
        )
        logger.warning("Неверный OTP код для email: {}. Попытка {} из 5".format(email, attempts + 1))
        return False


class AuthService(SessionService):
    """
    Сервис авторизации пользователей, управления сессиями и выдачи JWT-токенов.
    """
    def __init__(self, session: "AsyncSession", redis: "Redis"):
        """
        Инициализирует сервис авторизации.
        """
        self._user_dao = UsersDAO(session)
        self.redis = redis
        self._otp_key = "otp:{}"

    async def request_otp(self, email: str) -> str:
        """
        Запрашивает OTP код для входа по email. Создает учетную запись пользователя при ее отсутствии.
        """
        logger.info("Запрос OTP через AuthService для email: {}".format(email))
        await self._user_dao.get_or_create_by_email(email, UserCreate(email=email))
        try:
            code = str(randint(100000, 999999))
            await self.redis.set(
                name=self._otp_key.format(email),
                value=code,
                ex=settings.otp.expiration_delta
            )
            logger.info("Код авторизации для {} записан.".format(email))
            return code
        except Exception as e:
            logger.error("Не удалось сохранить OTP код для email {} в Redis: {}".format(email, e))
            raise

    @staticmethod
    def create_token(email: str, expires: int, refresh: bool = False) -> str:
        """
        Генерирует JWT токен доступа (access) или обновления (refresh) для указанного email.
        """
        logger.info("Генерация JWT токена для email: {}. Режим refresh: {}".format(email, refresh))
        if refresh:
            secret = settings.authentication.refresh_token.secret.get_secret_value()
        else:
            secret = settings.authentication.access_token.secret.get_secret_value()
        payload = {
            "sub": email,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expires)
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    @staticmethod
    def decode_and_verify(token: str, refresh: bool = False) -> str:
        """
        Декодирует JWT токен и верифицирует его подпись и срок действия.
        Возвращает email (subject) при успехе.
        """
        logger.info("Декодирование и проверка JWT токена. Режим refresh: {}".format(refresh))
        if refresh:
            secret = settings.authentication.refresh_token.secret.get_secret_value()
        else:
            secret = settings.authentication.access_token.secret.get_secret_value()

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[settings.authentication.algorithm]
            )
            email = payload.get("sub")
            if not email:
                raise ValueError("В токене отсутствует поле sub (email)")
            return email
        except ExpiredSignatureError:
            logger.warning("Срок действия токена истек.")
            raise Exception("Token expired")
        except PyJWTError as e:
            logger.info("Ошибка проверки подписи токена: {}".format(e))
            raise Exception("Invalid token")