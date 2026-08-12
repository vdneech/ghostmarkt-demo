import decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import BaseDAOTest
from src.products.models import Product
from src.products.dao import ProductsDAO
from src.products.schemas import ProductFilter


class TestProductsDAO(BaseDAOTest[Product]):
    model = Product

    @pytest.mark.asyncio
    async def test_decrease_quantity(self, test_session: AsyncSession):
        product = await self._create_object(
            test_session=test_session,
            name="Тестовый Рассеиватель",
            price=decimal.Decimal("100"),
            quantity=10,
            length=10,
            width=10,
            height=10,
        )
        await test_session.commit()

        product_dao = ProductsDAO(test_session)
        updated_count = await product_dao.decrease_quantity(product.id, 3)
        await test_session.commit()

        assert updated_count == 1
        await test_session.refresh(product)
        assert product.quantity == 7

    @pytest.mark.asyncio
    async def test_pydantic_filtering(self, test_session: AsyncSession):
        product_1 = await self._create_object(
            test_session=test_session,
            name="Тестовый Рассеиватель 1",
            price=decimal.Decimal("150"),
            is_active=True,
            length=10,
            width=10,
            height=10,
        )
        product_2 = await self._create_object(
            test_session=test_session,
            name="Тестовый Рассеиватель 2",
            price=decimal.Decimal("250"),
            is_active=False,
            length=10,
            width=10,
            height=10,
        )
        await test_session.commit()

        product_dao = ProductsDAO(test_session)

        filter_active = ProductFilter(is_active=True)
        active_products = await product_dao.find_all(filters=filter_active)
        assert len(active_products) == 1
        assert active_products[0].name == "Тестовый Рассеиватель 1"

        filter_name = ProductFilter(name="Рассеиватель")
        all_diffusers = await product_dao.find_all(filters=filter_name)
        assert len(all_diffusers) == 2
