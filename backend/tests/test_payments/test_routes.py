import hashlib

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.orders.models import PaymentStatus, Order


class TestRoutes:
    password_1 = settings.robokassa.password_1.get_secret_value()
    password_2 = settings.robokassa.password_2.get_secret_value()

    @pytest.mark.asyncio
    async def test_robokassa_webhook_success_payment(
        self, client: AsyncClient, order_factory: Order, test_session: AsyncSession
    ):
        data = {
            "OutSum": str(order_factory.total_amount),
            "InvId": str(order_factory.id),
            "shp_user_id": str(order_factory.user_id),
        }
        signature_str = "{}:{}:{}:shp_user_id={}".format(
            data.get("OutSum"),
            data.get("InvId"),
            self.password_2,
            data.get("shp_user_id"),
        )
        signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

        data["SignatureValue"] = signature

        response = await client.post("/api/webhooks/robokassa/result", data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.text == f"OK{order_factory.id}"
        
        await test_session.refresh(order_factory)
        assert order_factory.payment_status == PaymentStatus.PAID

    @pytest.mark.asyncio
    async def test_robokassa_webhook_already_paid(
        self, client: AsyncClient, order_factory: Order, test_session: AsyncSession
    ):
        order_factory.payment_status = PaymentStatus.PAID
        await test_session.commit()

        data = {
            "OutSum": str(order_factory.total_amount),
            "InvId": str(order_factory.id),
            "shp_user_id": str(order_factory.user_id),
        }
        signature_str = "{}:{}:{}:shp_user_id={}".format(
            data.get("OutSum"),
            data.get("InvId"),
            self.password_2,
            data.get("shp_user_id"),
        )
        signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

        data["SignatureValue"] = signature

        response = await client.post("/api/webhooks/robokassa/result", data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.text == f"OK{order_factory.id}"
        
        await test_session.refresh(order_factory)
        assert order_factory.payment_status == PaymentStatus.PAID

    @pytest.mark.asyncio
    async def test_robokassa_webhook_order_not_found(self, client: AsyncClient):
        data = {
            "OutSum": "12000.00",
            "InvId": "99999",
            "shp_user_id": "1",
        }

        signature_str = "{}:{}:{}:shp_user_id={}".format(
            data.get("OutSum"),
            data.get("InvId"),
            self.password_2,
            data.get("shp_user_id"),
        )
        signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

        data["SignatureValue"] = signature

        response = await client.post("/api/webhooks/robokassa/result", data=data)
        
        assert response.status_code == 500
        assert response.json()["detail"] == "Ошибка обработки платежа"

    @pytest.mark.asyncio
    async def test_robokassa_webhook_get_success_payment(
        self, client: AsyncClient, order_factory: Order
    ):
        data = {
            "OutSum": str(order_factory.total_amount),
            "InvId": str(order_factory.id),
            "shp_user_id": str(order_factory.user_id),
        }
        signature_str = "{}:{}:{}:shp_user_id={}".format(
            data.get("OutSum"),
            data.get("InvId"),
            self.password_2,
            data.get("shp_user_id"),
        )
        signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

        data["SignatureValue"] = signature

        # Отправляем GET-запрос вместо POST - должен вернуть 405 Method Not Allowed
        response = await client.get("/api/webhooks/robokassa/result", params=data)
        assert response.status_code == 405
