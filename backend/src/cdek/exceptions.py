from typing import Any
from src.cdek import schemas


class CDEKError(Exception):
    """
    Базовое исключение для интеграции с сервисом CDEK.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class CDEKDataError(
    CDEKError,
):

    def __init__(
        self,
        message: str,
        errors: list[schemas.CDEKError] = None
    ):
        self.errors = errors
        super().__init__(message)


class CDEKAuthenticationError(CDEKError):
    """
    Вызывается при неудачной попытке авторизации в API CDEK (ошибка получения токена).
    """
    pass


class CDEKApiError(CDEKError):
    """
    Вызывается, когда CDEK API возвращает неуспешный ответ (код ошибки HTTP).
    """

    def __init__(self, status_code: int, detail: Any = None):
        self.status_code = status_code
        self.detail = detail
        message = f"CDEK API вернул ошибку с кодом {status_code}: {detail}"
        super().__init__(message)


class CDEKRequestError(CDEKError):
    """
    Вызывается при ошибках формирования проксируемых запросов в CDEK.
    """
    pass
