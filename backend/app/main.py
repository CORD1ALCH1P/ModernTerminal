from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import agent_ws, ai_settings, folders, hosts, terminal_ws

app = FastAPI(title="ModernTerminal", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(folders.router)
app.include_router(hosts.router)
app.include_router(terminal_ws.router)
app.include_router(agent_ws.router)
app.include_router(ai_settings.router)


# NOTE: API routers must be included above this line. The static mount below is a
# catch-all for "/" that serves the built frontend SPA, and must be registered last.
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
