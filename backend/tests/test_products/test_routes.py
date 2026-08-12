import pytest
import decimal
from unittest.mock import AsyncMock
from httpx import AsyncClient

from src.config import settings
from src.auth.services import AuthService
from src.shared.services import MediaService


class TestProductRoutes:


    auth_service = AuthService

    def _get_auth_cookies(self, email: str) -> dict:
        token = self.auth_service.create_token(
            email=email,
            expires=3600,
        )
        return {settings.authentication.access_token.cookie_key: token}

    @pytest.mark.asyncio
    async def test_get_products_list_regular_vs_admin(self, client: AsyncClient, user_factory, product_factory):
        _regular_user = await user_factory(email="user@example.com", is_superuser=False)
        _admin_user = await user_factory(email="admin@example.com", is_superuser=True)

        p_active = await product_factory(name="Active Product", is_active=True)
        _p_inactive = await product_factory(name="Inactive Product", is_active=False)

        user_cookies = self._get_auth_cookies("user@example.com")
        res_user = await client.get("/api/products/", cookies=user_cookies)
        assert res_user.status_code == 200
        res_user_json = res_user.json()
        assert res_user_json["total"] == 1
        assert res_user_json["products"][0]["id"] == p_active.id

        from fastapi_cache import FastAPICache
        await FastAPICache.clear(namespace="products")

        admin_cookies = self._get_auth_cookies("admin@example.com")
        res_admin = await client.get("/api/products/", cookies=admin_cookies)
        assert res_admin.status_code == 200
        res_admin_json = res_admin.json()
        assert res_admin_json["total"] == 2

    @pytest.mark.asyncio
    async def test_get_product_detail(self, client: AsyncClient, product_factory):
        p = await product_factory(name="Detail Product", price=decimal.Decimal("9.99"))
        
        response = await client.get(f"/api/products/{p.id}/")
        assert response.status_code == 200
        assert response.json()["name"] == "Detail Product"

        response_404 = await client.get("/api/products/99999/")
        assert response_404.status_code == 404

    @pytest.mark.asyncio
    async def test_create_product_permissions(self, client: AsyncClient, user_factory):
        await user_factory(email="user@example.com", is_superuser=False)
        await user_factory(email="admin@example.com", is_superuser=True)

        payload = {
            "name": "New Product",
            "price": "99.99",
            "quantity": 10,
            "dimensions": {"length": 1, "width": 2, "height": 3},
            "description": "desc",
            "is_active": True,
            "weight": 100,
        }

        # 1. Anonymous -> 401 Unauthorized (since dependency calls get_current_superuser)
        res_anon = await client.post("/api/products/", json=payload)
        assert res_anon.status_code == 401

        # 2. Regular user -> 403 Forbidden
        user_cookies = self._get_auth_cookies("user@example.com")
        res_user = await client.post("/api/products/", json=payload, cookies=user_cookies)
        assert res_user.status_code == 403

        # 3. Superuser -> 201 (Success creation status code)
        admin_cookies = self._get_auth_cookies("admin@example.com")
        res_admin = await client.post("/api/products/", json=payload, cookies=admin_cookies)
        assert res_admin.status_code == 201
        assert res_admin.json()["name"] == "New Product"

    @pytest.mark.asyncio
    async def test_update_product_permissions(self, client: AsyncClient, user_factory, product_factory):
        await user_factory(email="user@example.com", is_superuser=False)
        await user_factory(email="admin@example.com", is_superuser=True)
        p = await product_factory(name="Old Name")

        payload = {"name": "Updated Name"}

        user_cookies = self._get_auth_cookies("user@example.com")
        res_user = await client.patch(f"/api/products/{p.id}/", json=payload, cookies=user_cookies)
        assert res_user.status_code == 403

        admin_cookies = self._get_auth_cookies("admin@example.com")
        res_admin = await client.patch(f"/api/products/{p.id}/", json=payload, cookies=admin_cookies)
        assert res_admin.status_code == 200
        assert res_admin.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_product_permissions(self, client: AsyncClient, user_factory, product_factory):
        await user_factory(email="user@example.com", is_superuser=False)
        await user_factory(email="admin@example.com", is_superuser=True)
        p = await product_factory()

        user_cookies = self._get_auth_cookies("user@example.com")
        res_user = await client.delete(f"/api/products/{p.id}/", cookies=user_cookies)
        assert res_user.status_code == 403

        admin_cookies = self._get_auth_cookies("admin@example.com")
        res_admin = await client.delete(f"/api/products/{p.id}/", cookies=admin_cookies)
        assert res_admin.status_code == 204

    @pytest.mark.asyncio
    async def test_translate_product_route(self, client: AsyncClient, user_factory, product_factory, mocker):
        await user_factory(email="admin@example.com", is_superuser=True)
        p = await product_factory(name="Книга", description="Интересная книга")
        
        # Mock AIService text_to_text directly
        mocker.patch(
            "src.infrastructure.ai.services.AIService.text_to_text",
            new_callable=AsyncMock,
            return_value='{"name": "Book", "description": "Interesting book"}'
        )
        
        admin_cookies = self._get_auth_cookies("admin@example.com")
        response = await client.post(f"/api/products/{p.id}/translate", cookies=admin_cookies)
        assert response.status_code == 200
        assert response.json()["name_en"] == "Book"
        assert response.json()["description_en"] == "Interesting book"

    @pytest.mark.asyncio
    async def test_image_upload_and_delete(self, client: AsyncClient, user_factory, product_factory, test_session, mocker):
        await user_factory(email="admin@example.com", is_superuser=True)
        p = await product_factory()

        mocker.patch.object(MediaService, "save", return_value="/media/fake_image.png")
        mocker.patch.object(MediaService, "delete", return_value=None)

        admin_cookies = self._get_auth_cookies("admin@example.com")
        
        files = {"file": ("test.png", b"fake file content", "image/png")}
        response = await client.post(
            f"/api/products/{p.id}/images",
            files=files,
            cookies=admin_cookies,
        )
        assert response.status_code == 201
        res_json = response.json()
        assert res_json["path"] == "/media/fake_image.png"
        img_id = res_json["id"]

        # 2. Delete image
        del_response = await client.delete(
            f"/api/products/{p.id}/images/{img_id}",
            cookies=admin_cookies,
        )
        assert del_response.status_code == 204
