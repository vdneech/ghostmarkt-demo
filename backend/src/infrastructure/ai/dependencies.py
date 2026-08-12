from src.infrastructure.ai.services import AIService

def get_ai_service() -> AIService:
    """
    Зависимость для получения экземпляра AIService.
    """
    return AIService()
