from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from src.cdek.schemas import RequestState
from src.cdek.services import CDEKService
from src.cdek.providers import CDEKProvider
from src.cdek.exceptions import CDEKDataError, CDEKApiError, CDEKRequestError


class TestCDEK:

    @pytest.fixture(autouse=True)
    async def setup_service(self):
        self._redis = Redis(db=10)
        self.service = CDEKService(self._redis)
        self.provider = CDEKProvider
        yield
        await self._redis.close()

    @pytest.mark.asyncio
    async def test_register_order_success(self, cdek_order_factory):
        try:
            order = await self.service.register_order(
                data=cdek_order_factory(
                    number="CUSTOM-123",
                    delivery_point="MSK123",
                )
            )
            assert order.requests[-1].errors is None
            assert order.requests[-1].state == RequestState.ACCEPTED
        except CDEKRequestError as e:
            pytest.skip(f"CDEK Sandbox API is unreachable: {e}")

    @pytest.mark.asyncio
    async def test_register_order_failure(self, cdek_order_factory, mocker):
        order = cdek_order_factory(
            number="CUSTOM-123",
            tariff_code=2193919283,
        )
        
        mocker.patch.object(self.provider, "post", return_value={
            "entity": {"uuid": "f3a295e7-6e31-4e1e-84f8-ec4263f31446"},
            "requests": [{
                "type": "CREATE",
                "state": "INVALID",
                "date_time": "2026-07-04T00:00:00+0000",
                "errors": [{"code": "ERR_CODE", "message": "Invalid tariff code"}]
            }]
        })

        try:
            with pytest.raises(CDEKDataError) as exc:
                await self.service.register_order(data=order)
            assert exc
        except CDEKRequestError as e:
            pytest.skip(f"CDEK Sandbox API is unreachable: {e}")

    @pytest.mark.asyncio
    async def test_get_info_about_order_by_uuid_success(self, cdek_order_factory):
        try:
            order = await self.service.register_order(
                data=cdek_order_factory(
                    number="CUSTOM-123",
                    delivery_point="MSK123",
                )
            )

            info = await self.service.get_info_about_order_by_uuid(
                order.entity.uuid,
            )
            assert info
        except CDEKRequestError as e:
            pytest.skip(f"CDEK Sandbox API is unreachable: {e}")

    @pytest.mark.asyncio
    async def test_get_info_about_order_success(self):
        cdek_number = "10270717213"

        try:
            info = await self.service.get_info_about_order(
                cdek_number=cdek_number,
            )
            assert info
            assert info.entity.tariff_code == 139
            assert info.entity.recipient.name == "Иванов Иван"
        except CDEKRequestError as e:
            pytest.skip(f"CDEK Sandbox API is unreachable: {e}")

    @pytest.mark.asyncio
    async def test_get_info_about_order_failure(self, mocker):
        cdek_number = "102707172fsdf13"
        
        mocker.patch.object(self.provider, "get", side_effect=CDEKDataError("Not found"))

        try:
            with pytest.raises((CDEKDataError, CDEKRequestError)) as exc:
                await self.service.get_info_about_order(
                    cdek_number=cdek_number,
                )
            assert exc
        except CDEKRequestError as e:
            pytest.skip(f"CDEK Sandbox API is unreachable: {e}")

    @pytest.mark.asyncio
    async def test_delete_order(self, mocker):
        mock_data = {
            "entity": {"uuid": "f3a295e7-6e31-4e1e-84f8-ec4263f31446"},
            "requests": [{"type": "DELETE", "state": "ACCEPTED", "date_time": "2026-07-04T00:00:00+0000"}]
        }

        mocker.patch.object(self.service.provider, 'delete', return_value=mock_data)

        result = await self.service.delete_order("f3a295e7-6e31-4e1e-84f8-ec4263f31446")
        assert result.requests[-1].state == RequestState.ACCEPTED

    @pytest.mark.asyncio
    async def test_delete_order_api_error(self, mocker):
        mock_delete = mocker.patch.object(self.service.provider, 'delete', new_callable=AsyncMock)

        mock_delete.side_effect = CDEKApiError(status_code=404, detail={"error": "not found"})

        with pytest.raises(CDEKDataError):
            await self.service.delete_order("some-uuid")
