import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import BaseDAOTest
from src.auth.models import User
from src.auth.dao import UsersDAO


class TestUsersDAO(BaseDAOTest[User]):
    model = User

    @pytest.mark.asyncio
    async def test_find_one_or_none_by_telegram_chat_id(self, test_session: AsyncSession):
        user = await self._create_object(test_session, telegram_chat_id=1000000)
        await test_session.commit()
        users_dao = UsersDAO(test_session)
        user_from_db = await users_dao.find_one_or_none_by_telegram_chat_id(chat_id=user.telegram_chat_id)

        assert user_from_db is not None

    @pytest.mark.asyncio
    async def test_get_admins(self, test_session: AsyncSession):
        admin = await self._create_object(test_session, is_superuser=True)
        user = await self._create_object(test_session, is_superuser=False)
        await test_session.commit()

        users_dao = UsersDAO(test_session)
        admin_list = await users_dao.get_admins(sync=True)

        assert user not in admin_list
        assert admin in admin_list

    @pytest.mark.asyncio
    async def test_check_full_registration_by_chat_id(self, test_session: AsyncSession):
        user_1 = await self._create_object(
            test_session=test_session,
            first_name="Test",
            last_name="Test",
            specialty="QA",
            source="Test",
            phone="+100000000",
            email="test@example.com",
            telegram_chat_id=1090929039
        )

        user_2 = await self._create_object(
            test_session=test_session,
            first_name="Test",
            telegram_chat_id=1090929040
        )

        users_dao = UsersDAO(test_session)
        user_1_full_registration = await users_dao.check_full_registration_by_chat_id(user_1.telegram_chat_id)
        user_2_full_registration = await users_dao.check_full_registration_by_chat_id(user_2.telegram_chat_id)
        assert user_1_full_registration is True
        assert user_2_full_registration is False
