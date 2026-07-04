from __future__ import annotations

import re
from functools import lru_cache

from app.config import get_settings

# Deliberately over-inclusive (e.g. a plain interface "shutdown" also matches) --
# an unnecessary extra confirmation prompt fails safe; a missed catastrophic
# command does not.
DEFAULT_DANGEROUS_PATTERNS: list[str] = [
    r"\breload\b",
    r"\breboot\b",
    r"\brestart\b",
    r"\berase\b",
    r"\bwrite\s+erase\b",
    r"\bformat\s+\S*(flash|bootflash|disk)\S*",
    r"\bdelete\s*/(force|recursive)\b",
    r"\bshutdown\b",
    r"\bpoweroff\b",
    r"\bhalt\b",
    r"\bfactory[- ]?(reset|default)\b",
    r"\bzeroize\b",
    r"\bclear\s+config\b",
    r"\bno\s+boot\b",
    r"\brm\s+-rf\b",
    r"\brmdir\b",
]


def _parse_extra_patterns(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,\n]", raw) if p.strip()]


@lru_cache
def _compiled_patterns() -> list[re.Pattern[str]]:
    settings = get_settings()
    patterns = [*DEFAULT_DANGEROUS_PATTERNS, *_parse_extra_patterns(settings.ai_dangerous_extra_patterns)]
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def is_dangerous(command: str) -> bool:
    return any(pattern.search(command) for pattern in _compiled_patterns())
