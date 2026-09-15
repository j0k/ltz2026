# -*- coding: utf-8 -*-
"""Картинки для карточки снимка: исходник и разметка сервиса поверх него."""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCALE = 2
GREEN = (27, 190, 122)
RED = (235, 80, 78)
CYAN = (90, 200, 250)
AMBER = (240, 170, 20)

_FONT_CANDIDATES = [
    os.environ.get("DXAQC_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


def _font(size: int):
    for p in _FONT_CANDIDATES:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def original(pixels: np.ndarray) -> Image.Image:
    im = Image.fromarray(pixels).convert("RGB")
    return im.resize((im.width * SCALE, im.height * SCALE), Image.LANCZOS)


def _dashed_rect(d, box, color, width=2, dash=8):
    x0, y0, x1, y1 = box
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        length = max(abs(bx - ax), abs(by - ay))
        steps = max(int(length // dash), 1)
        for i in range(0, steps, 2):
            t0, t1 = i / steps, min((i + 1) / steps, 1)
            d.line([(ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)], fill=color, width=width)


def overlay(pixels: np.ndarray, res: dict) -> Image.Image:
    im = original(pixels)
    d = ImageDraw.Draw(im)
    g = res.get("geometry", {})
    s = SCALE

    def S(p):
        return [(x * s, y * s) for x, y in p]

    if res.get("region") == "lumbar_spine":
        for box, ok in zip(g.get("iliac_boxes", []), g.get("iliac_ok", [])):
            _dashed_rect(d, [v * s for v in box], GREEN if ok else RED, width=2)
        pts = S(g.get("centerline", []))
        for x, y in pts:
            d.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=CYAN)
        if g.get("axis"):
            d.line(S(g["axis"]), fill=GREEN if g.get("axis_ok") else RED, width=3)
        for x, y in S(g.get("thirds", [])):
            d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=AMBER, width=3)
        for box in g.get("artifact_boxes", []):
            d.rectangle([v * s for v in box], outline=RED, width=3)
    elif res.get("region") in ("hip_right", "hip_left") and g.get("shaft_x") is not None:
        x = g["shaft_x"] * s
        d.line([(x, im.height * 0.55), (x, im.height - 4)], fill=CYAN, width=3)
        ax = x + (60 if res["region"] == "hip_right" else -60)
        d.line([(x, im.height * 0.35), (ax, im.height * 0.25)], fill=AMBER, width=3)
        d.ellipse([ax - 6, im.height * 0.25 - 6, ax + 6, im.height * 0.25 + 6], fill=AMBER)

    q = res.get("quality_class")
    label, color = {0: ("качественное", GREEN), 1: ("нарушение", RED)}.get(q, ("не оценено", (150, 150, 150)))
    f = _font(15)
    tw = d.textlength(label, font=f)
    d.rounded_rectangle([8, 8, 8 + tw + 18, 34], radius=8, fill=color)
    d.text((17, 11), label, font=f, fill=(255, 255, 255))
    return im
