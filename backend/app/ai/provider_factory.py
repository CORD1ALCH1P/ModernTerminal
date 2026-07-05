from functools import lru_cache

from app.ai.base import AIProvider
from app.ai.ollama_provider import OllamaProvider
from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.ai.runtime_settings import get_runtime_settings
from app.config import get_settings


@lru_cache
def get_provider() -> AIProvider:
    settings = get_runtime_settings()
    if settings.provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=get_settings().ollama_request_timeout_s,
            max_response_tokens=get_settings().ai_max_response_tokens,
        )
    if settings.provider == "custom_api":
        return OpenAICompatibleProvider(
            base_url=settings.custom_api_base_url,
            model=settings.custom_api_model,
            api_key=settings.custom_api_key,
            timeout=get_settings().custom_api_request_timeout_s,
            max_response_tokens=get_settings().ai_max_response_tokens,
        )
    raise NotImplementedError(f"AI provider {settings.provider!r} is not supported yet")
