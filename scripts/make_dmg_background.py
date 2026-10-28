#!/usr/bin/env python3
"""Draw the background of Caelumite's DMG window (scripts/build_release.py).

A light sky with a few of the app icon's sparkles, an arrow from the app to
the Applications folder, and a one-line hint. The icons themselves come
from Finder; their centres are ICON_APP and ICON_APPS in window points.

Usage: .venv/bin/python scripts/make_dmg_background.py <dir>

Writes <dir>/background.png (WIDTH x HEIGHT) and background@2x.png;
dmgbuild combines the pair into one HiDPI image.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen)

USAGE = "Usage: .venv/bin/python scripts/make_dmg_background.py <dir>"
WIDTH, HEIGHT = 640, 400
ICON_APP = (170, 180)
ICON_APPS = (470, 180)
HINT = "Drag Caelumite to Applications to install it"


def _star(p: QPainter, x: float, y: float, r: float, alpha: int) -> None:
    path = QPainterPath()
    path.moveTo(x, y - r)
    path.quadTo(x, y, x + r, y)
    path.quadTo(x, y, x, y + r)
    path.quadTo(x, y, x - r, y)
    path.quadTo(x, y, x, y - r)
    p.fillPath(path, QColor(74, 147, 230, alpha))


def draw(scale: int) -> QImage:
    img = QImage(WIDTH * scale, HEIGHT * scale, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)

    sky = QLinearGradient(0, 0, 0, HEIGHT)
    sky.setColorAt(0.0, QColor("#f7f9fe"))
    sky.setColorAt(1.0, QColor("#e3e9f7"))
    p.fillRect(QRectF(0, 0, WIDTH, HEIGHT), sky)

    for x, y, r, a in ((52, 48, 7, 70), (598, 64, 9, 60), (318, 46, 5, 55),
                       (88, 330, 5, 45), (566, 318, 6, 50), (612, 214, 4, 40)):
        _star(p, x, y, r, a)

    # Arrow between the icons, clear of their 128 pt frames.
    y = ICON_APP[1]
    x0, x1 = ICON_APP[0] + 92, ICON_APPS[0] - 92
    pen = QPen(QColor("#3d82d6"), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(QPointF(x0, y), QPointF(x1 - 4, y))
    p.drawPolyline([QPointF(x1 - 20, y - 16), QPointF(x1, y), QPointF(x1 - 20, y + 16)])

    font = QFont(".AppleSystemUIFont")
    font.setPixelSize(15)
    p.setFont(font)
    p.setPen(QColor("#4b5670"))
    p.drawText(QRectF(0, 318, WIDTH, 30), Qt.AlignHCenter | Qt.AlignVCenter, HINT)
    p.end()
    return img


def main() -> int:
    if len(sys.argv) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - QImage/QPainter need it
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for scale, name in ((1, "background.png"), (2, "background@2x.png")):
        img = draw(scale)
        img.setDevicePixelRatio(scale)
        if not img.save(str(out / name)):
            print(f"error: could not write {out / name}", file=sys.stderr)
            return 1
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
