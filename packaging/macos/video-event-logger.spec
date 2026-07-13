# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parents[1]
entrypoint = project_root / "video_event_logger" / "main.py"
svg_icon = project_root / "video_event_logger" / "assets" / "app_icon.svg"
icns_icon = project_root / "build" / "macos" / "app_icon.icns"

app_version = "0.0.0"
for line in (project_root / "video_event_logger" / "app_config.py").read_text().splitlines():
    if line.startswith("APP_VERSION = "):
        app_version = line.split("=", 1)[1].strip().strip('"')
        break

if not icns_icon.exists():
    raise FileNotFoundError(
        "macOS icon is missing. Run: python packaging/macos/create_icns.py"
    )

a = Analysis(
    [str(entrypoint)],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(svg_icon), "video_event_logger/assets")],
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
    name="Video Event Logger",
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
    icon=str(icns_icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Video Event Logger",
)

app = BUNDLE(
    coll,
    name="Video Event Logger.app",
    icon=str(icns_icon),
    bundle_identifier="com.videoeventlogger.app",
    info_plist={
        "CFBundleName": "Video Event Logger",
        "CFBundleDisplayName": "Video Event Logger",
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "NSHighResolutionCapable": True,
    },
)
