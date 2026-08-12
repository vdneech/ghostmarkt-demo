import pytest
from decimal import Decimal
from httpx import AsyncClient
from src.config import settings
from src.orders.models import PaymentStatus, Order
from src.auth.services import AuthService


class TestOrderRoutes:

    def _get_auth_cookies(self, email: str) -> dict:
        token = AuthService.create_token(
            email=email,
            expires=3600,
        )
        return {settings.authentication.access_token.cookie_key: token}

    @pytest.mark.asyncio
    async def test_create_order(self, client: AsyncClient, product_factory, user_factory):
        product = await product_factory(price=Decimal("150"), quantity=10)
        user = await user_factory(email="customer@example.com")
        cookies = self._get_auth_cookies("customer@example.com")

        payload = {
            "address": "Moscow, Red Square 1",
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ],
            "shipment_cost": 50,
            "tariff_code": 136,
            "delivery_point": "KSD295"
        }
        response = await client.post("/api/orders/", json=payload, cookies=cookies)
        assert response.status_code == 201
        res_json = response.json()
        assert Decimal(res_json["total_amount"]) == Decimal("350")
        assert res_json["payment_status"] == "PENDING"
        assert "payment_url" in res_json

    @pytest.mark.asyncio
    async def test_get_all_orders_user_vs_admin(self, client: AsyncClient, order_factory, user_factory, test_session):
        user1 = await user_factory(telegram_chat_id=111, email="user1@example.com")
        user2 = await user_factory(telegram_chat_id=222, email="user2@example.com")
        admin = await user_factory(telegram_chat_id=333, email="admin@example.com", is_superuser=True)

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

        # Get for user1 (should only see user1's order)
        cookies = self._get_auth_cookies("user1@example.com")
        response = await client.get("/api/orders/", cookies=cookies)
        assert response.status_code == 200
        user_orders = response.json()
        assert len(user_orders) == 1
        assert user_orders[0]["id"] == order1.id

        # Get for admin (should see both orders)
        cookies_admin = self._get_auth_cookies("admin@example.com")
        response_admin = await client.get("/api/orders/", cookies=cookies_admin)
        assert response_admin.status_code == 200
        admin_orders = response_admin.json()
        assert len(admin_orders) >= 2

    @pytest.mark.asyncio
    async def test_get_order(self, client: AsyncClient, order_factory, user_factory, test_session):
        user1 = await user_factory(telegram_chat_id=111, email="user1@example.com")
        user2 = await user_factory(telegram_chat_id=222, email="user2@example.com")
        admin = await user_factory(telegram_chat_id=333, email="admin@example.com", is_superuser=True)

        order = order_factory
        order.user = user1
        order.user_id = user1.id
        await test_session.commit()

        # Get by owner (success)
        cookies_owner = self._get_auth_cookies("user1@example.com")
        response = await client.get(f"/api/orders/{order.id}/", cookies=cookies_owner)
        assert response.status_code == 200

        # Get by admin (success)
        cookies_admin = self._get_auth_cookies("admin@example.com")
        response = await client.get(f"/api/orders/{order.id}/", cookies=cookies_admin)
        assert response.status_code == 200

        # Get by other user (400 OrderDomainError)
        cookies_other = self._get_auth_cookies("user2@example.com")
        response = await client.get(f"/api/orders/{order.id}/", cookies=cookies_other)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_order_status(self, client: AsyncClient, order_factory, user_factory):
        admin = await user_factory(email="admin@example.com", is_superuser=True)
        user = await user_factory(email="user@example.com")
        order = order_factory

        # Patch by admin (success)
        cookies_admin = self._get_auth_cookies("admin@example.com")
        response = await client.patch(f"/api/orders/{order.id}/?status=PAID", cookies=cookies_admin)
        assert response.status_code == 200
        assert response.json()["payment_status"] == "PAID"

        # Patch by non-admin (403)
        cookies_user = self._get_auth_cookies("user@example.com")
        response = await client.patch(f"/api/orders/{order.id}/?status=PAID", cookies=cookies_user)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_order(self, client: AsyncClient, order_factory, user_factory):
        admin = await user_factory(email="admin@example.com", is_superuser=True)
        user = await user_factory(email="user@example.com")
        order = order_factory

        # Delete by non-admin (403)
        cookies_user = self._get_auth_cookies("user@example.com")
        response = await client.delete(f"/api/orders/{order.id}/", cookies=cookies_user)
        assert response.status_code == 403

        # Delete by admin (204)
        cookies_admin = self._get_auth_cookies("admin@example.com")
        response = await client.delete(f"/api/orders/{order.id}/", cookies=cookies_admin)
        assert response.status_code == 204


