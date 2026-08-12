from decimal import Decimal
from typing import Annotated

from pydantic import Field

Money = Annotated[
    Decimal,
    Field(max_digits=10, decimal_places=2, ge=0, examples=[Decimal('251001.99')])
]

