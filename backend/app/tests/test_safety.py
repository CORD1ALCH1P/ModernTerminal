from app.ai.safety import is_dangerous


def test_recognizes_default_dangerous_commands():
    assert is_dangerous("reload")
    assert is_dangerous("write erase")
    assert is_dangerous("format bootflash:")
    assert is_dangerous("erase startup-config")
    assert is_dangerous("shutdown")
    assert is_dangerous("rm -rf /")


def test_case_insensitive():
    assert is_dangerous("RELOAD")
    assert is_dangerous("Write Erase")


def test_safe_commands_not_flagged():
    assert not is_dangerous("show running-config")
    assert not is_dangerous("interface gi0/1")
    assert not is_dangerous("ip address 10.0.0.1 255.255.255.0")


def test_extra_patterns_are_additive_not_replacing(monkeypatch):
    from app.ai import safety

    monkeypatch.setenv("AI_DANGEROUS_EXTRA_PATTERNS", "wipe-everything")
    from app.config import get_settings

    get_settings.cache_clear()
    safety._compiled_patterns.cache_clear()
    try:
        assert is_dangerous("wipe-everything")
        assert is_dangerous("reload")  # built-in list still active, not replaced
    finally:
        safety._compiled_patterns.cache_clear()
        get_settings.cache_clear()