class TestWebhooks:

    @pytest.mark.asyncio
    async def test_create_order_webhook_success(self, client: AsyncClient, product_factory):
        product = await product_factory(id=1, price=Decimal("100"), quantity=10)
        payload = {
            "user": {
                "email": "customer@example.com",
                "first_name": "Customer",
                "last_name": "LastName",
                "phone": "+79991112233",
                "specialty": "Specialty"
            },
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ],
            "address": "Moscow, Red Square 1",
            "delivery": "CDEK",
            "tariff_code": 136,
            "delivery_point": "KSD295",
            "shipment_cost": 50
        }
        secret_token = settings.order.webhook_secret.get_secret_value()
        response = await client.post("/api/orders/webhooks/create", headers={"X-Webhook-Secret": secret_token}, json=payload)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_order_webhook_invalid_secret(self, client: AsyncClient, product_factory):
        product = await product_factory(id=1, price=Decimal("100"), quantity=10)
        payload = {
            "user": {
                "email": "customer@example.com",
                "first_name": "Customer",
                "last_name": "LastName",
                "phone": "+79991112233",
                "specialty": "Specialty"
            },
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ],
            "address": "Moscow, Red Square 1",
            "delivery": "CDEK",
            "tariff_code": 136,
            "delivery_point": "KSD295",
            "shipment_cost": 50
        }
        response = await client.post("/api/orders/webhooks/create", headers={"X-Webhook-Secret": "wrong_secret"}, json=payload)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_order_webhook_user_upsert(self, client: AsyncClient, product_factory, user_factory, test_session):
        product = await product_factory(id=1, price=Decimal("100"), quantity=10)
        # Pre-seed user with chat_id 12345
        user = await user_factory(
            telegram_chat_id=12345,
            email="test@example.com",
            first_name="Test",
            last_name="User"
        )
        # Pre-seed admin user
        admin = await user_factory(
            telegram_chat_id=54321,
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            is_superuser=True
        )

        payload = {
            "user": {
                "telegram_chat_id": 12345,
                "email": "new_email@example.com",
                "first_name": "UpdatedName",
                "last_name": "LastName",
                "phone": "+79991112233",
                "specialty": "Specialty"
            },
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ],
            "address": "Moscow, Red Square 1",
            "delivery": "CDEK",
            "tariff_code": 136,
            "delivery_point": "KSD295",
            "shipment_cost": 50
        }
        secret_token = settings.order.webhook_secret.get_secret_value()
        response = await client.post("/api/orders/webhooks/create", headers={"X-Webhook-Secret": secret_token}, json=payload)
        assert response.status_code == 201

        from src.auth.services import AuthService
        token = AuthService.create_token(email="admin@example.com", expires=3600)
        cookies = {settings.authentication.access_token.cookie_key: token}
        admin_response = await client.get("/api/auth/users/", cookies=cookies)
        assert admin_response.status_code == 200
        users = admin_response.json()
        target_user = next(u for u in users if u["telegram_chat_id"] == 12345)
        assert target_user["fullname"] == "LastName UpdatedName Testovish"
        assert target_user["email"] == "new_email@example.com"
