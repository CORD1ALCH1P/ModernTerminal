from __future__ import annotations

from dataclasses import dataclass, replace

from app.config import get_settings


@dataclass
class AIRuntimeSettings:
    """AI provider config the user can change at runtime from the UI, without
    restarting the app. Starts from the env-var defaults in app.config, but
    lives only in memory -- a restart reverts to those defaults, same as chat
    history and terminal scrollback not surviving a restart either."""

    provider: str
    ollama_base_url: str
    ollama_model: str
    custom_api_base_url: str
    custom_api_key: str
    custom_api_model: str


_current: AIRuntimeSettings | None = None


def get_runtime_settings() -> AIRuntimeSettings:
    global _current
    if _current is None:
        settings = get_settings()
        _current = AIRuntimeSettings(
            provider=settings.ai_provider,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            custom_api_base_url=settings.custom_api_base_url,
            custom_api_key=settings.custom_api_key,
            custom_api_model=settings.custom_api_model,
        )
    return _current


def update_runtime_settings(**changes: str) -> AIRuntimeSettings:
    global _current
    current = get_runtime_settings()
    _current = replace(current, **changes)
    return _current
