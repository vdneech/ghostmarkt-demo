import pytest
import jwt
from decimal import Decimal
from datetime import datetime, timezone
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.services import UserService, OTPService, AuthService
from src.auth.schemas import UserCreate, UserUpdate, AdminUserUpdate, AdminUserReplace
from src.auth.exceptions import UserNotFoundError, InvalidPhoneNumber, OTPCodeAlreadySent, FullnameValidationError
from src.config import settings


class TestUserService:

    @pytest.mark.asyncio
    async def test_create_and_format_phone(self, test_session):
        service = UserService(test_session)
        
        # Test RU phone formatting
        data_ru = UserCreate(
            email="ru_user@example.com",
            first_name="Ivan",
            last_name="Ivanov",
            phone="+79991112233",
            specialty="QA"
        )
        user_ru = await service.create(data_ru, raw=True)
        assert user_ru.phone == "+79991112233"
        
        # Test US phone formatting
        data_us = UserCreate(
            email="us_user@example.com",
            first_name="John",
            last_name="Doe",
            phone="+12025550143",
            specialty="Developer"
        )
        user_us = await service.create(data_us, raw=True)
        assert user_us.phone == "+12025550143"

    @pytest.mark.asyncio
    async def test_create_invalid_phone(self, test_session):
        service = UserService(test_session)
        data = UserCreate(
            email="invalid_phone@example.com",
            first_name="Test",
            last_name="Test",
            phone="+1234567890",  # invalid phone number format
            specialty="QA"
        )
        with pytest.raises(InvalidPhoneNumber):
            await service.create(data)

    @pytest.mark.asyncio
    async def test_get_by_id(self, test_session, user_factory):
        user = await user_factory()
        service = UserService(test_session)
        
        resp = await service.get_by_id(user.id)
        assert resp.id == user.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, test_session):
        service = UserService(test_session)
        with pytest.raises(UserNotFoundError):
            await service.get_by_id(99999)

    @pytest.mark.asyncio
    async def test_update_profile(self, test_session, user_factory):
        user = await user_factory(first_name="OldName", phone="+79991112233")
        service = UserService(test_session)
        
        update_data = UserUpdate(
            first_name="NewName",
            last_name="NewLastName",
            phone="+79998887766",
            specialty="Manager"
        )
        resp = await service.update(user.id, update_data)
        assert resp.fullname == "NewLastName NewName Testovish"
        assert resp.phone == "+79998887766"

    @pytest.mark.asyncio
    async def test_admin_update_user(self, test_session, user_factory):
        user = await user_factory()
        service = UserService(test_session)
        
        # Admin PATCH update
        patch_data = AdminUserUpdate(
            first_name="AdminPatched",
            is_superuser=True
        )
        resp = await service.admin_update_user(user.id, patch_data)
        assert "AdminPatched" in resp.fullname
        assert resp.is_superuser is True

        # Admin PUT replace
        put_data = AdminUserReplace(
            first_name="AdminReplaced",
            last_name="Replacement",
            email="replaced@example.com",
            phone="+79991112233",
            specialty="Director",
            is_superuser=True
        )
        resp = await service.admin_update_user(user.id, put_data)
        assert resp.fullname == "AdminReplaced Replacement"
        assert resp.email == "replaced@example.com"

    @pytest.mark.asyncio
    async def test_upsert_user_by_identifiers(self, test_session, user_factory):
        service = UserService(test_session)
        
        # 1. Create new user
        data1 = UserCreate(
            email="upsert@example.com",
            first_name="Upserted",
            last_name="One",
            phone="+79991112233",
            specialty="QA",
            telegram_chat_id=12345
        )
        user1 = await service.upsert_user_by_identifiers(data1)
        assert user1.id is not None
        assert user1.telegram_chat_id == 12345

        # 2. Update existing user by telegram_chat_id
        data2 = UserCreate(
            email="new_upsert@example.com",
            first_name="UpdatedUpsert",
            last_name="Two",
            phone="+79998887766",
            specialty="Dev",
            telegram_chat_id=12345
        )
        user2 = await service.upsert_user_by_identifiers(data2)
        assert user2.id == user1.id
        assert user2.first_name == "UpdatedUpsert"
        assert user2.email == "new_upsert@example.com"

    @pytest.mark.asyncio
    async def test_validate_and_split_fullname(self):
        # Successful parse
        last, first, middle = UserService.validate_and_split_fullname("Иванов Иван Иванович")
        assert last == "Иванов"
        assert first == "Иван"
        assert middle == "Иванович"

        # Missing last name / too short
        with pytest.raises(FullnameValidationError):
            UserService.validate_and_split_fullname("Иванов")

    @pytest.mark.asyncio
    async def test_finalize_user_profile(self, test_session, user_factory):
        user = await user_factory(telegram_chat_id=7777)
        service = UserService(test_session)
        
        profile_data = {
            "fullname": "Петров Петр",
            "specialty": "Designer",
            "phone": "+79992223344",
            "email": "petrov@example.com",
            "source": "Telegram"
        }
        updated = await service.finalize_user_profile(7777, profile_data)
        assert updated.last_name == "Петров"
        assert updated.first_name == "Петр"
        assert updated.specialty == "Designer"
        assert updated.phone == "+79992223344"
        assert updated.email == "petrov@example.com"


