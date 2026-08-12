from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.dependencies import get_db
from src.products.services import ProductService
from src.infrastructure.ai.dependencies import get_ai_service
from src.infrastructure.ai.services import AIService

def get_product_service(
    session: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service),
) -> ProductService:
    """
    Зависимость для получения экземпляра ProductService.
    """
    return ProductService(session=session, ai_service=ai_service)
