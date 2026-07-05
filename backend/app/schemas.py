from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Protocol = Literal["ssh", "telnet"]
AuthMethod = Literal["password", "private_key", "none"]

DEFAULT_PORTS: dict[Protocol, int] = {"ssh": 22, "telnet": 23}


# --- Folders ---------------------------------------------------------------


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None


class FolderRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderMove(BaseModel):
    parent_id: int | None = None
    index: int = Field(ge=0)


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- Hosts -------------------------------------------------------------


class HostCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    folder_id: int | None = None
    protocol: Protocol
    hostname: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    auth_method: AuthMethod = "none"
    secret: str | None = None
    passphrase: str | None = None
    legacy_crypto: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _apply_defaults_and_validate(self) -> "HostCreate":
        if self.port is None:
            self.port = DEFAULT_PORTS[self.protocol]
        if self.protocol == "ssh" and self.auth_method == "none":
            raise ValueError("SSH hosts require auth_method 'password' or 'private_key'")
        if self.auth_method in ("password", "private_key") and not self.secret:
            raise ValueError(f"'secret' is required when auth_method={self.auth_method!r}")
        return self


class HostUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    auth_method: AuthMethod | None = None
    secret: str | None = None
    passphrase: str | None = None
    legacy_crypto: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # folder_id intentionally omitted -- use POST /api/hosts/{id}/move


class HostMove(BaseModel):
    folder_id: int | None = None
    index: int = Field(ge=0)


class AcceptHostKey(BaseModel):
    fingerprint: str = Field(min_length=1)


class HostOut(BaseModel):
    id: int
    folder_id: int | None
    label: str
    protocol: Protocol
    hostname: str
    port: int
    username: str | None
    auth_method: AuthMethod
    has_secret: bool
    ssh_host_key_fingerprint: str | None
    legacy_crypto: bool
    notes: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
