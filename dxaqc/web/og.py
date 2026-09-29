# -*- coding: utf-8 -*-
"""Картинки превью ссылок (OpenGraph) 2400×1260 (раскладка 1200×630 в двойной плотности): карточка снимка, сводка прогона, общая картинка стенда и карточки страниц.

Telegram и другие мессенджеры показывают их рядом со ссылкой. Рисуются тем же шрифтом Inter и в тех же тёмных
цветах, что атлас, поэтому превью узнаётся с первого взгляда.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from dxaqc import atlas as T

W, H = 1200, 630   # логическая раскладка; рисуется в S раз крупнее — Telegram растягивает превью, 1× выглядел мыльно
S = 2
VERSION = 6  # поднять при смене оформления: кэшированные картинки пересоздадутся
BG, PANEL = (18, 20, 24), (28, 32, 39)
WHITE, BODY, MUTED, ACCENT = (246, 248, 251), (226, 231, 237), (156, 166, 178), (96, 172, 255)
VERDICT = {0: ("качественное", (12, 163, 12)), 1: ("нарушение", (208, 59, 59)), None: ("не оценено", (120, 128, 138))}
FOOTER = "ЛЦТ 2026 · задача 04 Департамента здравоохранения Москвы"
FOOTER_SHORT = "ЛЦТ 2026 · задача 04 ДепЗдрава"


_FONTS: dict = {}


def _font(size: int, bold: bool = False, weight: int | None = None):
    """Inter Display в плотных начертаниях, как системный шрифт Mac: после сжатия превью Telegram тонкий текст мылится."""
    w = weight or (760 if bold else 480)
    key = (size, w)
    if key not in _FONTS:
        if not os.path.exists(T.INTER):
            return T.font(size * S, bold)
        f = ImageFont.truetype(T.INTER, size * S, layout_engine=ImageFont.Layout.BASIC)
        try:
            f.set_variation_by_axes([32, w])      # оптический размер Display и насыщенность
        except (OSError, ValueError):
            pass
        _FONTS[key] = f
    return _FONTS[key]


class _Draw:
    """ImageDraw в логических координатах 1200×630: координаты, радиусы и толщины умножаются на S."""

    def __init__(self, img: Image.Image):
        self.d = ImageDraw.Draw(img)

    @staticmethod
    def _xy(xy):
        return [(a * S, b * S) for a, b in xy] if isinstance(xy[0], (tuple, list)) else [v * S for v in xy]

    def _kw(self, kw):
        return {k: (v * S if k in ("radius", "width") and v else v) for k, v in kw.items()}

    def text(self, xy, text, **kw):
        self.d.text((xy[0] * S, xy[1] * S), text, **kw)

    def textlength(self, text, font):
        return self.d.textlength(text, font=font) / S

    def rectangle(self, xy, **kw):
        self.d.rectangle(self._xy(xy), **self._kw(kw))

    def rounded_rectangle(self, xy, **kw):
        self.d.rounded_rectangle(self._xy(xy), **self._kw(kw))

    def ellipse(self, xy, **kw):
        self.d.ellipse(self._xy(xy), **self._kw(kw))

    def line(self, xy, **kw):
        self.d.line(self._xy(xy), **self._kw(kw))

    def polygon(self, xy, **kw):
        self.d.polygon(self._xy(xy), **self._kw(kw))

    def regular_polygon(self, circle, n_sides, **kw):
        self.d.regular_polygon(tuple(v * S for v in circle), n_sides, **kw)


def _canvas():
    img = Image.new("RGB", (W * S, H * S), BG)
    return img, _Draw(img)


def _paste(img: Image.Image, part: Image.Image, x: float, y: float):
    img.paste(part, (round(x * S), round(y * S)))


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
    """Вписать в рамку (логические px); результат в пикселях холста, размеры для раскладки — .width / S."""
    im = im.convert("RGB")
    r = min(box_w * S / im.width, box_h * S / im.height)
    return im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), Image.LANCZOS)


def _brand(d, x: int, y: int):
    fb = _font(32, weight=820)
    d.text((x, y), "Kostik", font=fb, fill=ACCENT, anchor="ls")
    d.text((x + d.textlength("Kostik", font=fb) + 14, y), "контроль качества денситометрии", font=_font(23, weight=520), fill=MUTED, anchor="ls")


def _pill(d, x: int, y: int, text: str, color, size: int = 27) -> int:
    f = _font(size, True)
    h = size + 22
    d.rounded_rectangle([x, y, x + d.textlength(text, font=f) + 62, y + h], radius=h // 2,
                        fill=T._mix(color, BG, 0.72), outline=T._mix(color, BG, 0.3), width=2)
    d.ellipse([x + 21, y + h / 2 - 7, x + 35, y + h / 2 + 7], fill=T._mix(color, (255, 255, 255), 0.25))
    d.text((x + 46, y + h / 2), text, font=f, fill=T._mix(color, (255, 255, 255), 0.62), anchor="lm")
    return y + h


def card(atlas_path: str, region: str, verdict, lines: list[str], name: str) -> Image.Image:
    """Карточка снимка: атлас слева, справа область, вердикт, нарушения или пояснения и имя файла."""
    img, d = _canvas()
    left = 700
    try:
        a = _fit(Image.open(atlas_path), left - 40, H - 50)
        _paste(img, a, 20 + (left - 40 - a.width / S) / 2, (H - a.height / S) / 2)
    except (OSError, ValueError):
        pass
    x, width = left + 10, W - left - 50
    _brand(d, x, 74)
    y = 112
    ft = _font(48, True)
    for ln in _wrap(d, region, ft, width, 2):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 58
    label, color = VERDICT.get(verdict, VERDICT[None])
    y = _pill(d, x, y + 12, label, color) + 26
    f = _font(25)
    for text in lines[:4]:
        wrapped = _wrap(d, text, f, width - 24, 3)
        if y + 34 * len(wrapped) > H - 110:
            break
        d.ellipse([x + 1, y + 11, x + 10, y + 20], fill=color)
        for ln in wrapped:
            d.text((x + 24, y), ln, font=f, fill=BODY, anchor="la")
            y += 34
        y += 10
    for ln in _wrap(d, name, _font(20), width, 1):
        d.text((x, H - 80), ln, font=_font(20), fill=MUTED, anchor="la")
    d.text((x, H - 38), FOOTER_SHORT, font=_font(18), fill=MUTED, anchor="ls")
    return img


def run(title: str, summary: dict, thumbs: list[str], state: str = "") -> Image.Image:
    """Сводка прогона: название, плитки счётчиков и полоса миниатюр — сначала снимки с нарушением."""
    img, d = _canvas()
    x = 60
    _brand(d, x, 84)
    y = 112
    ft = _font(50, True)
    for ln in _wrap(d, title, ft, W - 2 * x, 2):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 62
    if state:
        d.text((x, y + 6), state, font=_font(25, True), fill=ACCENT, anchor="la")
        y += 44
    tiles = [("снимков", summary.get("images", 0), WHITE), ("качественных", summary.get("good", 0), (70, 205, 100)),
             ("с нарушением", summary.get("bad", 0), (245, 105, 100)), ("не оценено", summary.get("not_evaluated", 0), MUTED)]
    gap = 20
    tw, ty = (W - 2 * x - 3 * gap) / 4, max(y + 22, 250)
    for i, (label, n, color) in enumerate(tiles):
        tx = x + i * (tw + gap)
        d.rounded_rectangle([tx, ty, tx + tw, ty + 128], radius=18, fill=PANEL)
        d.text((tx + 24, ty + 20), str(n), font=_font(56, True), fill=color, anchor="la")
        d.text((tx + 24, ty + 94), label, font=_font(23), fill=MUTED, anchor="la")
    sy = ty + 148
    th = H - 58 - sy
    cx = x
    if th >= 60:
        for path in thumbs:
            try:
                t = _fit(Image.open(path), 360, th)
            except (OSError, ValueError):
                continue
            if cx + t.width / S > W - x:
                break
            _paste(img, t, cx, sy)
            cx += t.width / S + 14
    d.text((x, H - 22), FOOTER, font=_font(18), fill=MUTED, anchor="ls")
    return img


def site(example_atlas: str | None) -> Image.Image:
    """Общая картинка стенда: что умеет сервис и пример атласа."""
    img, d = _canvas()
    x, width = 60, 520
    _brand(d, x, 84)
    y = 116
    ft = _font(60, weight=820)
    for ln in _wrap(d, "Проверка снимков DXA за доли секунды", ft, width, 3):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 66
    y += 16
    f = _font(29, weight=540)
    for text in ("вердикт и причина брака по каждому снимку", "разметка как в анатомическом атласе",
                 "снимки не уходят наружу"):
        d.ellipse([x + 1, y + 13, x + 13, y + 25], fill=ACCENT)
        for ln in _wrap(d, text, f, width - 28, 2):
            d.text((x + 28, y), ln, font=f, fill=BODY, anchor="la")
            y += 40
        y += 10
    d.text((x, H - 38), FOOTER, font=_font(18), fill=MUTED, anchor="ls")
    if example_atlas:
        try:
            a = _fit(Image.open(example_atlas), 540, H - 40)
            _paste(img, a, W - 40 - a.width / S, (H - a.height / S) / 2)
        except (OSError, ValueError):
            pass
    return img


# ------------------------------------------------------------------ карточки страниц

def _tiles(d, x: int, y: int, width: float, tiles: list) -> int:
    """Ряд плиток со счётчиками, как в сводке прогона."""
    gap, n = 18, len(tiles)
    tw = (width - gap * (n - 1)) / n
    for i, (label, value, color) in enumerate(tiles):
        tx = x + i * (tw + gap)
        d.rounded_rectangle([tx, y, tx + tw, y + 118], radius=18, fill=PANEL)
        d.text((tx + 20, y + 16), str(value), font=_font(50, True), fill=color, anchor="la")
        for ln in _wrap(d, label, _font(20), tw - 36, 1):
            d.text((tx + 20, y + 84), ln, font=_font(20), fill=MUTED, anchor="la")
    return y + 118


def _art_tree(d, box):
    """Дерево требований: ветви и узлы со статусами — мотив mind map."""
    x0, y0, x1, y1 = box
    cx, cy = x0 + 46, (y0 + y1) / 2
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=ACCENT)
    colors = {"done": (70, 205, 100), "partial": (232, 170, 60), "todo": (120, 128, 138)}
    # ветвь: сдвиг по вертикали, статус и сдвиги листьев — фиксированные, чтобы узлы не наезжали друг на друга
    branches = [(-150, "done", (-42, 42)), (-50, "done", (0,)), (50, "partial", (-42, 42)), (150, "todo", (0,))]
    for dy, status, leaves in branches:
        mx, my = cx + 116, cy + dy
        d.line([cx + 16, cy, mx, my], fill=T._mix(colors[status], BG, 0.45), width=5)
        d.ellipse([mx - 13, my - 13, mx + 13, my + 13], fill=colors[status])
        for off in leaves:
            lx, ly = mx + 112, my + off
            if not (y0 + 18 < ly < y1 - 18):
                continue
            d.line([mx + 13, my, lx, ly], fill=T._mix(colors[status], BG, 0.6), width=4)
            d.rounded_rectangle([lx, ly - 13, min(lx + 122, x1 - 10), ly + 13], radius=13,
                                fill=T._mix(colors[status], BG, 0.78))


def _art_scatter(d, box):
    """Россыпь оценщиков и путь выбора по ним — мотив шпаргалки scikit-learn."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    dots = [(0.16, 0.22), (0.34, 0.12), (0.52, 0.26), (0.72, 0.16), (0.86, 0.34),
            (0.12, 0.52), (0.3, 0.44), (0.48, 0.58), (0.66, 0.46), (0.84, 0.62),
            (0.22, 0.78), (0.42, 0.86), (0.6, 0.74), (0.78, 0.88)]
    path = [dots[i] for i in (0, 2, 8, 12)]
    for i in range(len(path) - 1):
        d.line([x0 + path[i][0] * w, y0 + path[i][1] * h, x0 + path[i + 1][0] * w, y0 + path[i + 1][1] * h],
               fill=T._mix(ACCENT, BG, 0.5), width=5)
    for i, (rx, ry) in enumerate(dots):
        px, py = x0 + rx * w, y0 + ry * h
        on_path = (rx, ry) in path
        r = 17 if on_path else 11
        color = ACCENT if on_path else T._mix(MUTED, BG, 0.45)
        d.ellipse([px - r, py - r, px + r, py + r], fill=color)


