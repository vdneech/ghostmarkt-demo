from decimal import Decimal
import hashlib
from urllib.parse import urlparse, parse_qs
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import PlainTextResponse

from src.config import settings
from src.orders.models import PaymentStatus, Delivery, Order
from src.payments.services import PaymentService


class TestPaymentService:
    service = PaymentService()

    @pytest.mark.asyncio
    async def test_generate_payment_url_success(self):
        order_id = 1
        cost = Decimal("1000.00")
        shp_user_id = 1
        
        url = self.service.generate_payment_url(
            order_id=order_id,
            cost=cost,
            shp_user_id=shp_user_id,
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert parsed.netloc == "auth.robokassa.ru"
        assert params.get("MerchantLogin")[0] == settings.robokassa.merchant_login.get_secret_value()
        assert params.get("OutSum")[0] == "1000.00"
        
        inv_id = int(params.get("InvId")[0])
        assert inv_id == order_id
        
        expected_signature = self.service.calculate_signature(cost, inv_id, shp_user_id)
        assert params.get("SignatureValue")[0] == expected_signature
        
        assert int(params.get("shp_user_id")[0]) == shp_user_id
        assert params.get("shp_order_id") is None

    @pytest.mark.asyncio
    async def test_generate_payment_url_invalid_cost(self):
        with pytest.raises(ValueError, match="Сумма платежа должна быть больше 0."):
            self.service.generate_payment_url(
                order_id=1,
                cost=Decimal("-10.00"),
                shp_user_id=1,
            )
            
        with pytest.raises(ValueError, match="Сумма платежа должна быть больше 0."):
            self.service.generate_payment_url(
                order_id=1,
                cost=Decimal("0.00"),
                shp_user_id=1,
            )

    @pytest.mark.asyncio
    async def test_calculate_signature(self):
        cost = Decimal("1234.56")
        inv_id = 42
        shp_user_id = 9
        
        expected_str = "{}:{}:{}:{}:shp_user_id={}".format(
            settings.robokassa.merchant_login.get_secret_value(),
            "1234.56",
            inv_id,
            settings.robokassa.password_1.get_secret_value(),
            shp_user_id,
        )
        expected_hash = hashlib.md5(expected_str.encode("utf-8")).hexdigest()
        
        assert self.service.calculate_signature(cost, inv_id, shp_user_id) == expected_hash

    @pytest.mark.asyncio
    async def test_check_signatures_success(self):
        out_sum = "1234.56"
        inv_id = 42
        shp_user_id = 9
        
        signature_str = "{}:{}:{}:shp_user_id={}".format(
            out_sum, inv_id, settings.robokassa.password_2.get_secret_value(), shp_user_id
        )
        valid_signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()
        
        # Test exact match
        assert self.service.check_signatures(out_sum, inv_id, shp_user_id, valid_signature) is True
        
        # Test case insensitivity
        assert self.service.check_signatures(out_sum, inv_id, shp_user_id, valid_signature.upper()) is True

    @pytest.mark.asyncio
    async def test_check_signatures_failure(self):
        out_sum = "1234.56"
        inv_id = 42
        shp_user_id = 9
        invalid_signature = "invalid_hash"
        
        assert self.service.check_signatures(out_sum, inv_id, shp_user_id, invalid_signature) is False

    @pytest.mark.asyncio
    async def test_process_webhook_no_order_service(self):
        local_service = PaymentService() # By default order_service is None
        
        with pytest.raises(Exception, match="OrderService is not provided to PaymentService"):
            await local_service.process_webhook(
                out_sum="100", inv_id=1, shp_user_id=1, signature_value="sig"
            )

    @pytest.mark.asyncio
    async def test_process_webhook_already_paid(self):
        order_mock = MagicMock(spec=Order)
        order_mock.payment_status = PaymentStatus.PAID
        
        order_service_mock = AsyncMock()
        order_service_mock.get_by_id.return_value = order_mock
        
        local_service = PaymentService(order_service=order_service_mock)
        
        response = await local_service.process_webhook(
            out_sum="100", inv_id=1, shp_user_id=1, signature_value="sig"
        )
        
        assert isinstance(response, PlainTextResponse)
        assert response.body == b"OK1"

    @pytest.mark.asyncio
    async def test_process_webhook_invalid_signature(self):
        order_mock = MagicMock(spec=Order)
        order_mock.payment_status = PaymentStatus.PENDING
        
        order_service_mock = AsyncMock()
        order_service_mock.get_by_id.return_value = order_mock
        
        local_service = PaymentService(order_service=order_service_mock)
        local_service.check_signatures = MagicMock(return_value=False)
        
        with pytest.raises(ValueError, match="Неверная подпись платежа"):
            await local_service.process_webhook(
                out_sum="100", inv_id=1, shp_user_id=1, signature_value="invalid"
            )

    @pytest.mark.asyncio
    async def test_process_webhook_success_no_cdek(self):
        inv_id = 1
        
        order_mock = MagicMock(spec=Order)
        order_mock.payment_status = PaymentStatus.PENDING
        order_mock.delivery = Delivery.URBAN
        order_mock.total_amount = Decimal("100")
        
        order_service_mock = AsyncMock()
        order_service_mock.get_by_id.return_value = order_mock
        order_service_mock.update_order.return_value = order_mock
        
        local_service = PaymentService(order_service=order_service_mock, cdek_service=None)
        local_service.check_signatures = MagicMock(return_value=True)
        
        response = await local_service.process_webhook(
            out_sum="100", inv_id=inv_id, shp_user_id=1, signature_value="valid"
        )
        
        assert isinstance(response, PlainTextResponse)
        assert response.body == b"OK1"
        assert response.status_code == 200
        order_service_mock.update_order.assert_called_once()
        order_service_mock.process_success_payment.assert_called_once()
