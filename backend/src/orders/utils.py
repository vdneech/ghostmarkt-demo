import math
from typing import TYPE_CHECKING

from src.shared.schemas import Dimensions

if TYPE_CHECKING:
    from src.orders.models import OrderItem

def calculate_dimensions(items: list["OrderItem"]) -> Dimensions:
    total_volume = 0
    max_length = 0
    max_width = 0
    max_height = 0

    for item in items:
        product = item.product
        total_volume += product.volume * item.quantity
        max_length = max(max_length, product.length)
        max_width = max(max_width, product.width)
        max_height = max(max_height, product.height)

    BOX_M_LENGTH = 33
    BOX_M_WIDTH = 25
    BOX_M_HEIGHT = 15

    base_length = max(BOX_M_LENGTH, max_length)
    base_width = max(BOX_M_WIDTH, max_width)
    base_height = max(BOX_M_HEIGHT, max_height)

    base_volume = base_length * base_width * base_height
    estimated_volume = total_volume * 1.25

    if estimated_volume > base_volume:
        cube_side = math.ceil(estimated_volume ** (1 / 3))
        return Dimensions(
            length=max(cube_side, base_length),
            width=max(cube_side, base_width),
            height=max(cube_side, base_height)
        )

    return Dimensions(
        length=base_length,
        width=base_width,
        height=base_height
    )
