import pytest
from unittest.mock import AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.exceptions import (
    MetadataValidationError,
    ProductNotFoundError,
    OrderNotFoundError,
    OrderDomainError,
    OutOfStockError,
)
from src.orders.services import OrderService
from src.orders.schemas import OrderCreate, OrderItemCreate, OrderUpdate
from src.orders.models import PaymentStatus, Order


class TestOrderService:

    @pytest.mark.asyncio
    async def test_validate_and_parse_meta(self, test_session, product_factory):
        product = await product_factory(
            meta=[{"key": "char_key", "values": {"ru": "char_value", "en": "char_value"}}]
        )
        text = "char_value: testing"
        service = OrderService(test_session)
        assert service.validate_and_parse_meta(text, product) == {"char_key": "testing"}

    @pytest.mark.asyncio
    async def test_validate_and_parse_meta_invalid(self, test_session, product_factory):
        product = await product_factory(
            meta=[{"key": "char_key", "values": {"ru": "char_value", "en": "char_value"}}]
        )
        text = "Some string"
        service = OrderService(test_session)
        with pytest.raises(MetadataValidationError):
            service.validate_and_parse_meta(text, product)

    @pytest.mark.asyncio
    async def test_validate_and_parse_empty_meta(self, test_session, product_factory):
        product = await product_factory(
            meta=[]
        )
        text = "Some string"
        service = OrderService(test_session)
        meta = service.validate_and_parse_meta(text, product)
        assert meta == {}

    @pytest.mark.asyncio
    async def test_create_order(self, test_session, product_factory, user_factory):
        product = await product_factory(price=Decimal("150"), quantity=10)
        user = await user_factory()

        service = OrderService(test_session)
        order_data = OrderCreate(
            address="Test address",
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="KSD123",
            items=[
                OrderItemCreate(
                    product_id=product.id,
                    quantity=2
                )
            ]
        )
        order_resp = await service.create_order(user, order_data)
        
        assert order_resp.total_amount == Decimal("350")  # (150 * 2) + 50
        assert order_resp.payment_status == PaymentStatus.PENDING
        assert order_resp.payment_url is not None

    @pytest.mark.asyncio
    async def test_create_order_product_not_found(self, test_session, user_factory):
        user = await user_factory()
        service = OrderService(test_session)
        order_data = OrderCreate(
            address="Test address",
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="KSD123",
            items=[
                OrderItemCreate(
                    product_id=99999,  # Non-existent ID
                    quantity=2
                )
            ]
        )
        with pytest.raises(ProductNotFoundError):
            await service.create_order(user, order_data)

    @pytest.mark.asyncio
    async def test_cancel_order(self, test_session, order_factory):
        order = order_factory
        service = OrderService(test_session)
        await service.cancel_order(order.id)
        
        await test_session.refresh(order)
        assert order.payment_status == PaymentStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, test_session):
        service = OrderService(test_session)
        with pytest.raises(OrderNotFoundError):
            await service.cancel_order(99999)

    @pytest.mark.asyncio
    async def test_delete_order(self, test_session, order_factory):
        order = order_factory
        service = OrderService(test_session)
        await service.delete(order.id)

        # Check deletion
        with pytest.raises(OrderNotFoundError):
            await service.get_by_id(order.id)

    @pytest.mark.asyncio
    async def test_finalize_order(self, test_session, order_factory):
        order = order_factory
        service = OrderService(test_session)
        await service.finalize_order(1234567, order.id)

        await test_session.refresh(order)
        assert order.telegram_message_id == 1234567

    @pytest.mark.asyncio
    async def test_update_order(self, test_session, order_factory):
        order = order_factory
        service = OrderService(test_session)
        
        updated_order = await service.update_order(
            data=OrderUpdate(payment_status=PaymentStatus.PAID),
            order_id=order.id
        )
        assert updated_order.payment_status == PaymentStatus.PAID
        assert updated_order.payment_date is not None

    @pytest.mark.asyncio
    async def test_get_by_id(self, test_session, order_factory):
        order = order_factory
        service = OrderService(test_session)
        
        order_resp = await service.get_by_id(order.id)
        assert order_resp.id == order.id

    @pytest.mark.asyncio
    async def test_get_many(self, test_session, order_factory, user_factory):
        user1 = await user_factory(telegram_chat_id=111, email="user1@example.com")
        user2 = await user_factory(telegram_chat_id=222, email="user2@example.com")
        
        order1 = order_factory
        order1.user = user1
        order1.user_id = user1.id
        
        order2 = Order(
            user_id=user2.id,
            total_amount=Decimal("150"),
            address="Address 2"
        )
        test_session.add(order2)
        
        await test_session.commit()
        
        service = OrderService(test_session)
        
        # All orders
        all_orders = await service.get_many()
        assert len(all_orders) >= 2
        
        # Filtered by user
        user1_orders = await service.get_many(user_id=user1.id)
        assert len(user1_orders) == 1
        assert user1_orders[0].id == order1.id

    @pytest.mark.asyncio
    async def test_create_order_metadata_validation_missing(self, test_session, product_factory, user_factory):
        # Product requires meta
        product = await product_factory(
            price=Decimal("100"), 
            quantity=10, 
            meta=[{"key": "engraving", "values": {"ru": "Гравировка", "en": "Engraving"}}]
        )
        user = await user_factory()
        service = OrderService(test_session)

        # No metadata provided
        order_data = OrderCreate(
            address="Test address",
            items=[OrderItemCreate(product_id=product.id, quantity=1)],
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="MSK",
        )

        with pytest.raises(MetadataValidationError) as exc:
            await service.create_order(user, order_data)
        assert "Гравировка" in str(exc.value)

    @pytest.mark.asyncio
    async def test_create_order_metadata_validation_success(self, test_session, product_factory, user_factory):
        product = await product_factory(
            price=Decimal("100"), 
            quantity=10, 
            meta=[{"key": "engraving", "values": {"ru": "Гравировка", "en": "Engraving"}}]
        )
        user = await user_factory()
        service = OrderService(test_session)

        order_data = OrderCreate(
            address="Test address",
            items=[OrderItemCreate(product_id=product.id, quantity=1, meta={"engraving": "С любовью"})],
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="MSK",
        )

        order = await service.create_order(user, order_data)
        assert order.payment_status == PaymentStatus.PENDING
        assert order.items[0].meta == {"engraving": "С любовью"}

    @pytest.mark.asyncio
    async def test_process_success_payment(self, test_session, order_factory, mocker):
        order = order_factory
        service = OrderService(test_session)
        
        notification_service_mock = AsyncMock()
        
        mocker.patch.object(service, "_delete_payment_message", new_callable=AsyncMock)
        mocker.patch.object(service, "_notify_admins", new_callable=AsyncMock)
        
        await service.process_success_payment(order, notification_service_mock)
        
        service._delete_payment_message.assert_called_once_with(order)
        service._notify_admins.assert_called_once_with(order, notification_service_mock)

    @pytest.mark.asyncio
    async def test_notify_admins(self, test_session, order_factory, mocker):
        order = order_factory
        service = OrderService(test_session)
        notification_service_mock = AsyncMock()
        
        mocker.patch("src.bot.texts.render_order_notification", return_value="Test message")
        
        await service._notify_admins(order, notification_service_mock)
        
        notification_service_mock.send_admins.assert_called_once_with(
            session=test_session, message="Test message"
        )

    @pytest.mark.asyncio
    async def test_create_order_inactive_product(self, test_session, product_factory, user_factory):
        product = await product_factory(price=Decimal("150"), quantity=10, is_active=False)
        user = await user_factory()
        service = OrderService(test_session)
        order_data = OrderCreate(
            address="Test address",
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="KSD123",
            items=[OrderItemCreate(product_id=product.id, quantity=1)]
        )
        with pytest.raises(OrderDomainError) as exc_info:
            await service.create_order(user, order_data)
        assert "деактивирован" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_zero_quantity_product(self, test_session, product_factory, user_factory):
        product = await product_factory(price=Decimal("150"), quantity=0, is_active=True)
        user = await user_factory()
        service = OrderService(test_session)
        order_data = OrderCreate(
            address="Test address",
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="KSD123",
            items=[OrderItemCreate(product_id=product.id, quantity=1)]
        )
        with pytest.raises(OutOfStockError):
            await service.create_order(user, order_data)

    @pytest.mark.asyncio
    async def test_order_stock_reservation_and_cancellation(self, test_session, product_factory, user_factory):
        product = await product_factory(price=Decimal("150"), quantity=10, is_active=True)
        user = await user_factory()
        service = OrderService(test_session)
        
        order_data = OrderCreate(
            address="Test address",
            shipment_cost=Decimal("50"),
            tariff_code=136,
            delivery_point="KSD123",
            items=[OrderItemCreate(product_id=product.id, quantity=3)]
        )

        # 1. Create order: check that stock is decremented immediately from 10 to 7
        order_resp = await service.create_order(user, order_data)
        assert order_resp.payment_status == PaymentStatus.PENDING
        
        # Refresh product from DB
        from src.products.dao import ProductsDAO
        products_dao = ProductsDAO(test_session)
        db_product = await products_dao.find_one_or_none_by_id(product.id)
        assert db_product.quantity == 7

        # 2. Cancel order: check that stock is restored back from 7 to 10
        await service.cancel_order(order_resp.id)
        db_product_after = await products_dao.find_one_or_none_by_id(product.id)
        assert db_product_after.quantity == 10
