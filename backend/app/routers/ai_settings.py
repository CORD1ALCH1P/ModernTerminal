from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.ai.base import ProviderUnavailable
from app.ai.ollama_provider import OllamaProvider
from app.ai.provider_factory import get_provider
from app.ai.runtime_settings import get_runtime_settings, update_runtime_settings

router = APIRouter(prefix="/api/ai", tags=["ai-settings"])


class AISettingsOut(BaseModel):
    provider: str
    ollama_base_url: str
    ollama_model: str
    custom_api_base_url: str
    custom_api_model: str
    # The key itself is never returned once saved -- same convention as host
    # secrets elsewhere in this app -- just whether one is currently set.
    has_custom_api_key: bool


class AISettingsUpdate(BaseModel):
    provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    custom_api_base_url: str | None = None
    custom_api_model: str | None = None
    # Omit (or send null) to leave an already-saved key unchanged; send "" to
    # explicitly clear it.
    custom_api_key: str | None = None


def _to_out(settings) -> AISettingsOut:
    return AISettingsOut(
        provider=settings.provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        custom_api_base_url=settings.custom_api_base_url,
        custom_api_model=settings.custom_api_model,
        has_custom_api_key=bool(settings.custom_api_key),
    )


@router.get("/settings", response_model=AISettingsOut)
async def get_ai_settings() -> AISettingsOut:
    return _to_out(get_runtime_settings())


@router.put("/settings", response_model=AISettingsOut)
async def update_ai_settings(payload: AISettingsUpdate) -> AISettingsOut:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    updated = update_runtime_settings(**changes)
    get_provider.cache_clear()  # next call rebuilds the provider with the new settings
    return _to_out(updated)


@router.get("/models")
async def list_ollama_models(base_url: str | None = None) -> dict:
    """Lists models available on an Ollama server -- defaults to the
    currently configured base_url, but accepts an override so the settings UI
    can validate a URL the user is typing before saving it. Ollama-specific:
    there's no equivalent generic listing endpoint across arbitrary
    OpenAI-compatible servers, so the custom-API provider has no "fetch
    models" button and just takes a free-text model name."""
    target_url = base_url or get_runtime_settings().ollama_base_url
    probe = OllamaProvider(target_url, model="")  # model unused by list_models()
    try:
        models = await probe.list_models()
    except ProviderUnavailable as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not reach Ollama at {target_url}: {exc}"
        ) from exc
    return {"models": models}
