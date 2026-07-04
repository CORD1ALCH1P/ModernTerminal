# PyInstaller spec for the Savr desktop build (pywebview window + bundled
# FastAPI backend). Build with: pyinstaller savr_desktop.spec
#
# This spec is platform-aware (see PLATFORM_HIDDENIMPORTS below) so the same
# file works when run on Linux, macOS, or Windows -- but PyInstaller never
# cross-compiles, so it must actually be *run* on each target OS to produce
# that OS's build.
#
# Deliberately does NOT bundle GTK3/WebKit2GTK (Linux) or their .typelib
# files -- those are large system shared libraries the target Linux machine
# is expected to already have installed (see README's desktop-build section).
# macOS's WKWebView and Windows' WebView2 are part of the OS/usually
# preinstalled, so nothing equivalent needs bundling there either. This only
# bundles the Python-level webview bindings plus our own app code, frontend
# build, and Alembic migrations.

import sys

block_cipher = None

datas = [
    ("app/static", "app/static"),
    ("alembic", "alembic"),
    ("alembic.ini", "."),
]

if sys.platform.startswith("linux"):
    platform_hiddenimports = [
        "webview.platforms.gtk",
        "gi",
        "gi.overrides.GLib",
        "gi.overrides.Gtk",
        "gi.overrides.GObject",
        "gi.overrides.Gio",
    ]
elif sys.platform == "win32":
    platform_hiddenimports = [
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr_loader",
    ]
elif sys.platform == "darwin":
    platform_hiddenimports = ["webview.platforms.cocoa"]
else:
    platform_hiddenimports = []

a = Analysis(
    ["app/desktop_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "aiosqlite",
        "asyncssh",
        "telnetlib3",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        *platform_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="savr",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="savr",
)
