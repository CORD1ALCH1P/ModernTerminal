"""
No `app.*` module may be imported at module level anywhere in this test suite.
Settings (DB path, master key path) are read once, at first use, via a cached
pydantic-settings singleton -- importing app.config/app.db/app.crypto before
_test_env below has set the environment would lock in the real dev settings
for the rest of the process.
"""

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def _test_env(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("savr-test")
    import os

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_dir / 'test.db'}"
    os.environ["MASTER_KEY_FILE"] = str(tmp_dir / "master.key")


@pytest_asyncio.fixture
async def _fresh_db(_test_env):
    """Wipe and re-migrate the test DB before each test.

    Runs fully async (no asyncio.run()) so it shares the same event loop
    pytest-asyncio is already running the test on -- mixing a fixture-local
    asyncio.run() with pytest-asyncio's own loop management caused cross-loop
    hangs (a Task/Future ending up attached to a since-discarded loop).
    Alembic's `command.upgrade` is itself synchronous and calls asyncio.run()
    internally, so it's pushed onto a worker thread via asyncio.to_thread,
    which gives it a brand new loop in a different thread -- no conflict.
    """
    from app.db import db_path, engine

    # The app engine may hold pooled connections open against the file we're
    # about to delete; dispose them first or they'd keep writing to the old
    # (unlinked but still-open) inode instead of the freshly migrated file.
    await engine.dispose()

    if db_path is not None:
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")


@pytest_asyncio.fixture
async def client(_fresh_db):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
