from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SVG_ICON = PROJECT_ROOT / "video_event_logger" / "assets" / "app_icon.svg"
BUILD_DIR = PROJECT_ROOT / "build" / "macos"
ICONSET_DIR = BUILD_DIR / "AppIcon.iconset"
ICNS_PATH = BUILD_DIR / "app_icon.icns"

ICON_FILES = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)

ICNS_CHUNKS = (
    ("icp4", "icon_16x16.png"),
    ("icp5", "icon_32x32.png"),
    ("icp6", "icon_32x32@2x.png"),
    ("ic07", "icon_128x128.png"),
    ("ic08", "icon_256x256.png"),
    ("ic09", "icon_512x512.png"),
    ("ic10", "icon_512x512@2x.png"),
)


def render_png(renderer: QSvgRenderer, output_path: Path, size: int) -> None:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    if not image.save(str(output_path), "PNG"):
        raise RuntimeError(f"Failed to write {output_path}")


def write_icns(iconset_dir: Path, output_path: Path) -> None:
    chunks = []
    for chunk_type, filename in ICNS_CHUNKS:
        png_data = (iconset_dir / filename).read_bytes()
        chunk = chunk_type.encode("ascii") + struct.pack(">I", len(png_data) + 8) + png_data
        chunks.append(chunk)

    total_size = 8 + sum(len(chunk) for chunk in chunks)
    output_path.write_bytes(b"icns" + struct.pack(">I", total_size) + b"".join(chunks))


def main() -> int:
    if not SVG_ICON.exists():
        print(f"SVG icon not found: {SVG_ICON}", file=sys.stderr)
        return 1

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if ICONSET_DIR.exists():
        shutil.rmtree(ICONSET_DIR)
    ICONSET_DIR.mkdir()

    renderer = QSvgRenderer(str(SVG_ICON))
    if not renderer.isValid():
        print(f"Invalid SVG icon: {SVG_ICON}", file=sys.stderr)
        return 1

    for filename, size in ICON_FILES:
        render_png(renderer, ICONSET_DIR / filename, size)

    write_icns(ICONSET_DIR, ICNS_PATH)
    print(ICNS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
