class ProductDomainError(Exception):
    """Базовое доменное исключение для продуктов."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class ProductNotFoundError(ProductDomainError):
    """Исключение, вызываемое когда товар не найден."""
    def __init__(self, message: str = 'Товар не найден'):
        super().__init__(message)

class ProductAlreadyExistsError(ProductDomainError):
    """Исключение, вызываемое когда товар с таким именем или слагом уже существует."""
    def __init__(self, message: str = 'Товар уже существует'):
        super().__init__(message)

class ProductImageError(ProductDomainError):
    """Исключение для ошибок, связанных с изображениями товара."""
    def __init__(self, message: str):
        super().__init__(message)

class ProductTranslationError(ProductDomainError):
    """Исключение для ошибок перевода товара с помощью AI."""
    def __init__(self, message: str):
        super().__init__(message)

class ProductVideoError(ProductDomainError):
    """Исключение для ошибок, связанных с видео товара."""
    def __init__(self, message: str):
        super().__init__(message)
