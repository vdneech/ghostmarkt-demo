import enum

from pydantic import BaseModel, Field, PositiveInt
from typing import Optional

class Locale(enum.Enum):
    RU = "ru"
    EN = "en"

class Dimensions(BaseModel):
    length: PositiveInt = Field(
        ...,
        gt=0,
        description="Длина в сантиметрах."
    )
    width: PositiveInt = Field(
        ...,
        gt=0,
        description="Ширина в сантиметрах."
    )
    height: PositiveInt = Field(
        ...,
        gt=0,
        description="Высота в сантиметрах."
    )

class ErrorResponse(BaseModel):
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Detailed error reason or trace if applicable")