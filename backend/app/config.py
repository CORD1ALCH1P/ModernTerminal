from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/savr.db"

    # Secret-encryption master key. MASTER_KEY takes precedence; otherwise a key is
    # loaded from (and created at, on first run) MASTER_KEY_FILE.
    master_key: str | None = None
    master_key_file: str = "./data/master.key"

    # AI copilot (Part 2). Provider-agnostic by design; "ollama" is the only
    # one implemented so far -- see app/ai/provider_factory.py.
    ai_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_request_timeout_s: float = 120.0

    ai_scrollback_max_bytes: int = 65536
    ai_command_quiet_ms: int = 700
    ai_command_max_wait_ms: int = 5000
    ai_max_history_messages: int = 40
    # Caps a single model turn's generated length (Ollama's `num_predict`).
    # Without this, a model that degenerates into a repetition loop -- a real,
    # observed failure mode on small local models -- has nothing but its
    # context window (thousands of tokens) stopping it, turning one turn into
    # a multi-minute stall. Generous enough for a normal explanation-plus-tool-
    # call turn, including a "thinking" model's reasoning preamble.
    ai_max_response_tokens: int = 1024
    # Additive only -- appended to, never replaces, the built-in dangerous-command
    # denylist in app/ai/safety.py. Comma or newline separated regex patterns.
    ai_dangerous_extra_patterns: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
