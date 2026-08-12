from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.shared.schemas import ErrorResponse
from src.auth.exceptions import InvalidPhoneNumber, OTPCodeAlreadySent, UserNotFoundError, FullnameValidationError
from src.orders.exceptions import OrderNotFoundError, OrderDomainError, OutOfStockError, MetadataValidationError, ProductNotFoundError as OrderProductNotFoundError
from src.products.exceptions import (
    ProductNotFoundError,
    ProductAlreadyExistsError,
    ProductImageError,
    ProductTranslationError,
    ProductDomainError,
)
from src.cdek.exceptions import (
    CDEKError,
    CDEKDataError,
    CDEKAuthenticationError,
    CDEKApiError,
    CDEKRequestError,
)
from src.infrastructure.exceptions import (
    InvalidFileExtensionError,
    FileTooLargeError,
    MediaSaveError,
)

class DAONotFoundError(Exception):
    """Исключение для ошибок нахождения DAO в наследниках BaseDAO."""
    def __init__(self, message: str = "DAO not found"):
        self.message = message
        super().__init__(self.message)

def create_error_response(status_code: int, message: str, detail: str = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(message=message, detail=detail).model_dump(exclude_none=True)
    )

async def order_not_found_handler(_request: Request, exc: OrderNotFoundError) -> JSONResponse:
    return create_error_response(status.HTTP_404_NOT_FOUND, "Order not found", str(exc))

async def out_of_stock_handler(_request: Request, exc: OutOfStockError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Product out of stock", str(exc))

async def order_domain_error_handler(_request: Request, exc: OrderDomainError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Order processing error", str(exc))

async def invalid_phone_error_handler(_request: Request, exc: InvalidPhoneNumber) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Invalid phone number format", str(exc))

async def file_not_found_error_handler(_request: Request, exc: FileNotFoundError) -> JSONResponse:
    return create_error_response(status.HTTP_404_NOT_FOUND, "File not found", str(exc))

async def code_already_sent_handler(_request: Request, exc: OTPCodeAlreadySent) -> JSONResponse:
    return create_error_response(status.HTTP_429_TOO_MANY_REQUESTS, "OTP code already sent recently", str(exc))

async def invalid_file_extension_handler(_request: Request, exc: InvalidFileExtensionError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Invalid file extension", str(exc))

async def file_too_large_handler(_request: Request, exc: FileTooLargeError) -> JSONResponse:
    return create_error_response(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large", str(exc))

async def media_save_error_handler(_request: Request, exc: MediaSaveError) -> JSONResponse:
    return create_error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to save media", str(exc))

async def product_not_found_handler(_request: Request, exc: ProductNotFoundError) -> JSONResponse:
    return create_error_response(status.HTTP_404_NOT_FOUND, "Product not found", str(exc))

async def product_already_exists_handler(_request: Request, exc: ProductAlreadyExistsError) -> JSONResponse:
    return create_error_response(status.HTTP_409_CONFLICT, "Product already exists", str(exc))

async def product_domain_error_handler(_request: Request, exc: ProductDomainError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Product domain error", str(exc))

async def cdek_error_handler(_request: Request, exc: CDEKError) -> JSONResponse:
    return create_error_response(status.HTTP_502_BAD_GATEWAY, "Delivery service error", str(exc))

async def cdek_data_error_handler(_request: Request, exc: CDEKDataError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Invalid delivery data", str(exc))

async def cdek_api_error_handler(_request: Request, exc: CDEKApiError) -> JSONResponse:
    status_code = exc.status_code if exc.status_code in [400, 401, 403, 404, 500, 502, 503] else 502
    return create_error_response(status_code, "Delivery API returned an error", str(exc.detail))

async def metadata_validation_error_handler(_request: Request, exc: MetadataValidationError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Metadata validation failed", str(exc))

async def fullname_validation_error_handler(_request: Request, exc: FullnameValidationError) -> JSONResponse:
    return create_error_response(status.HTTP_400_BAD_REQUEST, "Fullname validation failed", str(exc))

async def dao_not_found_error_handler(_request: Request, exc: DAONotFoundError) -> JSONResponse:
    return create_error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database DAO not found", str(exc))

async def user_not_found_handler(_request: Request, exc: UserNotFoundError) -> JSONResponse:
    return create_error_response(status.HTTP_404_NOT_FOUND, "User not found", str(exc))


def register_exception_handlers(app: FastAPI) -> None:
    """
    Регистрирует обработчики кастомных и системных исключений в приложении FastAPI.
    """
    app.add_exception_handler(OrderNotFoundError, order_not_found_handler)
    app.add_exception_handler(OutOfStockError, out_of_stock_handler)
    app.add_exception_handler(OrderDomainError, order_domain_error_handler)
    app.add_exception_handler(InvalidPhoneNumber, invalid_phone_error_handler)
    app.add_exception_handler(FileNotFoundError, file_not_found_error_handler)
    app.add_exception_handler(OTPCodeAlreadySent, code_already_sent_handler)
    app.add_exception_handler(InvalidFileExtensionError, invalid_file_extension_handler)
    app.add_exception_handler(FileTooLargeError, file_too_large_handler)
    app.add_exception_handler(MediaSaveError, media_save_error_handler)
    app.add_exception_handler(ProductNotFoundError, product_not_found_handler)
    app.add_exception_handler(ProductAlreadyExistsError, product_already_exists_handler)
    app.add_exception_handler(ProductDomainError, product_domain_error_handler)
    app.add_exception_handler(CDEKApiError, cdek_api_error_handler)
    app.add_exception_handler(CDEKDataError, cdek_data_error_handler)
    app.add_exception_handler(CDEKError, cdek_error_handler)
    app.add_exception_handler(MetadataValidationError, metadata_validation_error_handler)
    app.add_exception_handler(FullnameValidationError, fullname_validation_error_handler)
    app.add_exception_handler(DAONotFoundError, dao_not_found_error_handler)
    app.add_exception_handler(UserNotFoundError, user_not_found_handler)