def _art_docs(d, box):
    """Стопка листов с текстом — мотив раздела документов."""
    x0, y0, x1, y1 = box
    sw, sh = (x1 - x0) * 0.56, (y1 - y0) * 0.72
    for i, off in enumerate((44, 22, 0)):
        sx, sy = x0 + off + 20, y0 + (y1 - y0 - sh) / 2 - off * 0.5
        fill = PANEL if i < 2 else T._mix(WHITE, PANEL, 0.12)
        d.rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=16, fill=fill, outline=T._mix(MUTED, BG, 0.4), width=2)
        if i == 2:
            for k in range(6):
                ly = sy + 40 + k * 30
                if ly > sy + sh - 30:
                    break
                d.rounded_rectangle([sx + 26, ly, sx + sw - (26 if k % 3 else 80), ly + 10], radius=5,
                                    fill=T._mix(ACCENT if k == 0 else MUTED, PANEL, 0.35 if k == 0 else 0.6))


def _art_sliders(d, box):
    """Ползунки параметров — мотив пульта анализа."""
    x0, y0, x1, y1 = box
    w = x1 - x0 - 60
    top = (y0 + y1) / 2 - 1.5 * 74          # ряд ползунков по центру рисунка
    for i, pos in enumerate((0.62, 0.35, 0.78, 0.5)):
        sy = top + i * 74
        if sy > y1 - 40:
            break
        d.rounded_rectangle([x0 + 30, sy - 7, x0 + 30 + w, sy + 7], radius=7, fill=PANEL)
        d.rounded_rectangle([x0 + 30, sy - 7, x0 + 30 + w * pos, sy + 7], radius=7, fill=T._mix(ACCENT, BG, 0.35))
        kx = x0 + 30 + w * pos
        d.ellipse([kx - 18, sy - 18, kx + 18, sy + 18], fill=ACCENT)


