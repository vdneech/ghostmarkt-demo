from decimal import Decimal
from uuid import uuid4
from typing import TypeVar, Generic, Type, Any
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.shared.dependencies import get_db
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool

from src.orders.models import Delivery, Order
from src.orders.schemas import OrderItemCreate
from src.orders.schemas import OrderCreate
from src.products.schemas import ProductCreate
from src.shared.schemas import Dimensions
from src.products.models import Product
from src.auth.models import User
from src.auth.schemas import UserCreate
from src.cdek.schemas import Recipient, Item, Package, CDEKOrderCreate, Payment, Phone

from src.shared.database import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(
    scope="session", loop_scope="session"
)
async def setup_database():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def test_session(setup_database):
    async with setup_database.connect() as connection:
        transaction = await connection.begin()

        session = AsyncSession(bind=connection, expire_on_commit=False)

        yield session

        await session.close()
        await transaction.rollback()


@pytest_asyncio.fixture
async def client(test_session):

    async def _get_test_db():
        yield test_session

    app.dependency_overrides[get_db] = _get_test_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_factory(test_session):
    chat_id_counter = [10000000]
    async def _factory(user: UserCreate = None, **kwargs) -> User:
        chat_id_counter[0] += 1
        if not user:
            user = UserCreate(
                telegram_chat_id=chat_id_counter[0],
                username=f"test_test_{chat_id_counter[0]}",
                email=f"test_{chat_id_counter[0]}@gmail.com",
                first_name="Test",
                middle_name="Testovish",
                last_name="Testov",
                phone="+79384887988",
                specialty="QA",
            )
        data = user.model_dump(exclude_unset=True)
        data.update(kwargs)
        to_create = User(**data)
        test_session.add(to_create)
        await test_session.commit()
        return to_create
    return _factory


@pytest_asyncio.fixture
async def product_factory(test_session):
    async def _factory(product: ProductCreate = None, **kwargs) -> Product:
        if not product:
            product = ProductCreate(
                name="TestProduct",
                description="TestProduct",
                price=Decimal("12000.00"),
                quantity=100,
                weight=100,
                dimensions=Dimensions(
                    length=10,
                    width=10,
                    height=10,
                ),
                is_active=True,
            )
        data = product.model_dump(
            exclude_unset=True,
            exclude={"dimensions"},
        )
        data.update(kwargs)
        to_create = Product(
            **data,
            length=product.dimensions.length,
            width=product.dimensions.width,
            height=product.dimensions.height,
        )
        test_session.add(to_create)
        await test_session.commit()
        return to_create
    return _factory


# Не забудьте импортировать модель OrderItem, если она называется так
from src.orders.models import Order, OrderItem


@pytest_asyncio.fixture
async def order_factory(
    test_session, product_factory, user_factory, _model=Order
) -> "Order":
    prod = await product_factory()
    usr = await user_factory()

    item = OrderItemCreate(
        product_id=prod.id,
        quantity=1,
    )
    order = OrderCreate(
        address="Test st., b. 673",
        items=[item],
        delivery=Delivery.URBAN,
    )

    order_data = order.model_dump(exclude_unset=True)

    items_data = order_data.pop("items", [])

    db_items = [
        OrderItem(
            **item_dict,
            price_at_purchase=prod.price * prod.quantity,
        )
        for item_dict in items_data
    ]

    to_create = _model(
        **order_data,
        items=db_items,
        user=usr,
        total_amount=prod.price * prod.quantity,
    )

    test_session.add(to_create)
    await test_session.commit()

    return to_create


@pytest.fixture
def cdek_order_factory():
    """Фабрика для создания объекта CDEKOrderCreate."""

    def _create_order(
        number: str = f"GHOST-TEST-{uuid4().hex[:8].upper()}",
        tariff_code: int = 136,
        recipient_name: str = "Иван Иванов",
        recipient_phone: str = "+79991112233",
        shipment_point: str = "KSD231",
        delivery_point: str = "PET3",
        items: list[Item] = None,
    ) -> CDEKOrderCreate:
        if items is None:
            items = [
                Item(
                    name="Тестовый товар",
                    ware_key="test_item_1",
                    cost=Decimal("1000.00"),
                    payment=Payment(value=Decimal("1000.00")),
                    weight=500,
                    amount=1,
                )
            ]

        recipient = Recipient(
            name=recipient_name,
            phones=[Phone(number=recipient_phone)],
            email="test@example.com",
        )

        total_weight = sum(item.weight * item.amount for item in items)

        package = Package(
            number="1",
            weight=total_weight,
            length=10,
            width=10,
            height=10,
            items=items,
        )

        return CDEKOrderCreate(
            number=number,
            tariff_code=tariff_code,
            comment="Тестовый заказ",
            shipment_point=shipment_point,
            delivery_point=delivery_point,
            recipient=recipient,
            packages=[package],
        )

    return _create_order


