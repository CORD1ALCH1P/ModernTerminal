# PyInstaller spec for the Savr desktop build (pywebview window + bundled
# FastAPI backend). Build with: pyinstaller savr_desktop.spec
#
# Deliberately does NOT bundle GTK3/WebKit2GTK or their .typelib files -- those
# are large system shared libraries that the target Linux machine is expected
# to already have installed (see README's desktop-build section). This only
# bundles the Python-level PyGObject bindings plus our own app code, frontend
# build, and Alembic migrations.

import pathlib

block_cipher = None

datas = [
    ("app/static", "app/static"),
    ("alembic", "alembic"),
    ("alembic.ini", "."),
]

a = Analysis(
    ["app/desktop_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "aiosqlite",
        "asyncssh",
        "telnetlib3",
        "webview.platforms.gtk",
        "gi",
        "gi.overrides.GLib",
        "gi.overrides.Gtk",
        "gi.overrides.GObject",
        "gi.overrides.Gio",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
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
