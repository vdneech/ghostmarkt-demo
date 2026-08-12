import os
from pathlib import Path
import shutil
import decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import anyio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import Locale
from src.config import settings, BASE_DIR
from src.infrastructure.ai.services import AIService
from src.products.services import ProductService, InventoryService
from src.shared.services import MediaService
from src.products.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductPartiallyUpdate,
    ProductFilter,
    Dimensions, ProductMeta,
)
from src.products.exceptions import (
    ProductNotFoundError,
    ProductAlreadyExistsError,
    ProductImageError,
    ProductTranslationError,
)
from src.orders.exceptions import OutOfStockError
from src.infrastructure.exceptions import (
    InvalidFileExtensionError,
    FileTooLargeError,
)


class TestProductServices:

    @pytest.mark.asyncio
    async def test_create_product_success(self, test_session: AsyncSession):
        service = ProductService(test_session)
        data = ProductCreate(
            name="Супер Рассеиватель",
            price=decimal.Decimal("350.00"),
            quantity=15,
            weight=100,
            dimensions=Dimensions(length=12, width=14, height=16),
            description="Отличный рассеиватель для вспышки",
            is_active=True,
        )
        product = await service.create_product(data)
        assert product.name == "Супер Рассеиватель"
        assert product.price == decimal.Decimal("350.00")
        assert product.quantity == 15
        assert product.dimensions.length == 12

    @pytest.mark.asyncio
    async def test_get_one_success(self, test_session: AsyncSession, product_factory):
        p = await product_factory(name="Товар 1")
        service = ProductService(test_session)
        retrieved = await service.get_one(p.id)
        assert retrieved.id == p.id
        assert retrieved.name == "Товар 1"

    @pytest.mark.asyncio
    async def test_get_one_not_found(self, test_session: AsyncSession):
        service = ProductService(test_session)
        with pytest.raises(ProductNotFoundError):
            await service.get_one(99999)

    @pytest.mark.asyncio
    async def test_get_many_filtering(self, test_session: AsyncSession, product_factory):
        await product_factory(name="Красный софтбокс", is_active=True)
        await product_factory(name="Синий софтбокс", is_active=False)

        service = ProductService(test_session)
        
        # Filter active
        res_active = await service.get_many(ProductFilter(is_active=True))
        assert res_active.total == 1
        assert res_active.products[0].name == "Красный софтбокс"

        # Filter name (default is_admin=False -> active only)
        res_name = await service.get_many(ProductFilter(name="софтбокс"))
        assert res_name.total == 1

        # Filter name (is_admin=True -> gets all)
        res_name_admin = await service.get_many(ProductFilter(name="софтбокс"), is_admin=True)
        assert res_name_admin.total == 2

    @pytest.mark.asyncio
    async def test_update_product(self, test_session: AsyncSession, product_factory):
        p = await product_factory(name="Старый товар", price=decimal.Decimal("100"))
        service = ProductService(test_session)
        
        # Partial update
        updated = await service.update(
            p.id,
            ProductPartiallyUpdate(price=decimal.Decimal("150.00")),
            partial=True,
        )
        assert updated.price == decimal.Decimal("150.00")
        assert updated.name == "Старый товар"

    @pytest.mark.asyncio
    async def test_delete_product(self, test_session: AsyncSession, product_factory):
        p = await product_factory()
        service = ProductService(test_session)
        await service.delete(p.id)
        
        with pytest.raises(ProductNotFoundError):
            await service.get_one(p.id)

    @pytest.mark.asyncio
    async def test_translate_product_success(self, test_session: AsyncSession, product_factory, mocker):
        p = await product_factory(name="Вспышка", description="Мощная вспышка")
        
        mock_ai = AsyncMock()
        mock_ai.text_to_text.return_value = '{"name": "Flashlight", "description": "Powerful flashlight"}'
        
        service = ProductService(test_session)
        translated = await service.translate_product(p.id, mock_ai)
        
        assert translated.name_en == "Flashlight"
        assert translated.description_en == "Powerful flashlight"
        mock_ai.text_to_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_product_with_meta(self, test_session: AsyncSession):
        mock_ai = MagicMock(spec=AIService)
        mock_ai.text_to_text = AsyncMock(return_value='{"metas": [{"key": "water_proof", "values": {"ru": "Водонепроницаемый", "en": "Waterproof"}}]}')
        
        service = ProductService(test_session, ai_service=mock_ai)
        data = ProductCreate(
            name="Гидро-чехол",
            price=decimal.Decimal("250.00"),
            quantity=10,
            weight=50,
            dimensions=Dimensions(length=10, width=5, height=2),
            description="Отличный водонепроницаемый чехол",
            meta=["Водонепроницаемый"],
            is_active=True,
        )
        product = await service.create_product(data)
        
        assert product.name == "Гидро-чехол"
        assert len(product.meta) == 1
        assert product.meta[0].key == "water_proof"
        assert product.meta[0].values[Locale.RU] == "Водонепроницаемый"
        assert product.meta[0].values[Locale.EN] == "Waterproof"
        mock_ai.text_to_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_product_meta(self, test_session: AsyncSession, product_factory):
        p = await product_factory(
            name="Товар с метаданными",
            price=decimal.Decimal("100"),
            description="...",
            meta=[{"key": "old_feature", "values": {"ru": "Старая фича", "en": "Old feature"}}]
        )
        
        mock_ai = MagicMock(spec=AIService)
        mock_ai.text_to_text = AsyncMock(return_value='{"metas": [{"key": "new_feature", "values": {"ru": "Новая фича", "en": "New feature"}}]}')
        
        service = ProductService(test_session, ai_service=mock_ai)
        
        updated = await service.update(
            p.id,
            ProductUpdate(
                name="Товар с метаданными",
                price=decimal.Decimal("100"),
                quantity=10,
                weight=100,
                dimensions=Dimensions(length=10, width=10, height=10),
                meta=["Старая фича", "Новая фича"],
                is_active=True,
                description="...",
            ),
            partial=False
        )
        
        assert len(updated.meta) == 2
        assert updated.meta[0].key == "old_feature"
        assert updated.meta[1].key == "new_feature"
        assert updated.meta[1].values[Locale.EN] == "New feature"
        
        mock_ai.text_to_text.assert_called_once()
        call_args = mock_ai.text_to_text.call_args[1]
        assert "Новая фича" in call_args["user_prompt"]
        assert "Старая фича" not in call_args["user_prompt"]


