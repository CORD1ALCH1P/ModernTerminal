import pytest

from app.tests.fake_ollama_server import start_fake_ollama_server


@pytest.fixture(autouse=True)
def _reset_runtime_ai_settings():
    """runtime_settings/_current and get_provider are module-level singletons
    shared across the whole test session -- reset them before and after each
    test so changes made by one test (e.g. PUT /api/ai/settings) can't leak
    into another."""
    import app.ai.runtime_settings as runtime_settings
    from app.ai.provider_factory import get_provider

    runtime_settings._current = None
    get_provider.cache_clear()
    yield
    runtime_settings._current = None
    get_provider.cache_clear()


async def test_get_default_settings(client):
    resp = await client.get("/api/ai/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "ollama"
    assert body["ollama_base_url"]
    assert body["ollama_model"]


async def test_update_settings_persists_for_subsequent_reads(client):
    resp = await client.put(
        "/api/ai/settings", json={"ollama_base_url": "http://example.invalid:11434", "ollama_model": "llama3.1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "provider": "ollama",
        "ollama_base_url": "http://example.invalid:11434",
        "ollama_model": "llama3.1",
        "custom_api_base_url": "",
        "custom_api_model": "",
        "has_custom_api_key": False,
    }

    resp = await client.get("/api/ai/settings")
    assert resp.json()["ollama_model"] == "llama3.1"


async def test_update_settings_rebuilds_the_provider(client):
    from app.ai.ollama_provider import OllamaProvider
    from app.ai.provider_factory import get_provider

    original = get_provider()
    assert isinstance(original, OllamaProvider)

    await client.put("/api/ai/settings", json={"ollama_model": "a-different-model"})

    rebuilt = get_provider()
    assert rebuilt is not original
    assert rebuilt.model == "a-different-model"


async def test_partial_update_leaves_other_fields_unchanged(client):
    await client.put("/api/ai/settings", json={"ollama_model": "llama3.1"})
    resp = await client.put("/api/ai/settings", json={"ollama_base_url": "http://example.invalid:11434"})
    assert resp.json() == {
        "provider": "ollama",
        "ollama_base_url": "http://example.invalid:11434",
        "ollama_model": "llama3.1",
        "custom_api_base_url": "",
        "custom_api_model": "",
        "has_custom_api_key": False,
    }


async def test_can_switch_provider_and_configure_custom_api(client):
    resp = await client.put(
        "/api/ai/settings",
        json={
            "provider": "custom_api",
            "custom_api_base_url": "https://api.example.com/v1",
            "custom_api_model": "gpt-4o-mini",
            "custom_api_key": "sk-secret",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "custom_api"
    assert body["custom_api_base_url"] == "https://api.example.com/v1"
    assert body["custom_api_model"] == "gpt-4o-mini"
    # The key itself is never echoed back, only whether one is set.
    assert body["has_custom_api_key"] is True
    assert "custom_api_key" not in body

    from app.ai.openai_compatible_provider import OpenAICompatibleProvider
    from app.ai.provider_factory import get_provider

    provider = get_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "gpt-4o-mini"


async def test_list_models_against_real_fake_ollama_server(client):
    server = await start_fake_ollama_server(chat_turns=[])
    try:
        resp = await client.get("/api/ai/models", params={"base_url": server.base_url})
        assert resp.status_code == 200
        assert resp.json() == {"models": ["qwen3:8b"]}
    finally:
        await server.close()


async def test_list_models_unreachable_server_returns_502(client):
    resp = await client.get("/api/ai/models", params={"base_url": "http://127.0.0.1:1"})
    assert resp.status_code == 502
