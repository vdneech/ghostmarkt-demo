import logging
from typing import Optional
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status, Query, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.shared.dependencies import get_db
from src.auth.dependencies import get_current_superuser, get_current_user_or_none
from src.auth.models import User
from src.products.models import PromoCode
from src.products.schemas import PromoCodeCreate, PromoCodeResponse, PromoCodeValidateResponse
from src.shared.dependencies import clear_browser_cache

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/promocodes",
    tags=["PromoCodes"],
)

@router.post(
    "/",
    response_model=PromoCodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать промокод",
    responses={
        status.HTTP_201_CREATED: {
            "description": "Промокод успешно создан",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Невалидные данные или промокод уже существует",
            "content": {"application/json": {"example": {"detail": "Промокод с таким кодом уже существует"}}}
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        }
    }
)
async def create_promocode(
    data: PromoCodeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache)
):
    """
    ### Создание нового промокода
    
    Создает промокод в каталоге с указанием размера скидки (фиксированной или в процентах), 
    срока годности и лимита использования.
    
    Доступно **только администраторам** (`is_superuser=True`).
    """
    existing = await db.execute(select(PromoCode).where(PromoCode.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Промокод с таким кодом уже существует"
        )
    
    new_promo = PromoCode(
        code=data.code,
        expires_at=data.expires_at,
        max_usages=data.max_usages,
        usages_count=0,
        discount=data.discount,
        discount_percent=data.discount_percent,
    )
    db.add(new_promo)
    await db.commit()
    await db.refresh(new_promo)
    return new_promo

@router.get(
    "/",
    summary="Получить или верифицировать промокоды",
    responses={
        status.HTTP_200_OK: {
            "description": "Успешная верификация промокода (если переданы query параметры `code` и `sum`) "
                           "или список промокодов (если вызвано администратором без параметров).",
            "content": {
                "application/json": {
                    "examples": {
                        "validate_response": {
                            "summary": "Пример ответа верификации промокода",
                            "value": {
                                "valid": True,
                                "discount_amount": 150.00,
                                "message": "Промокод успешно применен"
                            }
                        },
                        "list_response": {
                            "summary": "Пример списка всех промокодов (для админов)",
                            "value": [
                                {
                                    "id": 1,
                                    "code": "SUMMER2026",
                                    "discount": 500.00,
                                    "discount_percent": None,
                                    "max_usages": 100,
                                    "usages_count": 5,
                                    "expires_at": "2026-08-31T23:59:59Z"
                                }
                            ]
                        }
                    }
                }
            }
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав (при запросе списка промокодов без прав администратора)",
        }
    }
)
async def get_promocodes(
    code: Optional[str] = Query(None, description="Код промокода для верификации"),
    sum: Optional[Decimal] = Query(None, description="Сумма заказа для верификации"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_or_none),
):
    """
    ### Получение или верификация промокодов
    
    Поддерживает два режима работы:
    * **Верификация промокода (для всех):** передайте параметры `code` (код) и `sum` (сумма заказа) для проверки применимости скидки.
    * **Просмотр списка промокодов:** доступен **только администраторам** при вызове эндпоинта без параметров.
    """
    if code is not None and sum is not None:
        stmt = select(PromoCode).where(PromoCode.code == code)
        result = await db.execute(stmt)
        promo = result.scalar_one_or_none()
        
        if not promo:
            return PromoCodeValidateResponse(valid=False, discount_amount=Decimal("0.00"), message="Промокод не найден")
        
        if promo.expires_at is not None:
            now = datetime.now(promo.expires_at.tzinfo or timezone.utc)
            if now > promo.expires_at:
                return PromoCodeValidateResponse(valid=False, discount_amount=Decimal("0.00"), message="Срок действия промокода истек")
        
        if promo.max_usages is not None and promo.usages_count >= promo.max_usages:
            return PromoCodeValidateResponse(valid=False, discount_amount=Decimal("0.00"), message="Промокод полностью использован")
        
        if promo.discount is not None:
            if promo.discount > sum:
                return PromoCodeValidateResponse(
                    valid=False, 
                    discount_amount=Decimal("0.00"), 
                    message=f"Сумма заказа ({sum} ₽) меньше суммы скидки ({promo.discount} ₽)"
                )
            discount_amount = promo.discount
        else:
            discount_amount = (sum * Decimal(promo.discount_percent) / Decimal(100)).quantize(Decimal("1.00"))
            
        return PromoCodeValidateResponse(valid=True, discount_amount=discount_amount, message="Промокод успешно применен")

    if not user or not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав"
        )
        
    stmt = select(PromoCode).order_by(PromoCode.id.desc())
    result = await db.execute(stmt)
    promos = result.scalars().all()
    return [PromoCodeResponse.model_validate(p) for p in promos]

@router.delete(
    "/{promocode_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить промокод",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Промокод успешно удален",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Промокод не найден",
            "content": {"application/json": {"example": {"detail": "Промокод не найден"}}}
        }
    }
)
async def delete_promocode(
    promocode_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache)
):
    """
    ### Удаление промокода
    
    Полностью удаляет промокод из базы данных по его идентификатору.
    
    Доступно **только администраторам** (`is_superuser=True`).
    """
    stmt = select(PromoCode).where(PromoCode.id == promocode_id)
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Промокод не найден"
        )
        
    await db.execute(delete(PromoCode).where(PromoCode.id == promocode_id))
    await db.commit()
    return