def _art_chat(d, box):
    """Реплики диалога — мотив вопросов к Claude."""
    x0, y0, x1, y1 = box
    w = x1 - x0 - 60
    top = (y0 + y1) / 2 - (3 * 116 - 30) / 2    # реплики по центру рисунка
    for i, (side, frac) in enumerate(((0, 0.74), (1, 0.56), (0, 0.62))):
        by = top + i * 116
        if by + 86 > y1:
            break
        bw = w * frac
        bx = x0 + 30 + (w - bw if side else 0)
        d.rounded_rectangle([bx, by, bx + bw, by + 86], radius=22,
                            fill=T._mix(ACCENT, BG, 0.62) if side else PANEL)
        for k in range(2):
            d.rounded_rectangle([bx + 24, by + 26 + k * 26, bx + bw - (24 if k else 90), by + 36 + k * 26],
                                radius=5, fill=T._mix(WHITE if side else MUTED, PANEL, 0.55))


def _art_gantt(d, box):
    """Полоски задач и ромб вехи — мотив диаграммы Ганта."""
    x0, y0, x1, y1 = box
    w = x1 - x0 - 60
    rows = ((0.0, 0.46, True), (0.14, 0.34, True), (0.3, 0.44, False), (0.22, 0.3, True), (0.5, 0.38, False))
    top = (y0 + y1) / 2 - (len(rows) * 58 - 20) / 2
    for i, (off, frac, done) in enumerate(rows):
        by = top + i * 58
        d.rounded_rectangle([x0 + 30, by - 9, x0 + 30 + w, by + 9], radius=9, fill=T._mix(PANEL, BG, 0.4))
        bx = x0 + 30 + w * off
        d.rounded_rectangle([bx, by - 9, bx + w * frac, by + 9], radius=9,
                            fill=(70, 205, 100) if done else T._mix(ACCENT, BG, 0.25))
    mx = x0 + 30 + w * 0.82
    d.regular_polygon((mx, (y0 + y1) / 2, 22), n_sides=4, rotation=45, fill=(232, 170, 60))


