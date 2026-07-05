"""Desktop entry point: runs the existing FastAPI app in a background thread
and shows the existing built frontend in a native OS window via pywebview,
instead of a browser tab. Not used by Docker/dev-server workflows -- those
keep running `uvicorn app.main:app` directly, unaffected by this module.

Import order matters: `app.config.get_settings()` is `@lru_cache`d and read at
import time by `app/db.py` and `app/crypto.py`, so the data-dir env vars below
must be set *before* anything below imports from `app.main`.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

DEFAULT_PORT = 47861


def _bundle_base_dir() -> Path:
    """Directory containing alembic.ini/alembic/ -- the PyInstaller bundle
    root when frozen (sys._MEIPASS), else backend/ in the source tree."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def _configure_data_dir() -> Path:
    import platformdirs

    data_dir = Path(platformdirs.user_data_dir("Savr", appauthor=False))
    data_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{data_dir / 'savr.db'}")
    os.environ.setdefault("MASTER_KEY_FILE", str(data_dir / "master.key"))
    return data_dir


def _redirect_output_to_log_file(data_dir: Path) -> None:
    """The packaged build has no console window, so without this a startup
    crash would be completely invisible -- stdout/stderr go to a log file in
    the same data directory as the database instead."""
    log_path = data_dir / "savr.log"
    log_file = open(log_path, "a", buffering=1)  # noqa: SIM115 -- lives for the process
    sys.stdout = log_file
    sys.stderr = log_file


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_bundle_base_dir() / "alembic.ini"))
    command.upgrade(cfg, "head")


def _start_server(port: int):
    import asyncio

    import uvicorn

    from app.main import app  # deferred: must come after env vars are set

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    return server, thread


def _wait_for_health(port: int, timeout_s: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def main() -> None:
    # WebKitGTK's hardware-accelerated compositing/DMA-BUF renderer produces a
    # blank black window in several real environments (software-rendering-only
    # GPUs, some VMs/containers) -- falling back to software compositing is a
    # little slower but far more reliably actually shows the page. setdefault
    # so a user who knows their setup is fine can still override.
    os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")

    data_dir = _configure_data_dir()
    _redirect_output_to_log_file(data_dir)
    _run_migrations()

    port = int(os.environ.get("SAVR_DESKTOP_PORT", str(DEFAULT_PORT)))
    server, thread = _start_server(port)

    if not _wait_for_health(port):
        raise RuntimeError(f"Savr backend did not start on port {port} in time")

    import webview

    # PNG works for the GTK (Linux) and Cocoa (macOS) backends; Windows'
    # winforms backend needs an .ico specifically (System.Drawing.Icon can't
    # load a bare PNG), so pick per-platform from the two bundled files.
    icon_name = "icon.ico" if sys.platform == "win32" else "icon.png"
    icon_path = Path(__file__).resolve().parent / "assets" / icon_name

    webview.create_window("Savr", f"http://127.0.0.1:{port}", width=1400, height=900)
    webview.start(icon=str(icon_path) if icon_path.is_file() else None)

    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
