import json
from typing import TYPE_CHECKING, Optional
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.exc import IntegrityError

from src.auth.models import Locale
from src.products.dao import ProductsDAO
from src.orders.schemas import ProductTranslation
from src.infrastructure.ai.services import AIService
from src.products.schemas import (
    ProductListResponse,
    ProductImageResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    ProductPartiallyUpdate,
    ProductFilter, ProductMeta, ProductMetaList,
)
from src.products.models import ProductImage, ProductVideo
from src.shared.services import MediaService, SessionService
import logging

logger = logging.getLogger(__name__)
from src.products.exceptions import (
    ProductNotFoundError,
    ProductAlreadyExistsError,
    ProductImageError,
    ProductTranslationError,
)
from slugify import slugify

if TYPE_CHECKING:
    from fastapi import File

class ProductService(SessionService):
    """
    Сервис для работы с товарами (Product).
    Реализует бизнес-логику управления каталогом товаров.
    """
    def __init__(self, session: AsyncSession, ai_service: Optional[AIService] = None):
        """
        Инициализирует сервис с сессией базы данных, DAO товаров, медиа-сервисом и AI-сервисом.
        """
        self._session = session
        self.dao = ProductsDAO(session)
        self._media_service = MediaService()
        self._image_model = ProductImage
        self._video_model = ProductVideo
        self._ai_service = ai_service or AIService()

    async def create_product(self, values: ProductCreate) -> ProductResponse:
        """
        Создает новый товар в каталоге с расчетом габаритов.
        Неявно фиксирует изменения в базе данных при успешном завершении.
        """
        logger.info("Запуск создания товара с названием: {}".format(values.name))
        try:
            dimensions = values.dimensions
            db_compatible_meta = await self._process_product_meta(values.meta)

            product = await self.dao.add(
                length=dimensions.length,
                width=dimensions.width,
                height=dimensions.height,
                meta=db_compatible_meta,
                **values.model_dump(exclude={"dimensions", "meta"})
            )
            set_committed_value(product, 'images', [])
            set_committed_value(product, 'videos', [])
            await self._session.commit()
            logger.info("Товар '{}' успешно создан с ID {} (commit).".format(values.name, product.id))
            return ProductResponse.model_validate(product)
        except IntegrityError as e:
            await self._session.rollback()
            logger.warning("Ошибка целостности при создании товара '{}': {}".format(values.name, e))
            raise ProductAlreadyExistsError(
                "Товар с таким именем или слагом уже существует (параллельный запрос)."
            )

    async def get_one(self, product_id: int, is_admin: bool = False) -> ProductResponse:
        """
        Возвращает детальную информацию о товаре по его идентификатору.
        Для обычных пользователей и гостей скрывает неактивные товары (is_active=False).
        Возбуждает ProductNotFoundError, если товар отсутствует или недоступен.
        """
        logger.info("Запрос на получение товара по ID: {} (is_admin={})".format(product_id, is_admin))
        product = await self.dao.find_one_or_none_by_id(
            product_id,
            selectinload(self.dao.model.images),
            selectinload(self.dao.model.videos),
        )
        if not product:
            logger.warning("Товар с ID {} не найден.".format(product_id))
            raise ProductNotFoundError("Товар не найден")

        if not is_admin and not product.is_active:
            logger.warning(
                "Товар с ID {} недоступен (is_active=False) для неавторизованного или обычного пользователя.".format(product_id)
            )
            raise ProductNotFoundError("Товар не найден")

        logger.info("Товар с ID {} успешно получен.".format(product_id))
        return ProductResponse.model_validate(product)

    async def get_many(
        self,
        filters: Optional[ProductFilter] = None,
        is_admin: bool = False,
    ) -> ProductListResponse:
        """
        Возвращает список товаров, соответствующих переданным фильтрам, и их общее количество.
        Для не-администраторов принудительно возвращаются только активные товары.
        """
        logger.info("Запрос на получение списка товаров по фильтрам: {} (is_admin={})".format(filters, is_admin))
        if not is_admin:
            if filters is None:
                filters = ProductFilter()
            filters.is_active = True

        products = await self.dao.find_all(
            selectinload(self.dao.model.images),
            selectinload(self.dao.model.videos),
            filters=filters,
        )
        total = await self.dao.count(filters=filters)
        logger.info("Получено {} товаров из общего числа {}.".format(len(products), total))
        result = {
            "products": [ProductResponse.model_validate(product) for product in products],
            "total": total,
        }
        return ProductListResponse.model_validate(result)

    async def update(
        self,
        product_id: int,
        data: ProductUpdate | ProductPartiallyUpdate,
        partial: bool = False,
    ) -> ProductResponse:
        """
        Обновляет данные существующего товара (полностью или частично).
        Возбуждает ProductNotFoundError, если товар не найден.
        """
        existing_product = await self.dao.find_one_or_none_by_id(product_id)
        if not existing_product:
            logger.warning("Товар с ID {} для обновления не найден.".format(product_id))
            raise ProductNotFoundError("Товар не найден")

        dump_args = {"exclude_unset": True} if partial else {}

        values = data.model_dump(**dump_args, exclude={"dimensions", "meta"})
        if data.dimensions:
            values.update(data.dimensions.model_dump(**dump_args))

        if "meta" in data.model_fields_set or (not partial and data.meta is not None):
            existing_meta = existing_product.meta
            db_compatible_meta = await self._process_product_meta(data.meta, existing_metas=existing_meta)
            values["meta"] = db_compatible_meta

        updated = await self.dao.update_returning(
            selectinload(self.dao.model.images),
            selectinload(self.dao.model.videos),
            filters={"id": product_id},
            values=values,
        )
        if not updated:
            raise ProductNotFoundError("Товар не найден")

        await self._session.commit()
        logger.info("Товар с ID {} успешно обновлен (commit).".format(product_id))
        return ProductResponse.model_validate(updated)

    async def delete(self, product_id: int) -> None:
        """
        Мягкое удаление товара: переводит его в статус неактивного (is_active = False),
        чтобы сохранить исторические связи в заказах (ForeignKey).
        """
        logger.info("Запрос на мягкое удаление товара с ID {}".format(product_id))
        product = await self.dao.find_one_or_none_by_id(product_id)
        if not product:
            logger.warning("Товар с ID {} для удаления не найден.".format(product_id))
            raise ProductNotFoundError("Товар не найден")
            
        await self.dao.update(
            filters={"id": product_id},
            values={"is_active": False}
        )
        await self._session.commit()
        logger.info("Товар с ID {} успешно деактивирован (commit).".format(product_id))

    async def save_image(self, product_id: int, file: "File") -> ProductImageResponse:
        """
        Сохраняет новое изображение товара на диск и связывает его с товаром в БД.
        В случае ошибки БД загруженный файл удаляется с диска.
        """
        logger.info("Запрос на добавление изображения к товару с ID {}".format(product_id))
        file_path = await self._media_service.save(file)

        photo = ProductImage(path=file_path, product_id=product_id)
        self._session.add(photo)
        try:
            await self._session.commit()
            logger.info("Изображение для товара {} сохранено с ID {} (commit).".format(product_id, photo.id))
            return ProductImageResponse.model_validate(photo)
        except Exception as e:
            await self._session.rollback()
            await self._media_service.delete(photo.path)
            logger.error("Ошибка при сохранении связей изображения в БД для товара {}: {}".format(product_id, e))
            raise ProductImageError("Ошибка сохранения связей в БД")

    async def delete_image(self, product_id: int, image_id: int) -> None:
        """
        Удаляет связь изображения с товаром в БД и удаляет сам файл с диска.
        Возбуждает ProductNotFoundError, если связь не найдена.
        """
        logger.info("Запрос на удаление изображения {} у товара {}".format(image_id, product_id))
        query = delete(self._image_model).where(
            self._image_model.id == image_id,
            self._image_model.product_id == product_id
        ).returning(self._image_model)
        result = await self._session.execute(query)
        deleted = result.scalar_one_or_none()

        if not deleted:
            logger.warning("Изображение {} у товара {} не найдено для удаления.".format(image_id, product_id))
            raise ProductNotFoundError("Изображение товара не найдено")

        await self._media_service.delete(deleted.path)
        await self._session.commit()
        logger.info("Изображение {} товара {} успешно удалено (commit).".format(image_id, product_id))

    async def save_video(self, product_id: int, file: "File", description: Optional[str] = None) -> "ProductVideoResponse":
        """
        Сохраняет новое видео товара на диск и связывает его с товаром в БД.
        В случае ошибки БД загруженный файл удаляется с диска.
        """
        logger.info("Запрос на добавление видео к товару с ID {}".format(product_id))
        file_path = await self._media_service.save(file)
        return await self.save_video_from_path(product_id, file_path, description)

    async def save_video_from_path(self, product_id: int, file_path: str, description: Optional[str] = None) -> "ProductVideoResponse":
        """
        Привязывает уже загруженный файл видео к товару в БД.
        В случае ошибки БД файл удаляется с диска.
        """
        video = self._video_model(path=file_path, product_id=product_id, description=description)
        self._session.add(video)
        try:
            await self._session.commit()
            logger.info("Видео для товара {} сохранено с ID {} (commit).".format(product_id, video.id))
            from src.products.schemas import ProductVideoResponse
            return ProductVideoResponse.model_validate(video)
        except Exception as e:
            await self._session.rollback()
            await self._media_service.delete(video.path)
            logger.error("Ошибка при сохранении связей видео в БД для товара {}: {}".format(product_id, e))
            from src.products.exceptions import ProductVideoError
            raise ProductVideoError("Ошибка сохранения связей видео в БД")

    async def update_video_description(self, product_id: int, video_id: int, description: Optional[str]) -> "ProductVideoResponse":
        """
        Обновляет описание видео.
        """
        video = await self._session.get(self._video_model, video_id)
        if not video or video.product_id != product_id:
            raise ProductNotFoundError("Видео товара не найдено")
        
        video.description = description
        try:
            await self._session.commit()
            from src.products.schemas import ProductVideoResponse
            return ProductVideoResponse.model_validate(video)
        except Exception as e:
            await self._session.rollback()
            raise ProductVideoError("Ошибка при обновлении видео в БД")

    async def delete_video(self, product_id: int, video_id: int) -> None:
        """
        Удаляет связь видео с товаром в БД и удаляет сам файл с диска.
        Возбуждает ProductNotFoundError, если связь не найдена.
        """
        logger.info("Запрос на удаление видео {} у товара {}".format(video_id, product_id))
        query = delete(self._video_model).where(
            self._video_model.id == video_id,
            self._video_model.product_id == product_id
        ).returning(self._video_model)
        result = await self._session.execute(query)
        deleted = result.scalar_one_or_none()

        if not deleted:
            logger.warning("Видео {} у товара {} не найдено для удаления.".format(video_id, product_id))
            raise ProductNotFoundError("Видео товара не найдено")

        await self._media_service.delete(deleted.path)
        await self._session.commit()
        logger.info("Видео {} товара {} успешно удалено (commit).".format(video_id, product_id))

    async def translate_product(
        self,
        product_id: int,
        ai_service: AIService,
    ) -> ProductResponse:
        """
        Переводит название и описание товара на английский язык с помощью AI-сервиса.
        """
        logger.info("Запуск перевода товара с ID {} на английский язык.".format(product_id))
        try:
            product = await self.get_one(product_id)

            system_prompt = (
                "Ты – профессиональный локализатор маркетплейсов. "
                "Переведи название и описание товара с русского языка на английский. "
                "Верни ответ СТРОГО в формате json с ключами 'name' и 'description'."
            )
            user_prompt = f"Название: {product.name}\nОписание: {product.description}"

            raw_json = await ai_service.text_to_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
            )

            translation = ProductTranslation.model_validate_json(raw_json)

            updated = await self.dao.update_returning(
                selectinload(self.dao.model.images),
                selectinload(self.dao.model.videos),
                filters={"id": product.id},
                values={
                    "name_en": translation.name,
                    "description_en": translation.description,
                },
            )

            if not updated:
                logger.warning("Товар с ID {} не найден при попытке сохранения перевода.".format(product_id))
                raise ProductNotFoundError("Товар не найден в базе данных при обновлении")

            await self._session.commit()
            logger.info("Перевод товара {} успешно завершен и сохранен (commit).".format(product_id))
            return ProductResponse.model_validate(updated)

        except ProductNotFoundError:
            raise
        except Exception as e:
            logger.exception("Ошибка в процессе перевода товара {}: {}".format(product_id, e))
            raise ProductTranslationError(
                f"Ошибка перевода: {type(e).__name__} - {e}"
            )

    @staticmethod
    async def _create_product_meta(
        ru_metas: list[str] | None,
        ai_service: AIService,
    ) -> list[ProductMeta] | None:
        logger.info("Запуск генерации метаданных товара с локализацией")

        if ru_metas is None:
            return None

        system_prompt = (
            "Ты – профессиональный локализатор маркетплейсов и системный архитектор. "
            "Тебе дан список сырых характеристик товара на русском языке. "
            "Для каждой характеристики тебе нужно:\n"
            "1. Сгенерировать уникальный системный 'key' в формате snake_case на английском языке (например: 'water_resistance').\n"
            "2. Заполнить объект `values`: сохранить оригинальное русское значение под ключом 'ru' "
            "и сделать качественный перевод на английский язык под ключом 'en'.\n"
            "Верни JSON-объект, содержащий поле 'metas', в котором будет лежать массив объектов"
        )

        user_prompt = f"Исходные характеристики для обработки:\n{json.dumps(ru_metas, ensure_ascii=False)}"

        try:
            en_meta_json = await ai_service.text_to_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
            )


            meta_collection = ProductMetaList.model_validate_json(en_meta_json)
            return meta_collection.metas

        except Exception as e:
            logger.error(f"Ошибка при парсинге или генерации метаданных: {e}")

            metas = [
                ProductMeta(
                    key=slugify(ru_meta),
                    values={
                        Locale.RU: ru_meta
                    }
                ) for ru_meta in ru_metas
            ]

            logger.info("Отдана дефолтная метадата: {}".format(metas[0].model_dump()))
            return metas

    async def _process_product_meta(
        self,
        new_ru_metas: list[str] | None,
        existing_metas: list[ProductMeta] | None = None,
    ) -> list[dict] | None:
        """
        Обрабатывает список метаданных товара. Сопоставляет новые характеристики
        с уже существующими, чтобы избежать лишних вызовов Alltokens API.
        Для новых характеристик вызывает AI-сервис Alltokens для перевода и генерации ключей.
        """
        if new_ru_metas is None:
            return None

        if not new_ru_metas:
            return []

        existing_map = {}
        if existing_metas:
            for item in existing_metas:
                if isinstance(item, dict):
                    ru_val = item.get("values", {}).get(Locale.RU) or item.get("values", {}).get("ru")
                    key = item.get("key")
                    values = item.get("values", {})
                else:
                    ru_val = item.values.get(Locale.RU) or item.values.get("ru")
                    key = item.key
                    values = item.values

                if ru_val:
                    existing_map[ru_val.strip().lower()] = {
                        "key": key,
                        "values": {
                            "ru": values.get(Locale.RU) or values.get("ru"),
                            "en": values.get(Locale.EN) or values.get("en"),
                        }
                    }

        to_translate = []
        result_metas = []

        for ru_meta in new_ru_metas:
            ru_meta_clean = ru_meta.strip().lower()
            if ru_meta_clean in existing_map:
                result_metas.append(existing_map[ru_meta_clean])
            else:
                to_translate.append(ru_meta)

        if to_translate:
            logger.info("Отправка новых характеристик на перевод через Alltokens: {}".format(to_translate))
            translated_new = await self._create_product_meta(to_translate, ai_service=self._ai_service)
            if translated_new:
                for item in translated_new:
                    if isinstance(item, dict):
                        result_metas.append(item)
                    else:
                        result_metas.append(item.model_dump(mode="json"))

        final_metas = []
        for ru_meta in new_ru_metas:
            ru_meta_clean = ru_meta.strip().lower()
            found = False
            for m in result_metas:
                ru_val = m["values"]["ru"]
                if ru_val and ru_val.strip().lower() == ru_meta_clean:
                    final_metas.append(m)
                    found = True
                    break
            if not found:
                key = slugify(ru_meta)
                final_metas.append({
                    "key": key,
                    "values": {
                        "ru": ru_meta,
                        "en": ru_meta
                    }
                })

        return final_metas




