import pytest
from unittest.mock import AsyncMock, MagicMock
from src.infrastructure.ai.services import AIService
from src.config import settings


class TestAIService:

    @pytest.mark.asyncio
    async def test_text_to_text_success(self, mocker):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Hello from mock AI!"
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response)

        service = AIService()
        
        system_prompt = "You are a helper."
        user_prompt = "Hello!"
        
        result = await service.text_to_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False
        )

        assert result == "Hello from mock AI!"
        
        mock_post.assert_called_once()
        called_url, called_kwargs = mock_post.call_args
        
        assert called_url[0] == "https://api.alltokens.ru/api/v1/chat/completions"
        assert called_kwargs["headers"]["Authorization"] == f"Bearer {settings.alltokens.api_key.get_secret_value()}"
        assert called_kwargs["headers"]["Content-Type"] == "application/json"
        
        payload = called_kwargs["json"]
        assert payload["model"] == settings.alltokens.model
        assert payload["messages"] == [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        assert "response_format" not in payload

    @pytest.mark.asyncio
    async def test_text_to_text_json_mode(self, mocker):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"status": "ok"}'
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response)

        service = AIService()
        result = await service.text_to_text(
            system_prompt="System",
            user_prompt="User",
            json_mode=True
        )

        assert result == '{"status": "ok"}'
        
        mock_post.assert_called_once()
        _, called_kwargs = mock_post.call_args
        payload = called_kwargs["json"]
        assert payload["response_format"] == {"type": "json_object"}