T = TypeVar("T", bound=Base)


class BaseDAOTest(Generic[T]):
    model: Type[T]

    @classmethod
    async def _create_object(cls, test_session: AsyncSession, **kwargs: Any) -> T:
        """
        Универсальный фабричный метод.
        Принимает любые поля модели, создает запись в БД и возвращает объект типа T.
        """
        new_object = cls.model(**kwargs)
        test_session.add(new_object)
        await test_session.flush()
        return new_object


from unittest.mock import AsyncMock, patch

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

@pytest.fixture(autouse=True, scope="session")
def setup_cache():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")


@pytest.fixture(autouse=True)
def mock_celery():
    with patch("src.notifications.tasks.send_email_otp_notification_task.delay") as mock_email_otp, \
         patch("src.orders.tasks.cancel_expired_order_task.apply_async") as mock_cancel_order:
        yield (mock_email_otp, mock_cancel_order)


class FakeRedis:
    def __init__(self, *args, **kwargs):
        self.data = {}
    async def get(self, name):
        return self.data.get(name)
    async def set(self, name, value, *args, **kwargs):
        self.data[name] = value
        return True
    async def delete(self, *names):
        count = 0
        for name in names:
            if name in self.data:
                del self.data[name]
                count += 1
        return count
    async def ttl(self, name):
        return 60 if name in self.data else -2
    async def close(self):
        pass

@pytest.fixture(autouse=True)
def mock_redis():
    fake_redis = FakeRedis()
    with patch("src.shared.redis.get_redis_client", return_value=fake_redis), \
         patch("src.auth.dependencies.get_redis_client", return_value=fake_redis), \
         patch("redis.asyncio.Redis", return_value=fake_redis):
        yield


@pytest.fixture
def mock_ai_service():
    with patch("src.infrastructure.ai.services.AIService.text_to_text", new_callable=AsyncMock) as mock:
        mock.return_value = '{"name": "Translated Name", "description": "Translated Description", "metas": []}'
        yield mock


@pytest.fixture(autouse=True)
def mock_cdek_provider():
    with patch("src.cdek.providers.CDEKProvider.post", new_callable=AsyncMock) as mock_post, \
         patch("src.cdek.providers.CDEKProvider.get", new_callable=AsyncMock) as mock_get, \
         patch("src.cdek.providers.CDEKProvider.delete", new_callable=AsyncMock) as mock_delete:
        
        mock_post.return_value = {
            "entity": {"uuid": "f3a295e7-6e31-4e1e-84f8-ec4263f31446"},
            "requests": [{"type": "CREATE", "state": "ACCEPTED", "date_time": "2026-07-04T00:00:00+0000"}]
        }
        
        mock_get.return_value = {
            "entity": {
                "uuid": "f3a295e7-6e31-4e1e-84f8-ec4263f31446",
                "cdek_number": "10270717213",
                "tariff_code": 139,
                "recipient": {"name": "Иванов Иван", "phones": [{"number": "+79991112233"}]}
            },
            "requests": [{"type": "CREATE", "state": "ACCEPTED", "date_time": "2026-07-04T00:00:00+0000"}]
        }
        
        mock_delete.return_value = {
            "entity": {"uuid": "f3a295e7-6e31-4e1e-84f8-ec4263f31446"},
            "requests": [{"type": "DELETE", "state": "ACCEPTED", "date_time": "2026-07-04T00:00:00+0000"}]
        }
        yield (mock_post, mock_get, mock_delete)


@pytest.fixture(autouse=True)
def mock_smtp():
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_telegram_bot():
    with patch("aiogram.Bot.send_message", new_callable=AsyncMock) as mock_msg, \
         patch("aiogram.Bot.send_invoice", new_callable=AsyncMock) as mock_invoice:
        yield (mock_msg, mock_invoice)