def _art_roadmap(d, box):
    """Дорожки направлений с карточками и путь через них — мотив роудмапа."""
    x0, y0, x1, y1 = box
    w, lanes = x1 - x0 - 40, 4
    top = (y0 + y1) / 2 - (lanes * 86 - 26) / 2
    cards = [(0, 0.02), (0, 0.5), (1, 0.26), (2, 0.08), (2, 0.62), (3, 0.4)]
    centers = []
    for lane in range(lanes):
        ly = top + lane * 86
        d.line([x0 + 20, ly + 30, x0 + 20 + w, ly + 30], fill=T._mix(PANEL, BG, 0.2), width=2)
    for i, (lane, off) in enumerate(cards):
        cx, cy = x0 + 20 + w * off, top + lane * 86
        on = i in (0, 2, 4, 5)
        d.rounded_rectangle([cx, cy + 10, cx + w * 0.34, cy + 50], radius=10,
                            fill=T._mix(ACCENT, BG, 0.62) if on else PANEL, outline=ACCENT if on else None, width=2)
        if on:
            centers.append((cx + w * 0.17, cy + 30))
    for (ax, ay), (bx, by) in zip(centers, centers[1:]):
        d.line([ax, ay + 20, bx, by - 20], fill=ACCENT, width=4)


ARTS = {"roadmap": _art_roadmap, "gantt": _art_gantt, "tree": _art_tree, "scatter": _art_scatter, "docs": _art_docs, "sliders": _art_sliders, "chat": _art_chat}


