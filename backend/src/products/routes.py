import logging
from typing import TYPE_CHECKING, Optional
from fastapi import APIRouter, Depends, File, UploadFile, status, Request, Response, Form, Header
from src.shared.cache import clear_cache
from fastapi_cache.decorator import cache

from src.infrastructure.ai.dependencies import get_ai_service
from src.infrastructure.ai.services import AIService
from src.auth.dependencies import get_current_superuser, get_current_user_or_none
from src.products.dependencies import get_product_service
from src.shared.dependencies import clear_browser_cache
from src.products.services import ProductService
from src.products.schemas import (
    ProductResponse,
    ProductCreate,
    ProductListResponse,
    ProductUpdate,
    ProductPartiallyUpdate,
    ProductImageResponse,
    ProductVideoResponse,
    ProductVideoUpdate,
    ProductFilter,
)

if TYPE_CHECKING:
    from src.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Products"],
    prefix="/products",
)

def products_list_key_builder(
    func,
    namespace: str = "",
    request: Request = None,
    response: Response = None,
    *args,
    **kwargs,
):
    user = kwargs.get("user")
    is_admin = user.is_superuser if user else False
    query_str = str(request.query_params) if request else ""
    return f"{namespace}:list:admin={is_admin}:{query_str}"


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар",
    responses={
        status.HTTP_201_CREATED: {
            "description": "Товар успешно создан",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Невалидные входные данные",
            "content": {"application/json": {"example": {"detail": "Длина должна быть больше нуля"}}}
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
            "content": {"application/json": {"example": {"detail": "Сессия устарела или токен отсутствует"}}}
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
            "content": {"application/json": {"example": {"detail": "Недостаточно прав для выполнения этой операции."}}}
        },
        status.HTTP_409_CONFLICT: {
            "description": "Конфликт данных",
            "content": {"application/json": {"example": {"detail": "Товар с таким именем или слагом уже существует"}}}
        }
    }
)
async def create_product(
    product_data: ProductCreate,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
) -> ProductResponse:
    """
    Создает новый товар в каталоге.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут создания товара от пользователя {}".format(user.id if user else 'Unknown'))
    product = await service.create_product(product_data)
    await clear_cache("products")
    logger.info("Товар успешно создан в роуте: {}. Кэш сброшен.".format(product.id))
    return product


@router.get(
    "/{product_id}/",
    response_model=ProductResponse,
    summary="Получить товар по ID",
    responses={
        status.HTTP_200_OK: {
            "description": "Информация о товаре получена",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
@cache(expire=3600, namespace="products")
async def get_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_user_or_none),
) -> ProductResponse:
    """
    Возвращает детальную информацию о конкретном товаре по его идентификатору.
    Гости и обычные пользователи видят **только активные** товары (`is_active=True`).
    Администратор видит **все** товары, включая деактивированные.
    """
    is_admin = bool(user and user.is_superuser)
    logger.info("Вход в роут получения детальной информации о товаре ID: {} (is_admin={})".format(product_id, is_admin))
    product = await service.get_one(product_id, is_admin=is_admin)
    logger.info("Детальная информация о товаре ID {} успешно получена.".format(product_id))
    return product


@router.post(
    "/{product_id}/translate",
    response_model=ProductResponse,
    summary="Перевести товар (AI)",
    responses={
        status.HTTP_200_OK: {
            "description": "Перевод успешно выполнен и сохранен",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
            "content": {"application/json": {"example": {"detail": "Неавторизованный доступ"}}}
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
            "content": {"application/json": {"example": {"detail": "Недостаточно прав для выполнения этой операции"}}}
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
async def translate_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
    ai_service: AIService = Depends(get_ai_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
) -> ProductResponse:
    """
    Автоматически переводит название и описание товара на английский язык с использованием AI-сервиса.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут перевода товара ID: {} от пользователя {}".format(product_id, user.id if user else 'Unknown'))
    product = await service.translate_product(product_id, ai_service)
    await clear_cache("products")
    logger.info("Перевод товара ID {} выполнен успешно. Кэш сброшен.".format(product_id))
    return product


@router.get(
    "/",
    response_model=ProductListResponse,
    summary="Получить список товаров",
    responses={
        status.HTTP_200_OK: {
            "description": "Список товаров успешно получен",
        }
    }
)
@cache(expire=3600, namespace="products", key_builder=products_list_key_builder)
async def get_products(
    request: Request,
    filters: ProductFilter = Depends(),
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_user_or_none),
) -> ProductListResponse:
    """
    Возвращает список всех товаров с учетом переданных фильтров (поиск по имени, количеству).
    Для обычных пользователей и гостей автоматически скрываются неактивные товары (`is_active=True`).
    """
    logger.info("Вход в роут списка товаров. Пользователь: {}".format(user.id if user else 'Аноним'))
    is_admin = bool(user and user.is_superuser)
    response = await service.get_many(filters=filters, is_admin=is_admin)
    logger.info("Возвращено {} товаров в списке.".format(response.total))
    return response


