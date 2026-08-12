import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from src.config import settings
from src.auth.models import User
from src.auth.services import AuthService


class TestAdminUserManagement:

    def _get_auth_cookies(self, email: str) -> dict:
        token = AuthService.create_token(
            email=email,
            expires=3600,
        )
        return {settings.authentication.access_token.cookie_key: token}

    @pytest.mark.asyncio
    async def test_list_users_by_admin(self, client: AsyncClient, user_factory, test_session):
        user = await user_factory(
            telegram_chat_id=12345,
            first_name="Test",
            last_name="User",
            phone="+79991234567",
            email="test@example.com",
        )
        admin = await user_factory(
            telegram_chat_id=54321,
            first_name="Admin",
            last_name="User",
            phone="+79997654321",
            email="admin@example.com",
            is_superuser=True,
        )

        cookies = self._get_auth_cookies("admin@example.com")
        response = await client.get("/api/auth/users/", cookies=cookies)
        assert response.status_code == 200
        users_list = response.json()
        assert len(users_list) == 2
        emails = [u["email"] for u in users_list]
        assert "test@example.com" in emails
        assert "admin@example.com" in emails

    @pytest.mark.asyncio
    async def test_get_user_detail_by_admin(self, client: AsyncClient, user_factory, test_session):
        user = await user_factory(
            telegram_chat_id=12345,
            first_name="Test",
            last_name="User",
            phone="+79991234567",
            email="test@example.com",
        )
        admin = await user_factory(
            telegram_chat_id=54321,
            first_name="Admin",
            last_name="User",
            phone="+79997654321",
            email="admin@example.com",
            is_superuser=True,
        )

        cookies = self._get_auth_cookies("admin@example.com")
        response = await client.get(f"/api/auth/users/{user.id}/", cookies=cookies)
        assert response.status_code == 200
        user_detail = response.json()
        assert user_detail["id"] == user.id
        assert user_detail["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_patch_user_by_admin(self, client: AsyncClient, user_factory, test_session):
        user = await user_factory(
            telegram_chat_id=12345,
            first_name="Test",
            last_name="User",
            phone="+79991234567",
            email="test@example.com",
        )
        admin = await user_factory(
            telegram_chat_id=54321,
            first_name="Admin",
            last_name="User",
            phone="+79997654321",
            email="admin@example.com",
            is_superuser=True,
        )

        cookies = self._get_auth_cookies("admin@example.com")
        data = {"first_name": "NewPatchName", "specialty": "NewSpecialty"}
        response = await client.patch(f"/api/auth/users/{user.id}/", json=data, cookies=cookies)
        assert response.status_code == 200
        res_json = response.json()
        assert "NewPatchName" in res_json["fullname"]
        assert res_json["specialty"] == "NewSpecialty"
        assert res_json["telegram_chat_id"] == 12345

    @pytest.mark.asyncio
    async def test_put_user_by_admin(self, client: AsyncClient, user_factory, test_session):
        user = await user_factory(
            telegram_chat_id=12345,
            first_name="Test",
            last_name="User",
            phone="+79991234567",
            email="test@example.com",
        )
        admin = await user_factory(
            telegram_chat_id=54321,
            first_name="Admin",
            last_name="User",
            phone="+79997654321",
            email="admin@example.com",
            is_superuser=True,
        )

        cookies = self._get_auth_cookies("admin@example.com")
        data = {
            "first_name": "NewPutName",
            "last_name": "NewPutLastName",
            "email": "putemail@example.com",
            "phone": "+79998887766",
            "specialty": "PutSpecialty",
            "is_superuser": True,
            "locale": "ru",
        }
        response = await client.put(f"/api/auth/users/{user.id}/", json=data, cookies=cookies)
        assert response.status_code == 200
        res_json = response.json()
        assert "NewPutName" in res_json["fullname"]
        assert res_json["email"] == "putemail@example.com"
        assert res_json["phone"] == "+79998887766"
        assert res_json["specialty"] == "PutSpecialty"
        assert res_json["is_superuser"] is True
        assert res_json["telegram_chat_id"] == 12345

    @pytest.mark.asyncio
    async def test_access_denied_for_non_admin(self, client: AsyncClient, user_factory, test_session):
        user = await user_factory(
            telegram_chat_id=12345,
            first_name="Test",
            last_name="User",
            phone="+79991234567",
            email="test@example.com",
        )

        cookies = self._get_auth_cookies("test@example.com")
        response = await client.get("/api/auth/users/", cookies=cookies)
        assert response.status_code == 403

        response = await client.patch(f"/api/auth/users/{user.id}/", json={"first_name": "Forbidden"}, cookies=cookies)
        assert response.status_code == 403

        response = await client.put(f"/api/auth/users/{user.id}/", json={"first_name": "Forbidden"}, cookies=cookies)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_access_denied_for_unauthorized(self, client: AsyncClient, user_factory, test_session):
        user = await user_factory(
            telegram_chat_id=12345,
            first_name="Test",
            last_name="User",
            phone="+79991234567",
            email="test@example.com",
        )
        response = await client.get("/api/auth/users/")
        assert response.status_code == 401


class TestAuthRoutes:

    @pytest.fixture(autouse=True)
    async def setup_redis(self):
        from src.shared.redis import get_redis_client
        self.redis = await get_redis_client()
        yield

    @pytest.mark.asyncio
    async def test_login_flow_otp_and_spam(self, client: AsyncClient, test_session):
        email = "spam_test@example.com"
        # Clear redis cache for email first
        await self.redis.delete(f"otp:{email}")

        # 1. First OTP request -> Success
        response = await client.post("/api/auth/login/", params={"email": email})
        assert response.status_code == 202

        # 2. Second OTP request immediately -> 429 Too Many Requests (Spam check)
        response_spam = await client.post("/api/auth/login/", params={"email": email})
        assert response_spam.status_code == 429
        assert "detail" in response_spam.json()

        # Retrieve code from Redis to proceed
        code = await self.redis.get(f"otp:{email}")
        assert code is not None

        # 3. Verify incorrect OTP code -> 401 Unauthorized
        response_verify_fail = await client.post("/api/auth/login/otp/", params={"email": email, "code": "000000"})
        assert response_verify_fail.status_code == 401

        # 4. Verify correct OTP code -> 200 OK & HttpOnly cookies set
        response_verify = await client.post("/api/auth/login/otp/", params={"email": email, "code": code})
        assert response_verify.status_code == 200
        
        # Check HTTP-only cookies
        cookies = response_verify.cookies
        assert settings.authentication.access_token.cookie_key in cookies
        assert settings.authentication.refresh_token.cookie_key in cookies

        set_cookie_headers = response_verify.headers.get_list("set-cookie")
        for cookie in set_cookie_headers:
            assert "HttpOnly" in cookie

    @pytest.mark.asyncio
    async def test_refresh_token(self, client: AsyncClient, user_factory):
        email = "refresh@example.com"
        user = await user_factory(email=email)

        # Generate refresh token
        refresh_token = AuthService.create_token(email, expires=3600, refresh=True)
        cookies = {settings.authentication.refresh_token.cookie_key: refresh_token}

        response = await client.post("/api/auth/refresh", cookies=cookies)
        assert response.status_code == 200
        assert settings.authentication.access_token.cookie_key in response.cookies

    @pytest.mark.asyncio
    async def test_refresh_token_invalid_or_missing(self, client: AsyncClient):
        # Missing token
        response = await client.post("/api/auth/refresh")
        assert response.status_code == 401

        # Invalid token
        cookies = {settings.authentication.refresh_token.cookie_key: "invalid_refresh"}
        response = await client.post("/api/auth/refresh", cookies=cookies)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_profile_me_get_and_patch(self, client: AsyncClient, user_factory):
        email = "me_profile@example.com"
        user = await user_factory(
            email=email,
            first_name="Me",
            last_name="User",
            phone="+79991112233",
            specialty="QA"
        )
        
        # Generate access token cookie
        token = AuthService.create_token(email, expires=3600, refresh=False)
        cookies = {settings.authentication.access_token.cookie_key: token}

        # 1. GET profile /me
        response = await client.get("/api/auth/me", cookies=cookies)
        assert response.status_code == 200
        assert response.json()["email"] == email

        # 2. PATCH profile /me
        update_data = {
            "first_name": "NewMe",
            "last_name": "NewUser",
            "phone": "+79998887766",
            "specialty": "Dev"
        }
        response = await client.patch("/api/auth/me", json=update_data, cookies=cookies)
        assert response.status_code == 200
        res_json = response.json()
        assert "NewMe" in res_json["fullname"]
        assert res_json["phone"] == "+79998887766"
        assert res_json["specialty"] == "Dev"

    @pytest.mark.asyncio
    async def test_logout(self, client: AsyncClient, user_factory):
        email = "logout@example.com"
        user = await user_factory(email=email)
        token = AuthService.create_token(email, expires=3600, refresh=False)
        cookies = {settings.authentication.access_token.cookie_key: token}

        response = await client.post("/api/auth/logout", cookies=cookies)
        assert response.status_code == 200
        
        # Check cookies deletion / expired max-age in set-cookie headers
        set_cookies = response.headers.get_list("set-cookie")
        assert len(set_cookies) > 0
        joined = "; ".join(set_cookies).lower()
        assert "max-age=0" in joined or "expires=" in joined or joined.count('access_token=""') > 0
