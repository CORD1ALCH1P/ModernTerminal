def test_encrypt_decrypt_roundtrip(_test_env):
    from app.crypto import decrypt_secret, encrypt_secret

    token = encrypt_secret("hunter2")

    assert token != b"hunter2"
    assert decrypt_secret(token) == "hunter2"


def test_key_file_created_with_restricted_permissions(_test_env):
    import stat
    from pathlib import Path

    from app.config import get_settings
    from app.crypto import encrypt_secret

    encrypt_secret("trigger-key-creation")

    key_path = Path(get_settings().master_key_file)
    assert key_path.exists()
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == 0o600
