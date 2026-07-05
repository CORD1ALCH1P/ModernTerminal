from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Host(Base):
    __tablename__ = "hosts"
    __table_args__ = (
        CheckConstraint("protocol IN ('ssh', 'telnet')", name="ck_hosts_protocol"),
        CheckConstraint(
            "auth_method IN ('password', 'private_key', 'none')", name="ck_hosts_auth_method"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    label: Mapped[str] = mapped_column(String(255))
    protocol: Mapped[str] = mapped_column(String(16))
    hostname: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_method: Mapped[str] = mapped_column(String(16), default="none")
    secret_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ssh_host_key_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Opt-in only: widens SSHConnector's negotiated kex/cipher/MAC algorithms
    # to include ones modern asyncssh excludes by default for being weak
    # (diffie-hellman-group1-sha1, CBC-mode ciphers, hmac-md5) -- needed to
    # reach old devices (e.g. Cisco IOS 12) that never speak anything newer.
    legacy_crypto: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
