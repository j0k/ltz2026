# -*- coding: utf-8 -*-
"""Favicon стенда: цветные позвонки как в атласе на синем градиенте и белая ось через них.

    .venv/bin/python scripts/make_favicon.py [--preview out.png]

Пишет dxaqc/web/static/favicon.svg, favicon.ico (16, 32, 48) и apple-touch-icon.png (180) из одной геометрии.
"""
from __future__ import annotations

import argparse
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dxaqc", "web", "static")
BG_TOP, BG_BOTTOM = (37, 99, 235), (91, 33, 182)       # синий сверху, фиолетовый снизу
VERT_COLORS = [(255, 138, 76), (52, 211, 153), (251, 191, 36)]  # позвонки в духе палитры атласа: оранжевый, зелёный, янтарный
AXIS = (255, 255, 255)
SHINE = (255, 255, 255, 46)                             # мягкий блик сверху, только в крупных размерах
# геометрия в сетке 64 × 64, размеры кратны 4: в 16 px позвонок 8 × 3 пикселя, ось ровно 2 пикселя
CORNER = 14
VERTEBRAE = [(16, 8, 32, 12), (16, 24, 32, 12), (16, 40, 32, 12)]  # x, y, ширина, высота
VERT_R = 3
AXIS_RECT = (28, 4, 8, 56)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(c[:3])


def svg() -> str:
    parts = [
        "<defs>"
        f'<linearGradient id="bg" x1="0" y1="0" x2="0.35" y2="1"><stop offset="0" stop-color="{_hex(BG_TOP)}"/>'
        f'<stop offset="1" stop-color="{_hex(BG_BOTTOM)}"/></linearGradient>'
        "</defs>",
        f'<rect width="64" height="64" rx="{CORNER}" fill="url(#bg)"/>',
        '<ellipse cx="22" cy="10" rx="22" ry="9" fill="#ffffff" opacity="0.18"/>',
    ]
    parts += [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{VERT_R}" fill="{_hex(c)}"/>'
              for (x, y, w, h), c in zip(VERTEBRAE, VERT_COLORS)]
    ax, ay, aw, ah = AXIS_RECT
    parts.append(f'<rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" rx="2" fill="{_hex(AXIS)}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' + "".join(parts) + "</svg>\n"


def _gradient(size: int) -> Image.Image:
    """Вертикальный градиент с лёгким наклоном, как в SVG."""
    im = Image.new("RGBA", (size, size))
    px = im.load()
    for y in range(size):
        for x in range(size):
            t = min(1.0, max(0.0, (y + 0.35 * x) / (size * 1.0 + 0.35 * size) * 1.35))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,)
    return im


def _mask(size: int, radius: float) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def pixel(size: int) -> Image.Image:
    """16 и 32 px рисуем прямо по пикселям: при уменьшении тонкая ось размывается."""
    k = size / 64
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.paste(_gradient(size), (0, 0), _mask(size, max(2, round(CORNER * k))))
    d = ImageDraw.Draw(im)
    for (x, y, w, h), c in zip(VERTEBRAE, VERT_COLORS):
        d.rectangle([x * k, y * k, (x + w) * k - 1, (y + h) * k - 1], fill=c)
    ax, ay, aw, ah = AXIS_RECT
    d.rectangle([ax * k, ay * k, (ax + aw) * k - 1, (ay + ah) * k - 1], fill=AXIS)
    return im


def raster(size: int, rounded: bool = True) -> Image.Image:
    if size in (16, 32) and rounded:
        return pixel(size)
    S, k = 512, 512 / 64  # крупные размеры рисуем с запасом и уменьшаем, так края ровные
    base = _gradient(S)
    shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shine).ellipse([0, 1 * k, 44 * k, 19 * k], fill=SHINE)
    base = Image.alpha_composite(base, shine)
    d = ImageDraw.Draw(base)
    for (x, y, w, h), c in zip(VERTEBRAE, VERT_COLORS):
        d.rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k], radius=VERT_R * k, fill=c)
    ax, ay, aw, ah = AXIS_RECT
    d.rounded_rectangle([ax * k, ay * k, (ax + aw) * k, (ay + ah) * k], radius=2 * k, fill=AXIS)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    im.paste(base, (0, 0), _mask(S, CORNER * k) if rounded else None)
    return im.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "favicon.svg"), "w", encoding="utf-8") as f:
        f.write(svg())
    # в ICO каждый размер свой: 16 и 32 по пикселям, 48 уменьшением
    raster(48).save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)],
                    append_images=[raster(16), raster(32)])
    # iOS сам скругляет углы, поэтому квадрат без скругления
    raster(180, rounded=False).convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"), optimize=True)
    if a.preview:
        both = Image.new("RGB", (560, 480), "#ffffff")
        ImageDraw.Draw(both).rectangle([0, 240, 560, 480], fill="#202124")
        for y0 in (0, 240):
            x = 20
            for s in (16, 32, 48, 180):
                ic = raster(s)
                both.paste(ic, (x, y0 + 30 + (180 - s) // 2), ic)
                x += s + 40
        both.save(a.preview)
    print("готово:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
