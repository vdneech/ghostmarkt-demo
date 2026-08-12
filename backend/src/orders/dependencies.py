from typing import TYPE_CHECKING
from fastapi import Depends

from src.orders.services import OrderService
from src.cdek.dependencies import get_cdek_service
from src.shared.dependencies import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

async def get_order_service(
    session: "AsyncSession" = Depends(get_db),
    cdek_service = Depends(get_cdek_service)
):

    service = OrderService(session=session, cdek_service=cdek_service)
    return service