class InventoryService(SessionService):
    """
    Сервис управления запасами товаров на складе.
    """
    def __init__(self, session: AsyncSession):
        """
        Инициализирует сервис с сессией базы данных и DAO товаров.
        """
        self._session = session
        self._products_dao = ProductsDAO(session)

    async def subtract(
        self,
        product_id: int,
        count: int,
    ) -> None:
        """
        Вычитает указанное количество товара из складских запасов.
        Неявно вызывает decrease_quantity в DAO.
        """
        logger.info("Запрос на уменьшение запасов товара {} на количество: {}".format(product_id, count))
        updated = await self._products_dao.decrease_quantity(
            product_id=product_id,
            count=count,
        )
        if updated:
            logger.info("Запасы товара {} успешно уменьшены на {}.".format(product_id, count))
        else:
            product = await self._products_dao.find_one_or_none_by_id(product_id)
            if not product:
                logger.warning("Товар с ID {} не найден при попытке списания".format(product_id))
                raise ProductNotFoundError(f"Товар с ID {product_id} не найден")
            
            logger.warning(
                "Недостаточно товара с ID {} на складе при попытке списания. Запрошено: {}, доступно: {}"
                .format(product_id, count, product.quantity)
            )
            from src.orders.exceptions import OutOfStockError
            raise OutOfStockError(
                product_id=product_id,
                requested=count,
                available=product.quantity,
            )

    async def add(
        self,
        product_id: int,
        count: int,
    ) -> None:
        """
        Добавляет указанное количество товара в складские запасы.
        Неявно вызывает increase_quantity в DAO.
        """
        logger.info("Запрос на увеличение запасов товара {} на количество: {}".format(product_id, count))
        updated = await self._products_dao.increase_quantity(
            product_id=product_id,
            count=count,
        )
        if not updated:
            product = await self._products_dao.find_one_or_none_by_id(product_id)
            if not product:
                logger.warning("Товар с ID {} не найден при попытке пополнения".format(product_id))
                raise ProductNotFoundError(f"Товар с ID {product_id} не найден")