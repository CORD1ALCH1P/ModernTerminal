import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

__all__ = ["encrypt_secret", "decrypt_secret", "InvalidToken"]


def _load_or_create_key() -> bytes:
    settings = get_settings()
    if settings.master_key:
        return settings.master_key.encode()

    path = Path(settings.master_key_file)
    if path.exists():
        return path.read_text().strip().encode()

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_text(key.decode())
    os.chmod(path, 0o600)
    return key


@lru_cache
def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_secret(token: bytes) -> str:
    return _fernet().decrypt(token).decode()
