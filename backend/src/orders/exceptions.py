class OrderDomainError(Exception):
    """Базовое исключение для бизнес-логики заказов."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class OrderNotFoundError(OrderDomainError):
    """Заказ не найден в системе."""
    pass


class ProductNotFoundError(OrderDomainError):
    """Один или несколько товаров из позиций заказа не существуют."""
    def __init__(self, product_id: int):
        self.product_id = product_id
        super().__init__(f"Товар с ID {product_id} не найден.")


class OutOfStockError(OrderDomainError):
    """Недостаточно товара на складе."""
    def __init__(self, product_id: int, requested: int, available: int):
        self.product_id = product_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Товар на складе закончился. Вы можете сделать заказ позже, когда товар появится!"
        )


class MetadataValidationError(OrderDomainError):
    """Ошибка валидации кастомных характеристик товара (item_meta)."""
    def __init__(self, message: str, missing_fields: set[str]):
        self.missing_fields = missing_fields
        super().__init__(message)

class MissingDeliveryInfo(OrderDomainError):
    """Ошибка при отсутствии необходимой информации для доставки."""
    def __init__(self, message: str, missing_fields: set[str] = None):
        self.missing_fields = missing_fields
        super().__init__(message)