# -*- coding: utf-8 -*-
"""Кадры для главной: примеры снимков, которые подходят для загрузки, в стилизованном виде.

Снимки берутся из прогона примера и последнего прогона всего обучающего набора: поясничный отдел, правое и левое
бедро по кругу, без повторов. Стилизация — дуотон «рентгеновский циан» на тёмно-синем, мягкое свечение светлых
участков, виньетка и тонкие линии развёртки. Кадр рисуется по первому запросу и кэшируется на диске.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

VERSION = 1  # поднять при смене стилизации: кэш пересоздастся
SIZE = 560
MAX_FRAMES = 8
REGIONS = ["lumbar_spine", "hip_right", "hip_left"]
REGION_RU = {"lumbar_spine": "поясничный отдел", "hip_right": "правое бедро", "hip_left": "левое бедро"}
NOTE = {"lumbar_spine": "DICOM DXA · прямая проекция",
        "hip_right": "DICOM DXA · проксимальный отдел",
        "hip_left": "DICOM DXA · проксимальный отдел"}


def pick(sources: list[tuple[str, dict | None]], limit: int = MAX_FRAMES) -> list[dict]:
    """sources — пары (прогон, manifest). Кадры по кругу по областям; у позвоночника сначала качественные снимки."""
    pools: dict[str, list[dict]] = {r: [] for r in REGIONS}
    seen = set()
    for run_id, man in sources:
        for row in (man or {}).get("rows", []):
            reg, key = row.get("anatomical_region"), row.get("key")
            if reg not in pools or row.get("processing_status") != "Success" or not row.get("original_png") or not key or key in seen:
                continue
            seen.add(key)
            pools[reg].append(dict(run_id=run_id, key=key, region=reg, region_ru=REGION_RU[reg], note=NOTE[reg],
                                   good=row.get("quality_class") == 0))
    for reg in pools:
        pools[reg].sort(key=lambda f: not f["good"])   # устойчивая сортировка сохраняет порядок внутри групп
    out: list[dict] = []
    while len(out) < limit and any(pools.values()):
        for reg in REGIONS:
            if pools[reg] and len(out) < limit:
                out.append(pools[reg].pop(0))
    return out


def _lut(stops):
    xs = [p for p, _ in stops]
    return [np.interp(np.arange(256) / 255, xs, [c[ch] for _, c in stops]).round().astype(int).tolist() for ch in range(3)]


# тёмно-синий → синий → циан → почти белый
LUT = _lut([(0.0, (6, 12, 24)), (0.32, (16, 46, 88)), (0.68, (56, 160, 214)), (1.0, (236, 250, 255))])


def stylize(src_path: str) -> Image.Image:
    g = ImageOps.autocontrast(Image.open(src_path).convert("L"), cutoff=1)
    g.thumbnail((SIZE - 36, SIZE - 36), Image.LANCZOS)
    canvas = Image.new("L", (SIZE, SIZE), 0)
    canvas.paste(g, ((SIZE - g.width) // 2, (SIZE - g.height) // 2))
    rgb = Image.merge("RGB", [canvas.point(t) for t in LUT])
    glow = Image.blend(Image.new("RGB", rgb.size), rgb.filter(ImageFilter.GaussianBlur(12)), 0.5)
    rgb = ImageChops.screen(rgb, glow)
    y, x = np.mgrid[0:SIZE, 0:SIZE]
    r2 = ((x - SIZE / 2) / (SIZE / 2)) ** 2 + ((y - SIZE / 2) / (SIZE / 2)) ** 2
    vignette = np.clip(1.08 - 0.5 * r2, 0.35, 1.0)
    scan = np.where(y % 4 == 0, 0.93, 1.0)
    a = np.asarray(rgb, np.float32) * (vignette * scan)[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
