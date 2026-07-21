# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


project_root = Path(SPECPATH).resolve().parents[1]
entrypoint = project_root / "video_event_logger" / "main.py"
app_icon = project_root / "video_event_logger" / "assets" / "app_icon.svg"
build_mode = os.environ.get("BUILD_MODE", "release").strip().lower()
if build_mode not in {"debug", "release"}:
    raise ValueError("BUILD_MODE must be 'debug' or 'release', got: %s" % build_mode)
debug_build = build_mode == "debug"


def is_system_vlc_runtime(entry):
    destination = str(entry[0]).replace("\\", "/")
    source = str(Path(entry[1]).resolve()).replace("\\", "/")
    source_is_system = any(
        source == root or source.startswith(root + "/")
        for root in ("/lib", "/lib64", "/usr/lib", "/usr/lib64")
    )
    if not source_is_system:
        return False
    filename = Path(destination).name
    is_vlc_library = (
        filename == "libvlc.so"
        or filename.startswith("libvlc.so.")
        or filename == "libvlccore.so"
        or filename.startswith("libvlccore.so.")
    )
    is_vlc_plugin = "/vlc/plugins/" in ("/" + destination.lstrip("/")) or "/vlc/plugins/" in source
    return is_vlc_library or is_vlc_plugin

a = Analysis(
    [str(entrypoint)],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(app_icon), "video_event_logger/assets")],
    hiddenimports=["vlc"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtNetwork"],
    noarchive=False,
    optimize=0,
)
# Python's bundled _ctypes extension is linked against Ubuntu 20.04's
# libffi.so.7. Keep that one narrow runtime dependency so the package also
# starts on newer Ubuntu systems that provide only libffi.so.8. glibc and
# system VLC remain excluded.
a.exclude_system_libraries(list_of_exceptions=["libffi.so.*"])
a.binaries = [entry for entry in a.binaries if not is_system_vlc_runtime(entry)]
a.datas = [entry for entry in a.datas if not is_system_vlc_runtime(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="video-event-logger",
    debug=debug_build,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=debug_build,
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