class TestOTPService:

    @pytest.fixture(autouse=True)
    async def setup_redis(self):
        self.redis = Redis(db=10, decode_responses=True)
        self.service = OTPService(self.redis)
        yield
        await self.redis.close()

    @pytest.mark.asyncio
    async def test_otp_flow_and_spam(self):
        email = "otp_test@example.com"
        
        # Clean Redis key if left over
        await self.redis.delete(self.service._key.format(email))

        # 1. Generate and save OTP
        code = await self.service.generate_and_save(email)
        assert len(code) == 6
        assert code.isdigit()

        # 2. Try to spam/generate again immediately -> raises OTPCodeAlreadySent
        with pytest.raises(OTPCodeAlreadySent):
            await self.service.generate_and_save(email)

        # 3. Verify incorrect code -> returns False, code remains in Redis
        verify_fail = await self.service.verify(email, "000000")
        assert verify_fail is False
        assert await self.redis.get(self.service._key.format(email)) is not None

        # 4. Verify correct code -> returns True, code is deleted from Redis
        verify_success = await self.service.verify(email, code)
        assert verify_success is True
        assert await self.redis.get(self.service._key.format(email)) is None

    @pytest.mark.asyncio
    async def test_otp_verify_limit(self):
        email = "otp_limit_test@example.com"
        await self.redis.delete(self.service._key.format(email))
        await self.redis.delete(f"otp_attempts:{email}")

        # 1. Generate OTP
        code = await self.service.generate_and_save(email)

        # 2. Verify with wrong code 5 times
        for _ in range(5):
            res = await self.service.verify(email, "000000")
            assert res is False
            # Code should still exist in Redis during first 5 attempts
            assert await self.redis.get(self.service._key.format(email)) is not None

        # 3. 6th attempt should block the OTP and delete it from Redis
        res_blocked = await self.service.verify(email, "000000")
        assert res_blocked is False
        assert await self.redis.get(self.service._key.format(email)) is None


class TestAuthService:

    @pytest.fixture(autouse=True)
    async def setup_redis(self, test_session):
        self.redis = Redis(db=10, decode_responses=True)
        self.service = AuthService(test_session, self.redis)
        yield
        await self.redis.close()

    @pytest.mark.asyncio
    async def test_request_otp(self):
        email = "auth_otp@example.com"
        await self.redis.delete(self.service._otp_key.format(email))

        code = await self.service.request_otp(email)
        assert len(code) == 6
        assert await self.redis.get(self.service._otp_key.format(email)) is not None
        await self.redis.delete(self.service._otp_key.format(email))

    def test_token_creation_and_validation(self):
        email = "jwt_test@example.com"
        
        # Create access token
        access_token = AuthService.create_token(email, expires=3600, refresh=False)
        decoded_email = AuthService.decode_and_verify(access_token, refresh=False)
        assert decoded_email == email

        # Create refresh token
        refresh_token = AuthService.create_token(email, expires=3600, refresh=True)
        decoded_refresh_email = AuthService.decode_and_verify(refresh_token, refresh=True)
        assert decoded_refresh_email == email

        # Test invalid token structure
        with pytest.raises(Exception, match="Invalid token"):
            AuthService.decode_and_verify("invalid.token.here")

        # Test token expiration (expires in -10 seconds)
        expired_token = AuthService.create_token(email, expires=-10, refresh=False)
        with pytest.raises(Exception, match="Token expired"):
            AuthService.decode_and_verify(expired_token)
