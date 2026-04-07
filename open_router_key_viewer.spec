import io
from contextlib import redirect_stdout

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


with redirect_stdout(io.StringIO()):
    datas = collect_data_files("qfluentwidgets")
    hiddenimports = collect_submodules("qfluentwidgets")

datas += [("assets/open-router-key-viewer.svg", "assets")]


a = Analysis(
    ["src/open_router_key_viewer/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name="open-router-key-viewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="build/icons/open-router-key-viewer.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