class TestInventoryService:

    @pytest.mark.asyncio
    async def test_subtract_success(self, test_session: AsyncSession, product_factory):
        p = await product_factory(quantity=10)
        inv_service = InventoryService(test_session)
        
        await inv_service.subtract(p.id, 4)
        await test_session.refresh(p)
        assert p.quantity == 6

    @pytest.mark.asyncio
    async def test_subtract_out_of_stock(self, test_session: AsyncSession, product_factory):
        p = await product_factory(quantity=5)
        inv_service = InventoryService(test_session)
        
        with pytest.raises(OutOfStockError) as exc_info:
            await inv_service.subtract(p.id, 10)
        
        assert exc_info.value.product_id == p.id
        assert exc_info.value.requested == 10
        assert exc_info.value.available == 5

    @pytest.mark.asyncio
    async def test_subtract_product_not_found(self, test_session: AsyncSession):
        inv_service = InventoryService(test_session)
        with pytest.raises(ProductNotFoundError):
            await inv_service.subtract(99999, 1)

    @pytest.mark.asyncio
    async def test_create_product_meta(self):
        ru_metas = ["Характеристика продукта", ]
        metadata = await ProductService._create_product_meta(
            ru_metas=ru_metas,
            ai_service=AIService()
        )

        assert len(metadata) == 1
        assert metadata[0].values[Locale.RU] == "Характеристика продукта"