def page(title: str, bullets: list[str], art: str = "", tiles: list | None = None) -> Image.Image:
    """Карточка обычной страницы: заголовок, короткие пункты, счётчики и рисунок-мотив справа."""
    img, d = _canvas()
    x = 60
    draw_art = ARTS.get(art)
    width = (640 if draw_art else W - 2 * x) - 0
    _brand(d, x, 84)
    y = 118
    ft = _font(50, True)
    for ln in _wrap(d, title, ft, width, 2):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 60
    y += 14
    f = _font(25)
    limit = H - (150 if tiles else 70)
    for text in bullets[:4]:
        wrapped = _wrap(d, text, f, width - 24, 2)
        if y + 34 * len(wrapped) > limit:
            break
        d.ellipse([x + 1, y + 11, x + 10, y + 20], fill=ACCENT)
        for ln in wrapped:
            d.text((x + 24, y), ln, font=f, fill=BODY, anchor="la")
            y += 34
        y += 8
    if tiles:
        _tiles(d, x, H - 190, width, tiles)
    if draw_art:
        draw_art(d, (x + width + 40, 70, W - 40, H - 70))
    d.text((x, H - 38), FOOTER, font=_font(18), fill=MUTED, anchor="ls")
    return img


def video(title: str, bullets: list[str], poster: str | None, duration: str = "") -> Image.Image:
    """Карточка страницы видео: заголовок и главы слева, кадр ролика с кнопкой воспроизведения справа."""
    img, d = _canvas()
    x, width = 60, 470
    _brand(d, x, 84)
    y = 118
    ft = _font(58, weight=820)
    for ln in _wrap(d, title, ft, width, 3):
        d.text((x, y), ln, font=ft, fill=WHITE, anchor="la")
        y += 66
    if duration:
        y = _pill(d, x, y + 12, duration, ACCENT, 24) + 22
    f = _font(29, weight=540)
    for text in bullets[:4]:
        wrapped = _wrap(d, text, f, width - 28, 2)
        if y + 40 * len(wrapped) > H - 70:
            break
        d.ellipse([x + 1, y + 13, x + 13, y + 25], fill=ACCENT)
        for ln in wrapped:
            d.text((x + 28, y), ln, font=f, fill=BODY, anchor="la")
            y += 40
        y += 8
    d.text((x, H - 38), FOOTER_SHORT, font=_font(18), fill=MUTED, anchor="ls")
    bx0, by0, bx1, by1 = x + width + 40, 60, W - 40, H - 60
    try:
        a = _fit(Image.open(poster), bx1 - bx0, by1 - by0)
        aw, ah = a.width / S, a.height / S
        px, py = bx1 - aw, (H - ah) / 2
        _paste(img, a, px, py)
        d.rounded_rectangle([px - 1, py - 1, px + aw + 1, py + ah + 1], radius=6, outline=T._mix(MUTED, BG, 0.4), width=2)
        cx, cy = px + aw / 2, py + ah / 2
    except (OSError, ValueError, AttributeError, TypeError):
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=18, fill=PANEL)
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    d.ellipse([cx - 58, cy - 58, cx + 58, cy + 58], fill=T._mix(ACCENT, BG, 0.1), outline=WHITE, width=3)
    d.polygon([(cx - 18, cy - 30), (cx - 18, cy + 30), (cx + 34, cy)], fill=WHITE)
    return img
