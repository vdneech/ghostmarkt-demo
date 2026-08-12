import pytest
import decimal
import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config import settings
from src.auth.services import AuthService
from src.products.models import PromoCode
from src.products.schemas import PromoCodeCreate
from src.orders.models import Order

class TestPromoCodes:
    auth_service = AuthService

    def _get_auth_cookies(self, email: str) -> dict:
        token = self.auth_service.create_token(
            email=email,
            expires=3600,
        )
        return {settings.authentication.access_token.cookie_key: token}

    def test_pydantic_validation(self):
        # Valid - discount only
        p1 = PromoCodeCreate(code="DISC100", discount=decimal.Decimal("100.00"))
        assert p1.discount == decimal.Decimal("100.00")
        assert p1.discount_percent is None

        # Valid - percent only
        p2 = PromoCodeCreate(code="PCT10", discount_percent=10)
        assert p2.discount_percent == 10
        assert p2.discount is None

        # Invalid - both set
        with pytest.raises(ValueError, match="must be provided, but not both"):
            PromoCodeCreate(code="BAD", discount=decimal.Decimal("100.00"), discount_percent=10)

        # Invalid - neither set
        with pytest.raises(ValueError, match="must be provided, but not both"):
            PromoCodeCreate(code="BAD")

        # Invalid - negative values
        with pytest.raises(ValueError, match="Discount must be greater than 0"):
            PromoCodeCreate(code="BAD", discount=decimal.Decimal("-5.00"))

        with pytest.raises(ValueError, match="Discount percent must be between 1 and 100"):
            PromoCodeCreate(code="BAD", discount_percent=105)

    @pytest.mark.asyncio
    async def test_promocode_admin_routes(self, client: AsyncClient, user_factory):
        regular_user = await user_factory(email="user@example.com", is_superuser=False)
        admin_user = await user_factory(email="admin@example.com", is_superuser=True)

        user_cookies = self._get_auth_cookies(regular_user.email)
        admin_cookies = self._get_auth_cookies(admin_user.email)

        # 1. POST /promocodes (Create)
        payload = {
            "code": "PROMO50",
            "discount": "50.00"
        }
        # Regular user forbidden
        res = await client.post("/api/promocodes/", json=payload, cookies=user_cookies)
        assert res.status_code == 403

        # Admin success
        res = await client.post("/api/promocodes/", json=payload, cookies=admin_cookies)
        assert res.status_code == 201
        promo_data = res.json()
        assert promo_data["code"] == "PROMO50"
        assert float(promo_data["discount"]) == 50.00

        # 2. GET /promocodes (List)
        # Regular user forbidden
        res = await client.get("/api/promocodes/", cookies=user_cookies)
        assert res.status_code == 403

        # Admin success
        res = await client.get("/api/promocodes/", cookies=admin_cookies)
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["code"] == "PROMO50"

        # 3. DELETE /promocodes/{id}/
        promo_id = promo_data["id"]
        # Regular user forbidden
        res = await client.delete(f"/api/promocodes/{promo_id}/", cookies=user_cookies)
        assert res.status_code == 403

        # Admin success
        res = await client.delete(f"/api/promocodes/{promo_id}/", cookies=admin_cookies)
        assert res.status_code == 204

        # List again -> empty
        res = await client.get("/api/promocodes/", cookies=admin_cookies)
        assert res.status_code == 200
        assert len(res.json()) == 0

    @pytest.mark.asyncio
    async def test_promocode_verification(self, client: AsyncClient, test_session: AsyncSession):
        # Create different promo codes directly in DB
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Valid absolute discount
        p1 = PromoCode(code="VALID_ABS", discount=decimal.Decimal("100.00"), usages_count=0)
        # Valid percentage discount
        p2 = PromoCode(code="VALID_PCT", discount_percent=15, usages_count=0)
        # Expired
        p3 = PromoCode(
            code="EXPIRED", 
            discount=decimal.Decimal("50.00"), 
            expires_at=now - datetime.timedelta(hours=1),
            usages_count=0
        )
        # Usages limit reached
        p4 = PromoCode(
            code="MAX_USED", 
            discount=decimal.Decimal("50.00"), 
            max_usages=3, 
            usages_count=3
        )
        
        test_session.add_all([p1, p2, p3, p4])
        await test_session.commit()

        # Test valid absolute discount
        res = await client.get("/api/promocodes/?code=VALID_ABS&sum=1000.00")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert float(data["discount_amount"]) == 100.00

        # Test valid percentage discount
        res = await client.get("/api/promocodes/?code=VALID_PCT&sum=1000.00")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert float(data["discount_amount"]) == 150.00

        # Test expired
        res = await client.get("/api/promocodes/?code=EXPIRED&sum=1000.00")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False
        assert "истек" in data["message"]

        # Test max usages reached
        res = await client.get("/api/promocodes/?code=MAX_USED&sum=1000.00")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False
        assert "использован" in data["message"]

        # Test sum less than discount
        res = await client.get("/api/promocodes/?code=VALID_ABS&sum=50.00")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False
        assert "меньше" in data["message"]

    @pytest.mark.asyncio
    async def test_order_creation_with_promocode(self, client: AsyncClient, test_session: AsyncSession, user_factory, product_factory):
        # Create a user
        user = await user_factory(email="buyer@example.com", is_superuser=False)
        user_cookies = self._get_auth_cookies(user.email)

        # Create a product
        prod = await product_factory(price=decimal.Decimal("1000.00"), quantity=5, is_active=True)

        # Create promo codes in DB
        p1 = PromoCode(code="SAVE200", discount=decimal.Decimal("200.00"), usages_count=0)
        p2 = PromoCode(code="EXPIRED", discount_percent=10, expires_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        test_session.add_all([p1, p2])
        await test_session.commit()

        # 1. Create order with VALID promo code
        order_payload = {
            "address": "Moscow",
            "items": [{"product_id": prod.id, "quantity": 1}],
            "delivery": "CDEK",
            "tariff_code": 136,
            "delivery_point": "MSK1",
            "promo_code": "SAVE200",
            "discount": "200.00",
            "shipment_cost": "300.00"
        }
        res = await client.post("/api/orders/", json=order_payload, cookies=user_cookies)
        assert res.status_code == 201
        data = res.json()
        # total_amount: 1000 (prod) - 200 (promo) + 300 (shipment) = 1100.00
        assert float(data["total_amount"]) == 1100.00
        assert data["promo_code"] == "SAVE200"
        assert float(data["discount"]) == 200.00

        # Verify usage count incremented in DB
        await test_session.refresh(p1)
        assert p1.usages_count == 1

        # 2. Create order with EXPIRED promo code -> fails
        order_payload2 = {
            "address": "Moscow",
            "items": [{"product_id": prod.id, "quantity": 1}],
            "delivery": "CDEK",
            "tariff_code": 136,
            "delivery_point": "MSK1",
            "shipment_cost": "300.00",
            "promo_code": "EXPIRED"
        }
        res2 = await client.post("/api/orders/", json=order_payload2, cookies=user_cookies)
        assert res2.status_code == 400
        assert "истек" in res2.json()["detail"]
