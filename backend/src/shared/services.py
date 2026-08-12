
from abc import ABC, abstractmethod
from typing import Type
import os
import uuid
import shutil
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import anyio
import aiofiles
from src.config import settings, BASE_DIR
import logging

logger = logging.getLogger(__name__)
from src.infrastructure.exceptions import (
    InvalidFileExtensionError,
    FileTooLargeError,
    MediaSaveError,
)

class Service(ABC):
    """
    Абстрактный базовый класс для всех сервисов приложения.
    """
    pass


class SessionService(Service):
    """
    Базовый класс сервиса, требующего активную сессию базы данных для работы.
    """
    @abstractmethod
    def __init__(self, session: AsyncSession):
        """
        Инициализирует сервис с сессией базы данных.
        """
        self._session = session


class MediaService(Service):
    """
    Сервис для работы с медиафайлами (загрузка, сохранение, удаление).
    """
    def __init__(self):
        """
        Инициализирует настройки медиафайлов из конфигурации приложения.
        """
        self._settings = settings.media

    async def save(self, file: UploadFile) -> str:
        """
        Проверяет формат и размер загружаемого файла, а затем сохраняет его на диск.
        Возвращает относительный путь к сохраненному файлу.
        Неявно закрывает объект загруженного файла при завершении операции.
        """
        logger.info("Запрос на сохранение файла {} с типом {}".format(file.filename, file.content_type))
        if file.content_type not in self._settings.extensions:
            logger.warning("Недопустимое расширение файла: {}".format(file.content_type))
            raise InvalidFileExtensionError(
                f"Недопустимый формат файла. Разрешены: {', '.join(self._settings.extensions)}"
            )

        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > self._settings.max_file_size:
            logger.warning("Размер файла {} ({} байт) превышает лимит в {}".format(file.filename, file_size, self._settings.max_file_size))
            raise FileTooLargeError(
                f"Файл слишком большой. Максимальный размер: {self._settings.max_file_size // (1024 * 1024)} МБ"
            )

        extension = file.content_type.split("/")[-1]
        unique_filename = f"{uuid.uuid4()}.{extension}"
        file_path = os.path.join(self._settings.dir, unique_filename)

        try:
            def _write():
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            await anyio.to_thread.run_sync(_write)
            logger.info("Файл успешно сохранен на диск по пути: {}".format(file_path))
        except Exception as e:
            logger.error("Не удалось записать файл {} на диск: {}".format(file.filename, e))
            raise MediaSaveError(f"Ошибка при сохранении файла: {str(e)}")
        finally:
            await file.close()

        return f"/{self._settings.dir}/{unique_filename}"

    async def append_chunk(self, upload_id: str, file: UploadFile) -> None:
        """
        Добавляет чанк к временному файлу.
        """
        tmp_dir = os.path.join(self._settings.dir, ".tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        
        tmp_file_path = os.path.join(tmp_dir, upload_id)
        try:
            def _write():
                with open(tmp_file_path, "ab") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            await anyio.to_thread.run_sync(_write)
        except Exception as e:
            logger.error(f"Не удалось записать чанк {upload_id}: {e}")
            raise MediaSaveError(f"Ошибка при сохранении чанка: {str(e)}")
        finally:
            await file.close()

    async def append_chunk_bytes(self, upload_id: str, content: bytes) -> None:
        """
        Добавляет сырые байты чанка к временному файлу.
        """
        tmp_dir = os.path.join(self._settings.dir, ".tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        
        tmp_file_path = os.path.join(tmp_dir, upload_id)
        try:
            def _write():
                with open(tmp_file_path, "ab") as buffer:
                    buffer.write(content)
            await anyio.to_thread.run_sync(_write)
        except Exception as e:
            logger.error(f"Не удалось записать сырые байты чанка {upload_id}: {e}")
            raise MediaSaveError(f"Ошибка при сохранении чанка: {str(e)}")

    async def finalize_chunked_upload(self, upload_id: str, content_type: str) -> str:
        """
        Проверяет и перемещает собранный файл. Возвращает итоговый путь.
        """
        tmp_dir = os.path.join(self._settings.dir, ".tmp")
        tmp_file_path = os.path.join(tmp_dir, upload_id)

        if not os.path.exists(tmp_file_path):
            raise FileNotFoundError("Временный файл не найден.")

        if content_type not in self._settings.extensions:
            os.remove(tmp_file_path)
            raise InvalidFileExtensionError(
                f"Недопустимый формат файла. Разрешены: {', '.join(self._settings.extensions)}"
            )

        file_size = os.path.getsize(tmp_file_path)
        if file_size > self._settings.max_file_size:
            os.remove(tmp_file_path)
            raise FileTooLargeError(
                f"Файл слишком большой. Максимальный размер: {self._settings.max_file_size // (1024 * 1024)} МБ"
            )

        extension = content_type.split("/")[-1]
        unique_filename = f"{uuid.uuid4()}.{extension}"
        final_file_path = os.path.join(self._settings.dir, unique_filename)

        try:
            shutil.move(tmp_file_path, final_file_path)
        except Exception as e:
            logger.error(f"Не удалось финализировать загрузку {upload_id}: {e}")
            raise MediaSaveError(f"Ошибка при сохранении итогового файла: {str(e)}")

        return f"/{self._settings.dir}/{unique_filename}"

    @staticmethod
    async def delete(path: str) -> None:
        """
        Удаляет файл с диска по указанному относительному пути.
        В случае отсутствия файла возбуждает исключение FileNotFoundError.
        """
        logger.info("Запрос на удаление файла по пути: {}".format(path))
        absolute_path = BASE_DIR / path.lstrip("/")

        file_exists = await anyio.to_thread.run_sync(os.path.exists, absolute_path)

        if file_exists:
            try:
                await anyio.to_thread.run_sync(os.remove, absolute_path)
                logger.info("Файл успешно удален по пути: {}".format(absolute_path))
            except Exception as e:
                logger.error("Ошибка при асинхронном удалении файла {}: {}".format(absolute_path, e))
                raise MediaSaveError(f"Не удалось удалить файл: {e}")
        else:
            logger.warning("Файл для удаления не найден: {}".format(absolute_path))
            raise FileNotFoundError("Указанный файл не найден для удаления.")






