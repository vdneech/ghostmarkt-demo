from typing import Generic, Type, TypeVar, List, Any, Dict, Optional
from sqlalchemy import select, func, update as sqlalchemy_update, delete as sqlalchemy_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.interfaces import ORMOption
from pydantic import BaseModel

import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")

class BaseDAO(Generic[T]):
    """
    Базовый класс для работы с базой данных (Data Access Object).
    Предоставляет CRUD-операции, фильтрацию с поддержкой Pydantic-моделей
    и автоматическое логирование операций.
    """
    model: Type[T] = None

    def __init__(self, session: AsyncSession):
        """
        Инициализирует экземпляр DAO с сессией базы данных.
        """
        self._session = session
        if self.model is None:
            raise ValueError("Модель должна быть указана в дочернем классе")

    def _apply_filters(
        self,
        query: Any,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Применяет фильтры к SQLAlchemy-запросу.
        Конвертирует Pydantic-модели в словари, исключая None-значения.
        Поддерживает Django-like операторы (например, price__gte=100) и
        частичный поиск без учета регистра по полю 'name'.
        """
        filter_dict = {}
        if filters is not None:
            if isinstance(filters, BaseModel):
                filter_dict.update(filters.model_dump(exclude_none=True))
            elif isinstance(filters, dict):
                filter_dict.update(filters)
        filter_dict.update(kwargs)

        for key, value in filter_dict.items():
            if value is None:
                continue

            if "__" in key:
                attr_name, op = key.split("__", 1)
                if not hasattr(self.model, attr_name):
                    raise ValueError(f"Модель {self.model.__name__} не имеет атрибута {attr_name}")
                attr = getattr(self.model, attr_name)

                if op == "gte":
                    query = query.where(attr >= value)
                elif op == "lte":
                    query = query.where(attr <= value)
                elif op == "gt":
                    query = query.where(attr > value)
                elif op == "lt":
                    query = query.where(attr < value)
                elif op == "ilike":
                    query = query.where(attr.ilike(value))
                elif op == "like":
                    query = query.where(attr.like(value))
                elif op == "in":
                    query = query.where(attr.in_(value))
                elif op == "contains":
                    query = query.where(attr.contains(value))
                else:
                    raise ValueError(f"Неподдерживаемый оператор {op} в фильтре {key}")
            else:
                if not hasattr(self.model, key):
                    raise ValueError(f"Модель {self.model.__name__} не имеет атрибута {key}")
                attr = getattr(self.model, key)
                if key == "name" and isinstance(value, str):
                    query = query.where(attr.ilike(f"%{value}%"))
                else:
                    query = query.where(attr == value)
        return query

    def _extract_values(self, values: Optional[BaseModel | Dict[str, Any]]) -> Dict[str, Any]:
        """
        Извлекает словарь значений для вставки или обновления.
        Если передана модель Pydantic, извлекаются только явно установленные поля.
        """
        if values is None:
            return {}
        if isinstance(values, BaseModel):
            return values.model_dump(exclude_unset=True)
        return values

    async def find_one_or_none_by_id(self, data_id: int, *options: ORMOption) -> Optional[T]:
        """
        Находит одну запись по ее идентификатору ID.
        """
        logger.info("Запрос на поиск {} по ID: {}".format(self.model.__name__, data_id))
        try:
            query = select(self.model).filter_by(id=data_id)
            if options:
                query = query.options(*options)

            result = await self._session.execute(query)
            record = result.scalar_one_or_none()
            if record:
                logger.info("Запись {} с ID {} найдена.".format(self.model.__name__, data_id))
            else:
                logger.info("Запись {} с ID {} не найдена.".format(self.model.__name__, data_id))
            return record
        except SQLAlchemyError as e:
            logger.error("Ошибка при поиске записи {} с ID {}: {}".format(self.model.__name__, data_id, e))
            raise

    async def find_one_or_none(
        self,
        *options: ORMOption,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[T]:
        """
        Находит первую запись, удовлетворяющую указанным фильтрам, или возвращает None.
        """
        logger.info("Запрос на поиск одной записи {} по фильтрам: {}, {}".format(self.model.__name__, filters, kwargs))
        try:
            query = select(self.model)
            query = self._apply_filters(query, filters, **kwargs)
            query = query.limit(1)
            if options:
                query = query.options(*options)
            result = await self._session.execute(query)
            record = result.scalars().first()
            if record:
                logger.info("Запись {} найдена по фильтрам.".format(self.model.__name__))
            else:
                logger.info("Запись {} не найдена по фильтрам.".format(self.model.__name__))
            return record
        except SQLAlchemyError as e:
            logger.error("Ошибка при поиске одной записи {} по фильтрам: {}".format(self.model.__name__, e))
            raise

    async def find_all(
        self,
        *options: ORMOption,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[T]:
        """
        Находит все записи, удовлетворяющие указанным фильтрам.
        """
        logger.info("Запрос на поиск всех записей {} по фильтрам: {}, {}".format(self.model.__name__, filters, kwargs))
        try:
            query = select(self.model)
            query = self._apply_filters(query, filters, **kwargs)
            if options:
                query = query.options(*options)
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info("Найдено {} записей для модели {}.".format(len(records), self.model.__name__))
            return list(records)
        except SQLAlchemyError as e:
            logger.error("Ошибка при поиске всех записей {}: {}".format(self.model.__name__, e))
            raise

    async def find_all_by_ids(self, ids: List[int]) -> List[T]:
        """
        Находит все записи с идентификаторами, содержащимися в переданном списке ids.
        """
        logger.info("Запрос на поиск записей {} по списку ID: {}".format(self.model.__name__, ids))
        try:
            query = select(self.model).where(self.model.id.in_(ids))
            result = await self._session.execute(query)
            records = result.scalars().all()
            logger.info("Найдено {} записей по списку ID.".format(len(records)))
            return list(records)
        except SQLAlchemyError as e:
            logger.error("Ошибка при поиске записей по списку ID {}: {}".format(ids, e))
            raise

    async def add(self, **values: Any) -> T:
        """
        Создает новую запись в базе данных с указанными значениями и синхронизирует состояние сессии.
        Неявно вызывает метод flush для получения сгенерированного ID без завершения транзакции.
        """
        logger.info("Добавление новой записи {}".format(self.model.__name__))
        try:
            new_instance = self.model(**values)
            self._session.add(new_instance)
            await self._session.flush()
            logger.info("Запись {} успешно добавлена в сессию и синхронизирована (flush).".format(self.model.__name__))
            return new_instance
        except SQLAlchemyError as e:
            logger.error("Ошибка при добавлении записи {}: {}".format(self.model.__name__, e))
            raise

    async def add_many(self, instances: List[Dict[str, Any]]) -> List[T]:
        """
        Добавляет несколько новых записей в базу данных.
        Неявно вызывает метод flush для синхронизации объектов с БД.
        """
        logger.info("Добавление нескольких записей {}. Количество: {}".format(self.model.__name__, len(instances)))
        try:
            new_instances = [self.model(**values) for values in instances]
            self._session.add_all(new_instances)
            await self._session.flush()
            logger.info("Успешно добавлено {} записей {} (flush).".format(len(new_instances), self.model.__name__))
            return new_instances
        except SQLAlchemyError as e:
            logger.error("Ошибка при добавлении нескольких записей {}: {}".format(self.model.__name__, e))
            raise

    async def update(
        self,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        values: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> int:
        """
        Обновляет записи, удовлетворяющие фильтрам, новыми значениями values.
        Неявно вызывает метод flush для фиксации изменений в текущей транзакции.
        """
        logger.info("Обновление записей {}".format(self.model.__name__))
        extracted_values = self._extract_values(values)
        if not extracted_values:
            logger.warning("Для обновления не переданы значения")
            return 0
        try:
            query = sqlalchemy_update(self.model)
            query = self._apply_filters(query, filters, **kwargs)
            query = query.values(**extracted_values).execution_options(synchronize_session="fetch")

            result = await self._session.execute(query)
            rowcount = result.rowcount
            await self._session.flush()
            logger.info("Обновлено {} записей {} (flush).".format(rowcount, self.model.__name__))
            return rowcount
        except SQLAlchemyError as e:
            logger.error("Ошибка при обновлении записей {}: {}".format(self.model.__name__, e))
            raise

    async def update_returning(
        self,
        *options: ORMOption,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        values: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[T]:
        """
        Обновляет запись, удовлетворяющую фильтрам, и возвращает обновленный объект.
        Неявно вызывает метод flush для синхронизации объекта с БД.
        """
        logger.info("Обновление с возвратом объекта {}".format(self.model.__name__))
        extracted_values = self._extract_values(values)
        if not extracted_values:
            logger.warning("Для обновления не переданы значения. Возвращаем существующий объект.")
            return await self.find_one_or_none(*options, filters=filters, **kwargs)

        try:
            query = sqlalchemy_update(self.model)
            query = self._apply_filters(query, filters, **kwargs)
            query = query.values(**extracted_values).returning(self.model).execution_options(synchronize_session="fetch")

            if options:
                query = query.options(*options)

            result = await self._session.execute(query)
            updated_object = result.scalar_one_or_none()
            await self._session.flush()
            if updated_object:
                logger.info("Запись {} успешно обновлена и получена (flush).".format(self.model.__name__))
            else:
                logger.warning("Запись {} не найдена для обновления.".format(self.model.__name__))
            return updated_object
        except SQLAlchemyError as e:
            logger.error("Ошибка при обновлении записи с возвратом {}: {}".format(self.model.__name__, e))
            raise

    async def delete(
        self,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> int:
        """
        Удаляет записи из базы данных, удовлетворяющие указанным фильтрам.
        Неявно вызывает метод flush для синхронизации изменений с БД.
        """
        logger.info("Удаление записей {}".format(self.model.__name__))
        try:
            query = sqlalchemy_delete(self.model)
            query = self._apply_filters(query, filters, **kwargs)
            result = await self._session.execute(query)
            rowcount = result.rowcount
            await self._session.flush()
            logger.info("Удалено {} записей {} (flush).".format(rowcount, self.model.__name__))
            return rowcount
        except SQLAlchemyError as e:
            logger.error("Ошибка при удалении записей {}: {}".format(self.model.__name__, e))
            raise

    async def count(
        self,
        filters: Optional[BaseModel | Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> int:
        """
        Подсчитывает количество записей, удовлетворяющих указанным фильтрам.
        """
        logger.info("Подсчет количества записей {}".format(self.model.__name__))
        try:
            query = select(func.count(self.model.id))
            query = self._apply_filters(query, filters, **kwargs)
            result = await self._session.execute(query)
            records_count = result.scalar() or 0
            logger.info("Найдено {} записей {}.".format(records_count, self.model.__name__))
            return records_count
        except SQLAlchemyError as e:
            logger.error("Ошибка при подсчете записей {}: {}".format(self.model.__name__, e))
            raise

    async def bulk_update(self, records: List[Dict[str, Any]]) -> int:
        """
        Выполняет массовое обновление записей по списку словарей (каждый должен содержать 'id').
        Неявно вызывает метод flush для синхронизации изменений с БД.
        """
        logger.info("Массовое обновление записей {}. Количество: {}".format(self.model.__name__, len(records)))
        try:
            updated_count = 0
            for record_dict in records:
                if 'id' not in record_dict:
                    continue

                update_data = {k: v for k, v in record_dict.items() if k != 'id'}
                stmt = (
                    sqlalchemy_update(self.model)
                    .filter_by(id=record_dict['id'])
                    .values(**update_data)
                )
                result = await self._session.execute(stmt)
                updated_count += result.rowcount

            await self._session.flush()
            logger.info("Массовое обновление завершено. Обновлено {} записей (flush).".format(updated_count))
            return updated_count
        except SQLAlchemyError as e:
            logger.error("Ошибка при массовом обновлении записей {}: {}".format(self.model.__name__, e))
            raise

    @classmethod
    def get_all_subclasses(cls) -> List[Type['BaseDAO']]:
        """
        Рекурсивно находит всех наследников BaseDAO.
        """
        subclasses = []
        for subclass in cls.__subclasses__():
            subclasses.append(subclass)
            subclasses.extend(subclass.get_all_subclasses())
        return subclasses