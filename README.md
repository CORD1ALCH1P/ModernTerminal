# Savr

A self-hosted, web-based session manager for SSH/Telnet hosts — organize connections into
labeled folders and connect from the browser (like MobaXterm, without the desktop client).
Single-user, runs locally via Docker Compose, or as a [native desktop app](#run-it-as-a-desktop-app-no-browserdocker-needed).

Part 2 is an AI copilot that chats alongside an open terminal tab and can read/type into that same
live session, with a per-session confirm-before-apply / auto-apply toggle (see "AI copilot" below).

## Features

- Session tree: nested folders and hosts, right-click context menus (create/rename/delete),
  drag-and-drop to reorder or move items between folders.
- SSH and Telnet connections, streamed over a WebSocket into a browser terminal (xterm.js),
  with live resize.
- Multiple concurrent tabs, including several tabs to the same host; background tabs stay
  connected while you work in another tab.
- Host secrets (passwords, private keys) encrypted at rest with a server-side master key —
  never returned by the API once saved.
- SSH host-key trust-on-first-use: the first connection pins the server's host key fingerprint;
  a later mismatch (e.g. the device was reimaged) is rejected with an "Accept new key & reconnect"
  action in the terminal's status banner, rather than silently trusted.
- No silent auto-reconnect on a dropped session — a status banner with a manual "Reconnect"
  button appears instead, so a network blip doesn't surprise you mid-task on live equipment.
- **AI plugin:** an "AI Plugin" button on each connected terminal tab opens a chat panel beside
  it. The agent reads that tab's recent output and can type commands into the same live session,
  backed by a local Ollama model by default (provider-agnostic — see `backend/app/ai/base.py`).
  Every new session defaults to confirm-before-apply; a built-in denylist of dangerous commands
  (`reload`, `erase`, `format`, `shutdown`, etc.) always pauses for human approval regardless of
  mode, with an inline Approve/Reject card.

## Run it (packaged, via Docker Compose)

```bash
docker compose up --build
```

Then open http://localhost:8000. Data (the SQLite DB and the encryption master key) persists in
the `savr_data` Docker volume across restarts.

The app is bound to `127.0.0.1` only and has **no login**. Do not change the compose port binding
to expose it beyond localhost/your local network without adding an auth layer first.

> **Note on verification:** this Dockerfile/compose setup was written and reviewed carefully but
> could not be executed in the sandbox this project was built in (no `docker` available there).
> What *was* verified end-to-end there is the equivalent packaged flow run manually — production
> frontend build copied into the backend's static directory, Alembic migrations, and `uvicorn`
> serving both the API and the SPA from one process — exercised with a real headless browser
> (folder/host CRUD, drag-and-drop, SSH connect against a real in-process test server, resize,
> multi-tab, host-key mismatch + accept + reconnect flows). Please do run `docker compose up
> --build` yourself before relying on it, to confirm the container build itself works in your
> environment.

## Run it as a desktop app (no browser/Docker needed)

Instead of opening a browser tab, Savr can run as a native desktop app: the same backend runs in
the background and the same frontend renders in a native OS window (via
[pywebview](https://pywebview.flowrl.com/)), not a browser tab.

Build it yourself (there's no pre-built download yet):

```bash
./scripts/build_desktop.sh
```

This produces `backend/dist/savr/savr` (plus its supporting `_internal/` folder — copy the whole
`backend/dist/savr/` directory together, it's not a single self-contained file). Run `./savr` to
launch it.

- **Where your data lives:** a per-OS user data directory (via
  [`platformdirs`](https://github.com/tox-dev/platformdirs)) instead of Docker's `./data` volume —
  `~/.local/share/Savr` on Linux, `~/Library/Application Support/Savr` on macOS, `%APPDATA%\Savr` on
  Windows. Includes `savr.log`, since the packaged app has no console to print startup errors to.
- **Linux dependency:** the desktop build renders via GTK3 + WebKit2GTK (through PyGObject), which
  is virtually always already installed on desktop Linux distros, but not guaranteed on a minimal or
  server install. If the build/run step complains about `gi`/`Gtk`/`WebKit2`, install (Debian/Ubuntu
  package names, adjust for your distro): `sudo apt install python3-gi gir1.2-gtk-3.0
  gir1.2-webkit2-4.1 libgirepository-2.0-dev pkg-config`. Windows (WebView2, normally preinstalled
  on Win10/11) and macOS (built-in WKWebView) don't need anything extra, but must be built on those
  OSes respectively — `scripts/build_desktop.sh` produces a build for whatever platform it's run on,
  it does not cross-compile.
- **Troubleshooting a blank/black window:** the build already sets
  `WEBKIT_DISABLE_COMPOSITING_MODE`/`WEBKIT_DISABLE_DMABUF_RENDERER` (WebKitGTK's hardware-accelerated
  renderer produces a blank window in several VMs/containers/software-rendering-only setups). If a
  window opens but stays blank on Linux, also try forcing `GDK_BACKEND=x11 ./savr` — a `WAYLAND_DISPLAY`
  left over from an unrelated remote-desktop/container GUI-forwarding setup can otherwise make GTK try
  to render to the wrong display entirely.
- Custom port: `SAVR_DESKTOP_PORT=... ./savr` (defaults to 47861).
- This is additive: `docker compose` / `uvicorn app.main:app` keep working exactly as before, using
  their own separate data locations — the desktop build is just a different way to run the same app.

### Building on Windows

`scripts/build_desktop.sh` is a bash script; the easiest way to run it as-is on Windows is via
**Git Bash** (installed alongside [Git for Windows](https://git-scm.com/downloads/win)). It detects
Windows' `Scripts/` venv layout automatically.

One-time setup:

1. Install [Python 3.12+](https://www.python.org/downloads/windows/) — check "Add python.exe to
   PATH" during install.
2. Install [Node.js LTS](https://nodejs.org/).
3. Install [Git for Windows](https://git-scm.com/downloads/win) (gives you Git Bash).

Then, in **Git Bash**:

```bash
git clone https://github.com/CORD1ALCH1P/ModernTerminal.git
cd ModernTerminal
./scripts/build_desktop.sh
```

This produces `backend\dist\savr\savr.exe`. Run it by double-clicking, or from a terminal:

```
cd backend\dist\savr
savr.exe
```

If you'd rather not install Git Bash, run the equivalent steps directly in PowerShell:

```powershell
cd frontend
npm ci
npm run build
Remove-Item -Recurse -Force ..\backend\app\static -ErrorAction SilentlyContinue
Copy-Item -Recurse dist\* ..\backend\app\static\

cd ..\backend
python -m venv .venv-desktop-build
.venv-desktop-build\Scripts\Activate.ps1
pip install -e ".[desktop]"
pyinstaller savr_desktop.spec --noconfirm
```

Windows-specific notes:

- pywebview renders via **WebView2** (the Chromium-based component Microsoft ships with Windows
  10/11) through `pythonnet`, which `pip install` pulls in automatically for you — nothing to add
  manually. On an older or stripped-down Windows install without WebView2, install the
  [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) redistributable.
- SmartScreen: since the `.exe` isn't code-signed, Windows will likely show "Windows protected your
  PC" on first run. Click "More info" → "Run anyway".
- Data lives at `%APPDATA%\Savr\` (`savr.db`, `master.key`, `savr.log`).
- **Not yet built or tested by me** — the PyInstaller spec is written to be platform-aware (it only
  references GTK/PyGObject on Linux, WebView2/pythonnet on Windows), and pywebview/PyInstaller both
  officially support Windows, but this container can only build and verify the Linux binary. If the
  build fails on a step, share the error output and I'll adjust the spec.

## AI copilot setup

The copilot needs a local [Ollama](https://ollama.com) server reachable from the backend, with a
tool-calling-capable model pulled:

```bash
ollama pull qwen3:8b   # or another tool-capable model -- see OLLAMA_MODEL below
ollama serve           # if not already running as a service
```

- **Docker Compose:** assumes Ollama runs on your host machine, and reaches it via
  `http://host.docker.internal:11434` (wired up in `docker-compose.yml`, including the
  `extra_hosts` entry Linux needs to resolve that hostname — Docker Desktop on Mac/Windows provides
  it automatically). If Ollama runs somewhere else, override `OLLAMA_BASE_URL`.
- **Local dev:** set `OLLAMA_BASE_URL`/`OLLAMA_MODEL` in `backend/.env` (see `.env.example`);
  defaults assume `http://localhost:11434`.
- **Or change it from the UI:** the "Settings" button in any open AI Plugin panel lets you edit the
  Ollama URL and pick a model from a live-fetched list, without restarting the backend (`GET`/`PUT
  /api/ai/settings`, `GET /api/ai/models`). This is in-memory only — it resets to the env-var
  defaults above on restart, same as chat history and terminal scrollback. Since it's a global
  setting, an already-open chat panel picks it up on its next reconnect (close and reopen the panel
  to apply immediately).
- The model landscape moves fast and tool-calling quality varies a lot by model — `qwen3:8b` is
  today's verified-working default, not a long-term guarantee. Override `OLLAMA_MODEL` freely. If
  the configured model doesn't report tool-calling support, the chat panel shows an inline warning
  (via `GET /api/show` against your Ollama server) rather than failing silently.
- The AI provider is pluggable (`backend/app/ai/base.py`'s `AIProvider` interface) — Ollama is the
  only implementation today, but a cloud provider could be added later behind the same interface
  without touching the tool-calling loop or the frontend.

## Develop locally (without Docker)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env   # adjust if needed
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` (including the WebSocket terminal endpoint) to
the backend on port 8000, so no CORS configuration is needed in dev either.

## Testing

```bash
cd backend
source .venv/bin/activate
pytest -q
```

The suite spins up real in-process test servers rather than mocking protocols: `asyncssh` and
`telnetlib3` servers for the terminal connectors (see `backend/app/tests/ssh_test_server.py`,
`telnet_test_server.py`), and a minimal hand-rolled HTTP/1.1 chunked-streaming server that speaks
Ollama's real NDJSON wire format for the AI provider (`backend/app/tests/fake_ollama_server.py`).
This covers host-key trust-on-first-use/mismatch-rejection, and the full AI tool-calling loop
including the confirmation-pause flow, against real network I/O rather than mocks. There's no
frontend test suite yet (see "Known gaps" below).

## Project layout

```
backend/    FastAPI app: REST API, WebSocket terminal + agent bridges, SSH/Telnet connectors,
            AI provider abstraction, SQLite via SQLAlchemy
frontend/   React + TypeScript + Vite + xterm.js
```

See `backend/app/connectors/` for the SSH/Telnet abstraction and `backend/app/ai/` for the AI
copilot: `base.py` (provider-agnostic interface), `ollama_provider.py`, `session_registry.py`
(correlates a terminal tab with its live connector for the agent to read/write), `tools.py` +
`loop.py` (the tool-calling conversation loop), `safety.py` (dangerous-command denylist).

## Security notes

- Secrets (host passwords, private keys) are encrypted at rest with `cryptography.Fernet`, keyed
  by a master key auto-generated on first run at `MASTER_KEY_FILE` (default `./data/master.key`,
  `0600` permissions). Master-key compromise means all stored secrets are compromised — there's no
  key rotation in this MVP, the same trust model as a local MobaXterm/KeePass-style credential
  store.
- There is no login. The app must not be exposed beyond localhost/your trusted local network
  without adding an auth layer first.
- SSH host keys use trust-on-first-use pinning (see Features above) rather than blind trust or a
  full known_hosts/CA setup.
- The AI copilot defaults every new session to **confirm-before-apply**, never auto-apply. A
  built-in dangerous-command denylist (`backend/app/ai/safety.py`) always forces a manual
  confirmation regardless of mode; `AI_DANGEROUS_EXTRA_PATTERNS` can only add to that list, never
  replace it. Using a local Ollama model by default (rather than a cloud API) keeps device configs
  and credentials off third-party infrastructure.

## Known gaps / not yet built

- No automated frontend test suite (Playwright was used manually during development to verify both
  Part 1 and the AI copilot end-to-end, but no test files were added to the repo).
- No multi-user support, roles, or authentication (explicit MVP scope decision).
- Telnet credentials are metadata-only; login happens interactively in the terminal stream itself,
  the same as a raw MobaXterm telnet session.
- AI chat history and terminal scrollback are in-memory only, per active connection — both reset if
  you hit "Reconnect" on a dropped session, and don't survive a backend restart.
- AI chat history has a simple message-count cap (`AI_MAX_HISTORY_MESSAGES`), not summarization —
  very long conversations will lose earlier context.
- Desktop build: only Linux has actually been built and verified so far. Windows/macOS use the
  identical entry point (`backend/app/desktop_app.py`) and PyInstaller spec, but haven't been
  produced or smoke-tested on those OSes yet. The desktop build also uses a fixed default port with
  no "detect and focus the already-running instance" handling — a second launch (or a port
  collision) fails rather than gracefully attaching to the first.
