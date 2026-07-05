from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/savr.db"

    # Secret-encryption master key. MASTER_KEY takes precedence; otherwise a key is
    # loaded from (and created at, on first run) MASTER_KEY_FILE.
    master_key: str | None = None
    master_key_file: str = "./data/master.key"

    # AI copilot (Part 2). Provider-agnostic by design -- "ollama" (local) and
    # "custom_api" (any OpenAI-compatible /chat/completions endpoint, e.g. a
    # cloud API or a self-hosted server like vLLM/LM Studio) are both
    # implemented -- see app/ai/provider_factory.py.
    ai_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_request_timeout_s: float = 120.0

    # base_url should include any version prefix the server expects (e.g.
    # "https://api.openai.com/v1") -- "/chat/completions" is appended as-is.
    custom_api_base_url: str = ""
    custom_api_key: str = ""
    custom_api_model: str = ""
    custom_api_request_timeout_s: float = 120.0

    ai_scrollback_max_bytes: int = 65536
    ai_command_quiet_ms: int = 700
    ai_command_max_wait_ms: int = 5000
    ai_max_history_messages: int = 40
    # Caps a single model *call's* generated length (Ollama's `num_predict` /
    # OpenAI-compatible `max_tokens`). Without this, a model that degenerates
    # into a repetition loop -- a real, observed failure mode on small local
    # models -- has nothing but its context window (thousands of tokens)
    # stopping it, turning one turn into a multi-minute stall. A response
    # that hits this cap without finishing is automatically continued with a
    # fresh call (see app/ai/loop.py) rather than left trailing off
    # mid-sentence, so this only bounds each individual call, not the total
    # length the agent can say in one turn.
    ai_max_response_tokens: int = 2048
    # Additive only -- appended to, never replaces, the built-in dangerous-command
    # denylist in app/ai/safety.py. Comma or newline separated regex patterns.
    ai_dangerous_extra_patterns: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
