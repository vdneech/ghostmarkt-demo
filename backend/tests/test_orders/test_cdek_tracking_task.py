import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from uuid import uuid4

from src.orders.models import Order, Delivery
from src.cdek.schemas import CDEKOrderResponse, CDEKEntity, RequestDTO, RequestState
from src.orders.tasks import (
    CdekNumberNotFoundError,
    fetch_cdek_tracking_code,
    fetch_cdek_tracking_code_task,
)
from src.payments.services import PaymentService
from src.orders.services import OrderService


@pytest.mark.asyncio
async def test_fetch_cdek_tracking_code_success(test_session, order_factory):
    """Test successful retrieval of CDEK tracking number."""
    order = order_factory
    order.delivery = Delivery.CDEK
    order.delivery_id = uuid4()
    order.delivery_code = None
    await test_session.commit()

    mock_response = CDEKOrderResponse(
        entity=CDEKEntity(
            uuid=order.delivery_id,
            cdek_number="12345678",
        ),
        requests=[
            RequestDTO(
                type="CREATE",
                date_time="2026-07-04T00:00:00+0000",
                state=RequestState.ACCEPTED,
            )
        ],
    )

    @asynccontextmanager
    async def mock_celery_session():
        yield test_session

    with patch("src.orders.tasks.celery_session_maker", mock_celery_session):
        with patch("src.cdek.services.CDEKService.get_info_about_order_by_uuid", new_callable=AsyncMock) as mock_get_info:
            mock_get_info.return_value = mock_response

            await fetch_cdek_tracking_code(order.id)

            await test_session.refresh(order)
            assert order.delivery_code == "12345678"
            mock_get_info.assert_called_once_with(order.delivery_id)


@pytest.mark.asyncio
async def test_fetch_cdek_tracking_code_not_assigned_yet(test_session, order_factory):
    """Test that task raises CdekNumberNotFoundError if tracking code is missing."""
    order = order_factory
    order.delivery = Delivery.CDEK
    order.delivery_id = uuid4()
    order.delivery_code = None
    await test_session.commit()

    mock_response = CDEKOrderResponse(
        entity=CDEKEntity(
            uuid=order.delivery_id,
            cdek_number=None,
        ),
        requests=[
            RequestDTO(
                type="CREATE",
                date_time="2026-07-04T00:00:00+0000",
                state=RequestState.ACCEPTED,
            )
        ],
    )

    @asynccontextmanager
    async def mock_celery_session():
        yield test_session

    with patch("src.orders.tasks.celery_session_maker", mock_celery_session):
        with patch("src.cdek.services.CDEKService.get_info_about_order_by_uuid", new_callable=AsyncMock) as mock_get_info:
            mock_get_info.return_value = mock_response

            with pytest.raises(CdekNumberNotFoundError):
                await fetch_cdek_tracking_code(order.id)


def test_fetch_cdek_tracking_code_task_retry():
    """Test that the Celery task calls retry on exception."""
    with patch.object(fetch_cdek_tracking_code_task, "retry") as mock_retry:
        mock_retry.side_effect = Exception("Retry called")

        with patch("src.orders.tasks.asyncio.run") as mock_run:
            mock_run.side_effect = CdekNumberNotFoundError("Tracking number not assigned yet")

            with pytest.raises(Exception, match="Retry called"):
                fetch_cdek_tracking_code_task.run(999)

            mock_retry.assert_called_once()


@pytest.mark.asyncio
async def test_payment_webhook_schedules_celery_task(test_session, order_factory):
    """Test that PaymentService schedules the Celery task when cdek_number is missing."""
    order = order_factory
    order.delivery = Delivery.CDEK
    order.delivery_id = None
    order.delivery_code = None
    order.total_amount = 100
    await test_session.commit()

    mock_cdek_response = CDEKOrderResponse(
        entity=CDEKEntity(
            uuid=uuid4(),
            cdek_number=None,
        ),
        requests=[
            RequestDTO(
                type="CREATE",
                date_time="2026-07-04T00:00:00+0000",
                state=RequestState.ACCEPTED,
            )
        ],
    )

    order_service = OrderService(test_session)
    cdek_service_mock = AsyncMock()
    cdek_service_mock.register_order.return_value = mock_cdek_response

    payment_service = PaymentService(order_service=order_service, cdek_service=cdek_service_mock)
    payment_service.check_signatures = MagicMock(return_value=True)

    with patch("src.orders.tasks.fetch_cdek_tracking_code_task.apply_async") as mock_apply_async:
        response = await payment_service.process_webhook(
            out_sum="100",
            inv_id=order.id,
            shp_user_id=order.user_id,
            signature_value="valid",
        )

        assert response.status_code == 200
        mock_apply_async.assert_called_once_with(
            args=[order.id],
            countdown=180,
        )
