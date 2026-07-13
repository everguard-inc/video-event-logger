# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parents[1]
entrypoint = project_root / "video_event_logger" / "main.py"
app_icon = project_root / "video_event_logger" / "assets" / "app_icon.svg"

a = Analysis(
    [str(entrypoint)],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(app_icon), "video_event_logger/assets")],
    hiddenimports=["vlc"],
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
    [],
    exclude_binaries=True,
    name="video-event-logger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="video-event-logger",
)
