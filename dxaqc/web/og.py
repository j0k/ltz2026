# -*- coding: utf-8 -*-
"""Картинки превью ссылок (OpenGraph) 1200×630: карточка снимка, сводка прогона и общая картинка стенда.

Telegram и другие мессенджеры показывают их рядом со ссылкой. Рисуются тем же шрифтом Inter и в тех же тёмных
цветах, что атлас, поэтому превью узнаётся с первого взгляда.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from dxaqc import atlas as T

W, H = 1200, 630
VERSION = 1  # поднять при смене оформления: кэшированные картинки пересоздадутся
BG, PANEL = (18, 20, 24), (28, 32, 39)
WHITE, BODY, MUTED, ACCENT = (240, 243, 247), (214, 220, 227), (143, 154, 167), (90, 167, 255)
VERDICT = {0: ("качественное", (12, 163, 12)), 1: ("нарушение", (208, 59, 59)), None: ("не оценено", (120, 128, 138))}
FOOTER = "ЛЦТ 2026 · задача 04 Департамента здравоохранения Москвы"
FOOTER_SHORT = "ЛЦТ 2026 · задача 04 ДепЗдрава"


def _wrap(d, text: str, font, width: float, max_lines: int) -> list[str]:
    words, lines, cur, used = (text or "").split(), [], "", 0
    for w in words:
        t = f"{cur} {w}".strip()
        if not cur or d.textlength(t, font=font) <= width:
            cur, used = t, used + 1
            continue
        lines.append(cur)
        if len(lines) == max_lines:
            break
        cur, used = w, used + 1
    else:
        if cur:
            lines.append(cur)
    lines = lines[:max_lines]
    if used < len(words) or len(" ".join(lines).split()) < len(words):   # не поместилось — многоточие
        last = lines[-1] if lines else ""
        while last and d.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1:] = [last.rstrip(" ,;:") + "…"]
    return lines


def _fit(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    im = im.convert("RGB")
    r = min(box_w / im.width, box_h / im.height)
    return im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), Image.LANCZOS)


def _brand(d, x: int, y: int):
    fb = T.font(26, True)
    d.text((x, y), "DXA QC", font=fb, fill=ACCENT, anchor="ls")
    d.text((x + d.textlength("DXA QC", font=fb) + 12, y), "контроль качества денситометрии", font=T.font(21), fill=MUTED, anchor="ls")


def _pill(d, x: int, y: int, text: str, color, size: int = 27) -> int:
    f = T.font(size, True)
    h = size + 22
    d.rounded_rectangle([x, y, x + d.textlength(text, font=f) + 62, y + h], radius=h // 2,
                        fill=T._mix(color, BG, 0.72), outline=T._mix(color, BG, 0.3), width=2)
    d.ellipse([x + 21, y + h / 2 - 7, x + 35, y + h / 2 + 7], fill=T._mix(color, (255, 255, 255), 0.25))
    d.text((x + 46, y + h / 2), text, font=f, fill=T._mix(color, (255, 255, 255), 0.62), anchor="lm")
    return y + h


def card(atlas_path: str, region: str, verdict, lines: list[str], name: str) -> Image.Image:
    """Карточка снимка: атлас слева, справа область, вердикт, нарушения или пояснения и имя файла."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    left = 700
    try:
        a = _fit(Image.open(atlas_path), left - 40, H - 50)
        img.paste(a, (20 + (left - 40 - a.width) // 2, (H - a.height) // 2))
    except (OSError, ValueError):
        pass
    x, width = left + 10, W - left - 50
    _brand(d, x, 74)
    y = 112
    ft = T.font(48, True)
    for ln in _wrap(d, region, ft, width, 2):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 58
    label, color = VERDICT.get(verdict, VERDICT[None])
    y = _pill(d, x, y + 12, label, color) + 26
    f = T.font(25)
    for text in lines[:4]:
        wrapped = _wrap(d, text, f, width - 24, 3)
        if y + 34 * len(wrapped) > H - 110:
            break
        d.ellipse([x + 1, y + 11, x + 10, y + 20], fill=color)
        for ln in wrapped:
            d.text((x + 24, y), ln, font=f, fill=BODY, anchor="la")
            y += 34
        y += 10
    for ln in _wrap(d, name, T.font(20), width, 1):
        d.text((x, H - 80), ln, font=T.font(20), fill=MUTED, anchor="la")
    d.text((x, H - 38), FOOTER_SHORT, font=T.font(18), fill=MUTED, anchor="ls")
    return img


def run(title: str, summary: dict, thumbs: list[str], state: str = "") -> Image.Image:
    """Сводка прогона: название, плитки счётчиков и полоса миниатюр — сначала снимки с нарушением."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    x = 60
    _brand(d, x, 84)
    y = 112
    ft = T.font(50, True)
    for ln in _wrap(d, title, ft, W - 2 * x, 2):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 62
    if state:
        d.text((x, y + 6), state, font=T.font(25, True), fill=ACCENT, anchor="la")
        y += 44
    tiles = [("снимков", summary.get("images", 0), WHITE), ("качественных", summary.get("good", 0), (70, 205, 100)),
             ("с нарушением", summary.get("bad", 0), (245, 105, 100)), ("не оценено", summary.get("not_evaluated", 0), MUTED)]
    gap = 20
    tw, ty = (W - 2 * x - 3 * gap) / 4, max(y + 22, 250)
    for i, (label, n, color) in enumerate(tiles):
        tx = x + i * (tw + gap)
        d.rounded_rectangle([tx, ty, tx + tw, ty + 128], radius=18, fill=PANEL)
        d.text((tx + 24, ty + 20), str(n), font=T.font(56, True), fill=color, anchor="la")
        d.text((tx + 24, ty + 94), label, font=T.font(23), fill=MUTED, anchor="la")
    sy = ty + 148
    th = H - 58 - sy
    cx = x
    if th >= 60:
        for path in thumbs:
            try:
                t = _fit(Image.open(path), 360, th)
            except (OSError, ValueError):
                continue
            if cx + t.width > W - x:
                break
            img.paste(t, (cx, sy))
            cx += t.width + 14
    d.text((x, H - 22), FOOTER, font=T.font(18), fill=MUTED, anchor="ls")
    return img


def site(example_atlas: str | None) -> Image.Image:
    """Общая картинка стенда: что умеет сервис и пример атласа."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    x, width = 60, 560
    _brand(d, x, 84)
    y = 118
    ft = T.font(52, True)
    for ln in _wrap(d, "Контроль качества денситометрии DXA", ft, width, 3):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 62
    y += 18
    f = T.font(25)
    for text in ("область, вердикт и причина брака по каждому снимку", "разметка в стиле анатомического атласа",
                 "сравнение с экспертами: F1 и ROC-AUC", "работает локально, снимки не уходят наружу"):
        d.ellipse([x + 1, y + 11, x + 10, y + 20], fill=ACCENT)
        for ln in _wrap(d, text, f, width - 24, 2):
            d.text((x + 24, y), ln, font=f, fill=BODY, anchor="la")
            y += 34
        y += 8
    d.text((x, H - 38), FOOTER, font=T.font(18), fill=MUTED, anchor="ls")
    if example_atlas:
        try:
            a = _fit(Image.open(example_atlas), 520, H - 60)
            img.paste(a, (W - 40 - a.width, (H - a.height) // 2))
        except (OSError, ValueError):
            pass
    return img
