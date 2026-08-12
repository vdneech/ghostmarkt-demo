import httpx

from src.shared.services import Service
from src.config import settings

class AIService(Service):
    """Универсальный сервис для работы с LLM-провайдером Alltokens"""

    def __init__(self, base_url: str = "https://api.alltokens.ru/api/v1"):
        self.api_key = settings.alltokens.api_key.get_secret_value()
        self.base_url = base_url


    async def text_to_text(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = settings.alltokens.model,
        json_mode: bool = False,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "modalities": ["text"],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]