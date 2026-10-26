#!/usr/bin/env python3
"""Draw Caelumite's app icon over upstream's src/icons/Logo.png (1024x1024).

A faceted sky-blue crystal on a night-sky tile, laid out on Apple's icon
grid (an 824 px rounded square centred in the 1024 px canvas).

Usage: .venv/bin/python scripts/make_icon.py [master-1024.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient)

SIZE = 1024
TILE = 824
OUT = Path(__file__).resolve().parents[1] / "src" / "icons" / "Logo.png"
LOGO_PX = 250  # upstream's Logo.png size; some views draw it unscaled


def _poly(*pts) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _star(p: QPainter, x: float, y: float, r: float, alpha: int) -> None:
    path = QPainterPath()
    path.moveTo(x, y - r)
    path.quadTo(x, y, x + r, y)
    path.quadTo(x, y, x, y + r)
    path.quadTo(x, y, x - r, y)
    path.quadTo(x, y, x, y - r)
    p.fillPath(path, QColor(255, 255, 255, alpha))


def draw() -> QImage:
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # Tile: deep night sky fading to dusk blue.
    off = (SIZE - TILE) / 2
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(off, off, TILE, TILE), 185, 185)
    sky = QLinearGradient(0, off, 0, off + TILE)
    sky.setColorAt(0.0, QColor("#0b1030"))
    sky.setColorAt(0.65, QColor("#1b2a6b"))
    sky.setColorAt(1.0, QColor("#3a5bb8"))
    p.fillPath(tile, sky)
    p.setClipPath(tile)

    # Soft glow behind the crystal.
    glow = QRadialGradient(QPointF(512, 560), 330)
    glow.setColorAt(0.0, QColor(120, 200, 255, 120))
    glow.setColorAt(1.0, QColor(120, 200, 255, 0))
    p.fillRect(QRectF(0, 0, SIZE, SIZE), QBrush(glow))

    for x, y, r, a in ((260, 250, 16, 220), (760, 300, 11, 180), (705, 205, 7, 150),
                       (300, 760, 9, 140), (790, 720, 13, 170), (210, 470, 6, 120)):
        _star(p, x, y, r, a)

    # Crystal: a hexagonal prism with a pointed crown, lit from the upper left.
    top, crown, waist, base = 215, 395, 690, 830
    left, cl, cr, right = 330, 430, 594, 694
    facets = [
        (_poly((512, top), (left, crown), (cl, crown + 40)), "#e8f7ff", "#a9dcff"),
        (_poly((512, top), (cl, crown + 40), (cr, crown + 40)), "#c9ecff", "#7cc4ff"),
        (_poly((512, top), (cr, crown + 40), (right, crown)), "#8fd0ff", "#4a93e6"),
        (_poly((left, crown), (cl, crown + 40), (cl, waist), (left, waist - 30)), "#9ad8ff", "#4f9be8"),
        (_poly((cl, crown + 40), (cr, crown + 40), (cr, waist), (cl, waist)), "#6fbaf5", "#2f6fcc"),
        (_poly((cr, crown + 40), (right, crown), (right, waist - 30), (cr, waist)), "#3f86dc", "#1f4fa8"),
        (_poly((left, waist - 30), (cl, waist), (512, base)), "#5aa6ee", "#2a5fb8"),
        (_poly((cl, waist), (cr, waist), (512, base)), "#3d82d6", "#1d4796"),
        (_poly((cr, waist), (right, waist - 30), (512, base)), "#2a63b8", "#152f73"),
    ]
    edge = QPen(QColor(230, 246, 255, 150), 3)
    edge.setJoinStyle(Qt.RoundJoin)
    for poly, c0, c1 in facets:
        rect = poly.boundingRect()
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(c0))
        grad.setColorAt(1.0, QColor(c1))
        p.setBrush(QBrush(grad))
        p.setPen(edge)
        p.drawPolygon(poly)

    _star(p, 470, 300, 30, 235)
    p.end()
    return img


def main() -> int:
    """Write Logo.png (250 px, upstream's size); with an argument, also write
    the full 1024 px master there (for the .app icon)."""
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - QImage/QPainter need it
    img = draw()
    targets = [(OUT, LOGO_PX)] + [(Path(a), SIZE) for a in sys.argv[1:]]
    for path, px in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        out = img if px == SIZE else img.scaled(
            px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if not out.save(str(path)):
            print(f"error: could not write {path}", file=sys.stderr)
            return 1
        print(f"wrote {path} ({px} px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