class TestMediaService:

    @pytest.fixture(autouse=True)
    def setup_dirs(self):
        # Ensure test media dir exists
        self.media_dir = BASE_DIR / "media_test"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        
        # Override media settings for testing
        self.orig_dir = settings.media.dir
        self.orig_exts = settings.media.extensions
        self.orig_max_size = settings.media.max_file_size
        
        settings.media.dir = "media_test"
        settings.media.extensions = ["image/jpeg", "image/png"]
        settings.media.max_file_size = 1024 * 1024 # 1MB
        
        yield
        
        # Teardown and clean up test directory completely
        settings.media.dir = self.orig_dir
        settings.media.extensions = self.orig_exts
        settings.media.max_file_size = self.orig_max_size
        
        if self.media_dir.exists():
            shutil.rmtree(self.media_dir)

    @pytest.mark.asyncio
    async def test_media_crud_lifecycle(self):
        media_service = MediaService()
        
        # Mock UploadFile
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test_image.png"
        mock_file.content_type = "image/png"
        
        # Real file-like object using BytesIO
        import io
        mock_file.file = io.BytesIO(b"fake file content")
        mock_file.close = AsyncMock()

        # 1. Save file
        saved_path = await media_service.save(mock_file)
        assert saved_path.startswith("/media_test/")
        assert saved_path.endswith(".png")
        
        # Verify file is created on the filesystem
        abs_path = BASE_DIR / saved_path.lstrip("/")
        assert abs_path.exists()
        assert abs_path.is_file()

        # 2. Delete file
        await media_service.delete(saved_path)
        assert not abs_path.exists()

    @pytest.mark.asyncio
    async def test_media_invalid_extension(self):
        media_service = MediaService()
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "malicious.exe"
        mock_file.content_type = "application/x-msdownload"
        mock_file.close = AsyncMock()

        with pytest.raises(InvalidFileExtensionError):
            await media_service.save(mock_file)

    @pytest.mark.asyncio
    async def test_media_file_too_large(self):
        media_service = MediaService()
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "huge_image.jpg"
        mock_file.content_type = "image/jpeg"
        mock_file.close = AsyncMock()
        
        # Fake size: 2MB (exceeds 1MB limit) using BytesIO
        import io
        mock_file.file = io.BytesIO(b"0" * (2 * 1024 * 1024))

        with pytest.raises(FileTooLargeError):
            await media_service.save(mock_file)

    @pytest.mark.asyncio
    async def test_media_delete_non_existent(self):
        media_service = MediaService()
        with pytest.raises(FileNotFoundError):
            await media_service.delete("/media_test/does_not_exist.png")

    @pytest.mark.asyncio
    async def test_process_product_meta_optimization(self, test_session: AsyncSession, mocker):
        # Mock AI service to return translation for new field only
        mock_ai = MagicMock(spec=AIService)
        mock_ai.text_to_text = AsyncMock(return_value='{"metas": [{"key": "new_feature", "values": {"ru": "Новая фича", "en": "New feature"}}]}')

        service = ProductService(test_session, ai_service=mock_ai)

        existing_meta = [
            ProductMeta(key="old_feature", values={Locale.RU: "Старая фича", Locale.EN: "Old feature"}).model_dump()
        ]

        new_ru_metas = ["Старая фича", "Новая фича"]

        result = await service._process_product_meta(new_ru_metas, existing_metas=existing_meta)

        assert len(result) == 2

        # Check order and keys
        assert result[0]["key"] == "old_feature"
        assert result[0]["values"]["ru"] == "Старая фича"
        assert result[0]["values"]["en"] == "Old feature"

        assert result[1]["key"] == "new_feature"
        assert result[1]["values"]["ru"] == "Новая фича"
        assert result[1]["values"]["en"] == "New feature"

        mock_ai.text_to_text.assert_called_once()
        call_args = mock_ai.text_to_text.call_args[1]
        assert "Новая фича" in call_args["user_prompt"]
        assert "Старая фича" not in call_args["user_prompt"]