@router.delete(
    "/{product_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить товар",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Товар успешно удален",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
async def delete_product(
    product_id: int,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
) -> None:
    """
    Удаляет товар по его уникальному ID.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут удаления товара ID: {} от пользователя {}".format(product_id, user.id if user else 'Unknown'))
    await service.delete(product_id=product_id)
    await clear_cache("products")
    logger.info("Товар ID {} успешно удален через роут. Кэш сброшен.".format(product_id))
    return


@router.patch(
    "/{product_id}/",
    response_model=ProductResponse,
    summary="Частично обновить товар",
    responses={
        status.HTTP_200_OK: {
            "description": "Товар успешно обновлен",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
async def partially_update_product(
    product_id: int,
    data: ProductPartiallyUpdate,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
) -> ProductResponse:
    """
    Обновляет только переданные поля товара.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут частичного обновления товара ID: {} от пользователя {}".format(product_id, user.id if user else 'Unknown'))
    product = await service.update(product_id, data, partial=True)
    await clear_cache("products")
    logger.info("Товар ID {} успешно обновлен частично. Кэш сброшен.".format(product_id))
    return product


@router.put(
    "/{product_id}/",
    response_model=ProductResponse,
    summary="Полностью обновить товар",
    responses={
        status.HTTP_200_OK: {
            "description": "Товар успешно обновлен полностью",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
) -> ProductResponse:
    """
    Полностью заменяет все поля товара (PUT).
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут полного обновления товара ID: {} от пользователя {}".format(product_id, user.id if user else 'Unknown'))
    product = await service.update(product_id, data, partial=False)
    await clear_cache("products")
    logger.info("Товар ID {} успешно обновлен полностью. Кэш сброшен.".format(product_id))
    return product


@router.post(
    "/{product_id}/images",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductImageResponse,
    summary="Загрузить изображение товара",
    responses={
        status.HTTP_201_CREATED: {
            "description": "Изображение успешно сохранено и привязано",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
async def upload_product_images(
    product_id: int,
    file: UploadFile = File(description="Выберите фотографии для отправки"),
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
):
    """
    Загружает изображение с диска и привязывает его к товару.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут загрузки изображения для товара ID: {} от пользователя {}".format(product_id, user.id if user else 'Unknown'))
    response = await service.save_image(
        product_id=product_id,
        file=file,
    )
    await clear_cache("products")
    logger.info("Изображение успешно привязано к товару {}. ID изображения: {}. Кэш сброшен.".format(product_id, response.id))
    return response


@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить изображение товара",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Изображение успешно удалено",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар или изображение не найдено",
            "content": {"application/json": {"example": {"detail": "Изображение товара не найдено"}}}
        }
    }
)
async def delete_product_image(
    product_id: int,
    image_id: int,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
):
    """
    Удаляет привязанное изображение товара.
    """
    logger.info("Вход в роут удаления изображения {} товара {} от пользователя {}".format(image_id, product_id, user.id if user else 'Unknown'))
    await service.delete_image(
        product_id=product_id,
        image_id=image_id,
    )
    await clear_cache("products")
    logger.info("Изображение {} товара {} успешно удалено. Кэш сброшен.".format(image_id, product_id))
    return


@router.post(
    "/{product_id}/videos",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductVideoResponse,
    summary="Загрузить видео товара",
    responses={
        status.HTTP_201_CREATED: {
            "description": "Видео успешно сохранено и привязано",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар не найден",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}}
        }
    }
)
async def upload_product_videos(
    product_id: int,
    file: UploadFile = File(description="Выберите видео для отправки"),
    description: Optional[str] = Form(None, description="Краткое описание видео"),
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
):
    """
    Загружает видео с диска и привязывает его к товару.
    Доступно **только администраторам** системы.
    """
    logger.info("Вход в роут загрузки видео для товара ID: {} от пользователя {}".format(product_id, user.id if user else 'Unknown'))
    response = await service.save_video(
        product_id=product_id,
        file=file,
        description=description,
    )
    await clear_cache("products")
    logger.info("Видео успешно привязано к товару {}. ID видео: {}. Кэш сброшен.".format(product_id, response.id))
    return response


@router.post(
    "/{product_id}/videos/chunk",
    status_code=status.HTTP_200_OK,
    summary="Загрузить чанк видео",
)
async def upload_video_chunk(
    product_id: int,
    request: Request,
    x_upload_id: str = Header(..., description="ID загрузки для сборки чанков"),
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
):
    content = await request.body()
    await service._media_service.append_chunk_bytes(x_upload_id, content)
    return {"status": "ok"}


@router.post(
    "/{product_id}/videos/finish",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductVideoResponse,
    summary="Завершить загрузку видео",
)
async def finish_video_upload(
    product_id: int,
    upload_id: str = Form(...),
    content_type: str = Form(...),
    description: Optional[str] = Form(None),
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache)
):
    file_path = await service._media_service.finalize_chunked_upload(upload_id, content_type)
    response = await service.save_video_from_path(product_id, file_path, description)
    await clear_cache("products")
    return response


@router.patch(
    "/{product_id}/videos/{video_id}",
    response_model=ProductVideoResponse,
    summary="Обновить описание видео",
)
async def update_video_description(
    product_id: int,
    video_id: int,
    data: ProductVideoUpdate,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
):
    response = await service.update_video_description(product_id, video_id, data.description)
    await clear_cache("products")
    return response


@router.delete(
    "/{product_id}/videos/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить видео товара",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Видео успешно удалено",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не авторизован",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Недостаточно прав",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Товар или видео не найдено",
            "content": {"application/json": {"example": {"detail": "Видео товара не найдено"}}}
        }
    }
)
async def delete_product_video(
    product_id: int,
    video_id: int,
    service: ProductService = Depends(get_product_service),
    user: "User" = Depends(get_current_superuser),
    _ = Depends(clear_browser_cache),
):
    """
    Удаляет привязанное видео товара.
    """
    logger.info("Вход в роут удаления видео {} товара {} от пользователя {}".format(video_id, product_id, user.id if user else 'Unknown'))
    await service.delete_video(
        product_id=product_id,
        video_id=video_id,
    )
    await clear_cache("products")
    logger.info("Видео {} товара {} успешно удалено. Кэш сброшен.".format(video_id, product_id))
    return

