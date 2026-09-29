# -*- coding: utf-8 -*-
"""Значок приложения: синий квадрат, стопка позвонков, зелёная галочка качества → icon.png (256) и icon.ico.
Значок файла снимка: лист с загнутым углом и значок приложения → dcm.ico (установщик: «Открывать файлы .dcm в Kostik»)."""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dxaqc", "desktop", "assets")
S = 1024
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bg = Image.new("RGBA", (S, S))
top, bot = (58, 140, 232), (24, 78, 160)
for y in range(S):
    t = y / S
    ImageDraw.Draw(bg).line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
im.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(im)
for i, (w, y) in enumerate([(300, 190), (330, 360), (350, 530), (330, 700)]):   # позвонки
    d.rounded_rectangle([S / 2 - w / 2 - 40, y, S / 2 + w / 2 - 40, y + 130], radius=48, fill=(255, 255, 255, 245))
    d.rounded_rectangle([S / 2 - 30 - 40, y + 130, S / 2 + 30 - 40, y + 170], radius=12, fill=(190, 215, 250, 255))
cx, cy, r = 760, 760, 190                                                       # галочка
d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(27, 175, 122, 255), outline=(255, 255, 255, 255), width=28)
d.line([(cx - 95, cy + 5), (cx - 25, cy + 80), (cx + 105, cy - 70)], fill=(255, 255, 255, 255), width=56, joint="curve")
im.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
im.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def document(size: int) -> Image.Image:
    """Лист со значком Kostik нужного размера: рисуем крупнее и уменьшаем, обводка не тоньше 1 px."""
    k = 8
    n = size * k
    line = max(1, round(size / 64)) * k
    edge, paper, corner = (132, 148, 170, 255), (250, 251, 253, 255), (214, 224, 238, 255)
    doc = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    g = ImageDraw.Draw(doc)
    x0, y0, x1, y1, fold = n * 0.17, n * 0.05, n * 0.83, n * 0.95, n * 0.22
    sheet = [(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)]
    g.polygon(sheet, fill=paper)
    g.polygon([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], fill=corner)
    g.line(sheet + sheet[:2], fill=edge, width=line, joint="curve")
    g.line([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], fill=edge, width=line, joint="curve")
    m = round(n * 0.54)
    doc.alpha_composite(im.resize((m, m), Image.LANCZOS), (round(n / 2 - m / 2), round(n * 0.36)))
    return doc.resize((size, size), Image.LANCZOS)


SIZES = [16, 24, 32, 48, 64, 128, 256]
docs = {s: document(s) for s in SIZES}
docs[256].save(os.path.join(OUT, "dcm.ico"), sizes=[(s, s) for s in SIZES], append_images=[docs[s] for s in SIZES[:-1]])
print("ok", OUT)
