# -*- coding: utf-8 -*-
"""Разметка снимков в стиле анатомического атласа (версии 0.3–0.4).

Кость выделяется порогом Отсу, цвет кладётся на её пиксели, поэтому края зон совпадают с анатомией.
Позвоночник: уровни Th12–L5 по межпозвонковым щелям в профиле яркости вдоль оси, привязка к гребням
подвздошных костей, ось, найденные яркие объекты. Бедро: бедренная и тазовая кость и надёжные точечные
ориентиры: большой вертел, шейка с головкой, диафиз и его ось. Детальные зоны бедра на данных
версии 0.3 оказались ненадёжными и не рисуются.

С версии 0.4 к атласу строится карта зон для интерактивной страницы: PNG того же размера, где в красном
канале код зоны под указателем, в зелёном — пиксели её подсветки (код = номер зоны · STEP), и список зон
с пояснениями и словами для голосовых вопросов.
С версии 0.5 атлас рисуется слоями одного размера (рамка, снимок, зоны, артефакты, ось, подписи): страница
включает их по отдельности и даёт лупу, файл атласа — их наложение.

Палитра зон: тёмные шаги категориальной палитры навыка dataviz в фиксированном порядке, проверена
валидатором на тёмном фоне; каждая зона дополнительно подписана текстом.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from dxaqc import analyze as A

PAL = [(57, 135, 229), (217, 89, 38), (25, 158, 112), (201, 133, 0), (213, 81, 129), (0, 131, 0), (144, 133, 233)]
CRIT, GOOD, NEUTRAL, BG = (208, 59, 59), (12, 163, 12), (120, 120, 120), (18, 20, 24)
AXIS_CYAN = (120, 210, 245)
SCALE = 2
STEP = 20  # шаг кода зоны в карте: устойчив к округлению цвета в браузере, до 12 зон

_REG = [os.environ.get("DXAQC_FONT", ""), "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"]
_BOLD = [os.environ.get("DXAQC_FONT_BOLD", ""), "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"]
_fonts: dict = {}
INTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Inter.ttf")  # OFL, тот же шрифт, что на сайте
TEXT, SUBTEXT, MUTED = (236, 240, 245), (143, 154, 167), (111, 122, 134)
CHIP_BG, CHIP_LINE = (21, 25, 32), (48, 55, 66)


def font(size: int, bold: bool = False):
    key = (size, bold)
    if key not in _fonts:
        if os.path.exists(INTER):
            # базовая раскладка: raqm с вариативным шрифтом на мелких кеглях рвал слова («пояс ничный», «fem oris»)
            f = ImageFont.truetype(INTER, size, layout_engine=ImageFont.Layout.BASIC)
            try:  # оси вариативного Inter: оптический размер и насыщенность
                f.set_variation_by_axes([min(max(size, 14), 32), 600 if bold else 400])
            except (OSError, ValueError):
                pass
            _fonts[key] = f
        else:
            for p in (_BOLD if bold else _REG):
                if p and os.path.exists(p):
                    _fonts[key] = ImageFont.truetype(p, size)
                    break
            else:
                _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def _mix(a, b, t: float):
    """Цвет a, смешанный с b: t=0 — a, t=1 — b."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def otsu(a: np.ndarray) -> int:
    hist = np.bincount(np.clip(a, 0, 255).astype(np.uint8).ravel(), minlength=256).astype(float)
    p = hist / max(hist.sum(), 1)
    om = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    sb = (mu[-1] * om - mu) ** 2 / (om * (1 - om) + 1e-12)
    return int(np.nanargmax(sb))


def edges(m: np.ndarray) -> np.ndarray:
    inner = m.copy()
    inner[1:, :] &= m[:-1, :]
    inner[:-1, :] &= m[1:, :]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    return m & ~inner


def _num(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


# ------------------------------------------------------------------ карта зон

class HitMap:
    """Карта зон атласа: hit — где зона ловит указатель, paint — какие пиксели подсвечивать."""

    def __init__(self, W: int, H: int, mL: int, top: int):
        self.hit, self.paint = Image.new("L", (W, H), 0), Image.new("L", (W, H), 0)
        self.dh, self.dp = ImageDraw.Draw(self.hit), ImageDraw.Draw(self.paint)
        self.mL, self.top = mL, top
        self.regions: list[dict] = []

    def region(self, key, title, sub, color, text, words, status="info") -> int:
        rid = len(self.regions) + 1
        if rid * STEP > 255:
            return 0
        self.regions.append(dict(id=rid, key=key, title=title, sub=sub, color="#%02x%02x%02x" % tuple(color),
                                 text=text, words=words, status=status))
        return rid

    def _targets(self, layers):
        return {"hit": [(self.hit, self.dh)], "paint": [(self.paint, self.dp)]}.get(
            layers, [(self.hit, self.dh), (self.paint, self.dp)])

    def mask(self, rid, m, layers="both"):
        if not rid or not m.any():
            return
        h, w = m.shape
        mi = Image.fromarray(m.astype(np.uint8) * 255).resize((w * SCALE, h * SCALE), Image.NEAREST)
        box = (self.mL, self.top, self.mL + w * SCALE, self.top + h * SCALE)
        for im, _ in self._targets(layers):
            im.paste(rid * STEP, box, mi)

    def rect(self, rid, r, layers="both", pad=0):
        if rid:
            for _, d in self._targets(layers):
                d.rectangle([r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad], fill=rid * STEP)

    def disc(self, rid, x, y, r, layers="both"):
        if rid:
            for _, d in self._targets(layers):
                d.ellipse([x - r, y - r, x + r, y + r], fill=rid * STEP)

    def line(self, rid, pts, width, layers="both"):
        if rid:
            for _, d in self._targets(layers):
                d.line(pts, fill=rid * STEP, width=width)

    def image(self) -> Image.Image:
        return Image.merge("RGB", (self.hit, self.paint, Image.new("L", self.hit.size, 0)))


# слова про артефакты тоже ведут к итогу: если предмета на снимке нет, итог отвечает, что нарушений не найдено
VERDICT_WORDS = ["итог", "вердикт", "не так", "нарушен", "качеств", "проблем", "почему", "плох", "хорош", "годн",
                 "артефакт", "предмет", "металл"]
VIOLATION_SAY = {"axis_tilt": "наклон оси больше допуска", "coverage": "неполный охват снизу",
                 "artifact": "посторонний предмет в кадре"}


def _verdict_region(hm: HitMap, res: dict, hip: bool) -> int:
    q = res.get("quality_class")
    if hip:
        text = ("Качество бедра в этой версии не оценивается. Сервис уже находит бедренную и тазовую кость и ориентиры, "
                "а проверка ротации по малому вертелу и полей вокруг зоны интереса появится в следующих версиях.")
        return hm.region("verdict", "итог проверки", "не оценено", NEUTRAL, text, VERDICT_WORDS, "info")
    if q == 0:
        text = ("Итог: снимок качественный, нарушений не найдено. Наведите на зону или коснитесь её, "
                "чтобы узнать, что проверял сервис.")
        return hm.region("verdict", "итог проверки", "качественное", GOOD, text, VERDICT_WORDS, "ok")
    found = "; ".join(VIOLATION_SAY.get(v, v) for v in res.get("violations", []))
    text = f"Итог: есть нарушение — {found}. Подробности в зонах, отмеченных красным."
    return hm.region("verdict", "итог проверки", "нарушение", CRIT, text, VERDICT_WORDS, "bad")


# ------------------------------------------------------------------ оформление

def _chip(d, x_edge, ty, label, color, align, sub=None):
    """Лёгкая плашка подписи: тёмный фон, тонкая обводка, цветная точка зоны, светлый текст."""
    f, fs = font(14, True), font(11)
    tw = max(d.textlength(label, font=f), d.textlength(sub, font=fs) if sub else 0)
    pad_l, pad_r = 23, 11
    hgt = 24 + (14 if sub else 0)
    w_ = tw + pad_l + pad_r
    x = x_edge if align == "left" else x_edge - w_
    top = ty - 12
    rect = [x, top, x + w_, top + hgt]
    d.rounded_rectangle(rect, radius=7, fill=CHIP_BG, outline=CHIP_LINE, width=1)
    d.ellipse([x + 9, top + 8.5, x + 16, top + 15.5], fill=color)
    d.text((x + pad_l, top + 12), label, font=f, fill=TEXT, anchor="lm")
    if sub:
        d.text((x + pad_l, top + 27), sub, font=fs, fill=SUBTEXT, anchor="lm")
    return ((x + w_, ty) if align == "left" else (x, ty)), rect


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


def _callouts(d, items, x_edge, align, y_min, y_max, gap=42, hm: HitMap | None = None, sink: list | None = None):
    """items: ((x, y), подпись, цвет, подпись второй строки[, код зоны]). Колонка без наложений.
    sink — список, куда складываются выноски данными (якорь, излом, край плашки): по ним страница рисует подписи сама."""
    items = sorted(items, key=lambda it: it[0][1])
    ys, prev = [], y_min - gap
    for it in items:
        y = max(it[0][1], prev + gap)
        ys.append(y)
        prev = y
    over = prev - y_max
    if over > 0:
        ys = [max(y_min + i * gap, y - over) for i, y in enumerate(ys)]
    for it, y in zip(items, ys):
        (ax, ay), label, color, sub = it[:4]
        rid = it[4] if len(it) > 4 else 0
        # сначала выноска, потом плашка поверх: линия не заходит на текст
        f, fs = font(14, True), font(11)
        w_ = max(d.textlength(label, font=f), d.textlength(sub, font=fs) if sub else 0) + 34
        end = (x_edge + w_, y) if align == "left" else (x_edge - w_, y)
        knee = (end[0] + (16 if align == "left" else -16), y)  # излом у плашки
        line_col = _mix(color, BG, 0.3)
        if sink is not None:
            sink.append(dict(id=rid, label=label, sub=sub or "", color=_hex(color), align=align,
                             anchor=[round(ax, 1), round(ay, 1)], knee=[round(knee[0], 1), round(knee[1], 1)],
                             end=[round(end[0], 1), round(end[1], 1)]))
        d.line([(ax, ay), knee, end], fill=line_col, width=1, joint="curve")
        d.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], fill=BG)
        d.ellipse([ax - 3.5, ay - 3.5, ax + 3.5, ay + 3.5], fill=color)
        end, rect = _chip(d, x_edge, y, label, color, align, sub)
        if hm is not None:
            hm.line(rid, [(ax, ay), knee, end], 5, "paint")
            hm.disc(rid, ax, ay, 8)
            hm.rect(rid, rect, pad=2)


def _header(d, W, title, q):
    d.text((20, 25), title, font=font(15, True), fill=(221, 227, 234), anchor="lm")
    lab, col = {0: ("качественное", GOOD), 1: ("нарушение", CRIT)}.get(q, ("не оценено", NEUTRAL))
    fb = font(12, True)
    tw = d.textlength(lab, font=fb)
    rect = [W - tw - 46, 13, W - 16, 37]
    d.rounded_rectangle(rect, radius=12, fill=_mix(col, BG, 0.78), outline=_mix(col, BG, 0.45), width=1)
    d.ellipse([rect[0] + 10, 22, rect[0] + 16, 28], fill=_mix(col, (255, 255, 255), 0.25))
    d.text((rect[0] + 22, 25), lab, font=fb, fill=_mix(col, (255, 255, 255), 0.55), anchor="lm")
    return rect


def _legend(d, x0, y0, entries, note, width, hm: HitMap | None = None):
    """entries: (название, цвет[, код зоны])."""
    x, y = x0, y0
    f = font(12)
    for e in entries:
        name, col = e[:2]
        w_ = 32 + d.textlength(name, font=f)
        if x + w_ > width - 10:
            x, y = x0, y + 22
        d.ellipse([x, y + 2, x + 9, y + 11], fill=col)
        d.text((x + 15, y + 7), name, font=f, fill=(174, 183, 194), anchor="lm")
        if hm is not None and len(e) > 2:
            hm.rect(e[2], [x - 4, y - 4, x + w_ - 12, y + 18])
        x += w_
    d.text((x0, y + 31), note, font=font(11), fill=MUTED, anchor="lm")


def _base(a):
    """Увеличенный снимок — то же, что render.original: страница берёт слой снимка из original_png."""
    h, w = a.shape
    return Image.fromarray(a).convert("RGB").resize((w * SCALE, h * SCALE), Image.LANCZOS)


# порядок наложения; frame (фон, шапка, легенда) всегда внизу и не выключается
LAYER_ORDER = ["frame", "image", "zones", "artifacts", "axis", "labels"]


class Layers:
    """Слои атласа одного размера. Страница включает их по отдельности, файл атласа — их наложение по порядку."""

    def __init__(self, W: int, H: int, a: np.ndarray, box: tuple[int, int]):
        self.frame = Image.new("RGB", (W, H), BG)
        self.image, self.box = _base(a), box
        self.callouts: dict | None = None   # подписи данными для страницы, см. compose_clean
        self.rgba = {k: Image.new("RGBA", (W, H), (0, 0, 0, 0)) for k in LAYER_ORDER[2:]}
        self.draw = {"frame": ImageDraw.Draw(self.frame), **{k: ImageDraw.Draw(v) for k, v in self.rgba.items()}}

    def overlay(self, name: str, over: np.ndarray):
        h, w = over.shape[:2]
        self.rgba[name].alpha_composite(Image.fromarray(over, "RGBA").resize((w * SCALE, h * SCALE), Image.NEAREST), self.box)

    def compose(self) -> Image.Image:
        out = self.frame.convert("RGBA")
        out.paste(self.image.convert("RGBA"), self.box)
        for k in LAYER_ORDER[2:]:
            out.alpha_composite(self.rgba[k])
        return out.convert("RGB")

    def export(self) -> dict:
        """Рамка и непустые прозрачные слои; снимок сюда не входит, он уже лежит в original_png."""
        return {"frame": self.frame, **{k: im for k, im in self.rgba.items() if im.getbbox()}}


CLEAN_LAYERS = ("zones", "artifacts", "axis")


def compose_clean(out_dir: str, layers: dict) -> Image.Image:
    """Рисунок без впечатанного текста: фон, снимок, заливка зон, артефакты и ось. Подложка для компонента
    atlas-callouts, который рисует заголовок, выноски и легенду на странице по данным callouts.
    layers — {имя: {file, x, y}} из строки manifest (row.layers)."""
    size = Image.open(os.path.join(out_dir, layers["frame"]["file"])).size
    canvas = Image.new("RGBA", size, (*BG, 255))
    img = layers["image"]
    canvas.paste(Image.open(os.path.join(out_dir, img["file"])).convert("RGBA"), (int(img["x"]), int(img["y"])))
    for name in CLEAN_LAYERS:
        if name in layers:
            canvas.alpha_composite(Image.open(os.path.join(out_dir, layers[name]["file"])).convert("RGBA"))
    return canvas.convert("RGB")


def _thumb(a, over, size=220):
    im = Image.alpha_composite(Image.fromarray(a).convert("RGBA"), Image.fromarray(over, "RGBA")).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def _paint(over, m, col, alpha=105):
    over[m] = (*col, alpha)
    over[edges(m)] = (*col, 255)


# ------------------------------------------------------------------ позвоночник

LEVEL_RU = {"Th12": "двенадцатый грудной", "L1": "первый поясничный", "L2": "второй поясничный",
            "L3": "третий поясничный", "L4": "четвёртый поясничный", "L5": "пятый поясничный"}
LEVEL_ORDER = ["Th12", "L1", "L2", "L3", "L4", "L5"]
LEVEL_WORDS = {"Th12": ["th12", "двенадцат", "грудн"], "L1": ["l1", "перв"], "L2": ["l2", "втор"],
               "L3": ["l3", "трет"], "L4": ["l4", "четверт"], "L5": ["l5", "пят"]}
ILIAC_COLOR = PAL[6]


def _level_text(n: str) -> str:
    approx = "Уровень найден по межпозвонковым щелям приблизительно."
    if n == "Th12":
        return ("Двенадцатый грудной позвонок, Th12. По ТЗ верхняя граница снимка должна проходить через середину Th12. "
                f"{approx} Эту границу версия пока не проверяет.")
    if n == "L5":
        return ("Пятый поясничный позвонок, L5. Он лежит на уровне гребней подвздошных костей и в расчёт плотности "
                f"обычно не входит, но по нему видно, что снимок захватил низ поясничного отдела. {approx}")
    return (f"{LEVEL_RU[n].capitalize()} позвонок, {n}. Позвонки L1–L4 — зона, по которой денситометр считает "
            f"минеральную плотность кости, поэтому они должны целиком попасть в кадр. {approx}")


def spine_parts(a: np.ndarray) -> dict:
    h, w = a.shape
    af = a.astype(np.float32)
    b = A._blur(af, 7)
    ys, xs = A._spine_centerline(b)
    yy = np.arange(h)
    xc = np.interp(yy, ys, xs)
    prof = np.array([b[y, max(0, int(xc[y]) - 16): int(xc[y]) + 17].mean() for y in yy])
    ps = np.convolve(prof, np.ones(7) / 7, mode="same")

    mins: list[int] = []
    for y in range(12, h - 12):
        win = ps[max(0, y - 13): y + 14]
        if ps[y] == win.min() and ps[y] < np.median(ps[max(0, y - 28): y + 29]) - 3:
            if not mins or y - mins[-1] >= 24:
                mins.append(y)
            elif ps[y] < ps[mins[-1]]:
                mins[-1] = y
    if len(mins) >= 2:  # пропущенные щели: слишком высокие промежутки делим поровну
        med = float(np.median(np.diff(mins)))
        fixed = [mins[0]]
        for m in mins[1:]:
            gap = m - fixed[-1]
            parts = int(round(gap / med)) if med > 0 else 1
            start = fixed[-1]
            for j in range(1, parts):
                fixed.append(int(start + gap * j / parts))
            fixed.append(m)
        mins = sorted(set(fixed))

    bb = A._blur(af, 9)
    thr = max(otsu(bb), 25)
    mask = bb > thr * 0.9
    cw = int(w * 0.28)
    crest_pts = []
    for sl in (slice(0, cw), slice(w - cw, w)):
        rows = np.where(mask[int(h * 0.5):, sl].mean(1) > 0.18)[0]
        if len(rows):
            y = int(h * 0.5) + int(rows.min())
            xs_ = np.nonzero(mask[y, sl])[0]
            crest_pts.append((sl.start + int(np.median(xs_)), y))
    crest_y = min(p[1] for p in crest_pts) if crest_pts else None

    levels = []
    if mins:
        k = len(mins) - 1
        if crest_y is not None:
            j = int(np.argmin([abs(m - crest_y) for m in mins]))
            if abs(mins[j] - crest_y) <= 45:
                k = j
        names_up = ["L4", "L3", "L2", "L1", "Th12"]
        bounds = [0] + mins + [h]
        for i in range(len(bounds) - 1):
            y0, y1 = bounds[i], bounds[i + 1]
            if i == k + 1:
                name = "L5"
            elif i <= k and (k - i) < len(names_up):
                name = names_up[k - i]
            else:
                name = None
            if name and y1 - y0 >= 14:
                levels.append((name, y0, y1))
    band = np.abs(np.arange(w)[None, :] - xc[:, None]) < w * 0.15
    return dict(xc=xc, levels=levels, crest_pts=crest_pts, mask=mask, band=band, cw=cw)


def render_spine(a: np.ndarray, res: dict):
    h, w = a.shape
    P = spine_parts(a)
    S, mL, mR, top, bot = SCALE, 200, 220, 50, 92
    W, H = w * S + mL + mR, h * S + top + bot
    g, met = res["geometry"], res["metrics"]
    ok = g["axis_ok"]
    ang = met["angle_deg"]
    iliac_ok = g.get("iliac_ok", [True, True])
    lim = res.get("limits") or {}
    axis_lim = lim.get("axis_limit_deg", 5.0)
    iliac_lim = lim.get("iliac_min_brightness", 4.0)
    X = lambda x: mL + x * S
    Y = lambda y: top + y * S

    hm = HitMap(W, H, mL, top)
    r_verdict = _verdict_region(hm, res, hip=False)
    lvl_ids = {}
    for name, _, _ in P["levels"]:
        lvl_ids[name] = hm.region(name, name, f"{LEVEL_RU[name]} позвонок", PAL[LEVEL_ORDER.index(name)],
                                  _level_text(name), LEVEL_WORDS[name])
    if all(iliac_ok):
        il_text = (f"Гребни подвздошных костей — нижняя граница охвата по ТЗ. В нижних углах кадра кость видна: яркость "
                   f"слева {_num(met['iliac_left'])}, справа {_num(met['iliac_right'])} при пороге {_num(iliac_lim)}. Охват снизу в норме.")
    else:
        miss = " и ".join(s for s, k in zip(("слева", "справа"), iliac_ok) if not k)
        il_text = (f"Гребни подвздошных костей — нижняя граница охвата по ТЗ. В нижнем углу кадра {miss} кость не видна: "
                   f"яркость слева {_num(met['iliac_left'])}, справа {_num(met['iliac_right'])} при пороге {_num(iliac_lim)}. "
                   f"Снимок обрезан снизу, это нарушение охвата.")
    r_iliac = hm.region("iliac", "гребни подвздошных костей", "нижняя граница охвата", ILIAC_COLOR if all(iliac_ok) else CRIT,
                        il_text, ["подвздош", "гребн", "гребен", "таз", "охват", "нижн", "обрез"],
                        "ok" if all(iliac_ok) else "bad")
    ax_text = (f"Ось позвоночного столба проведена через центры позвонков в верхней и нижней трети снимка. Наклон "
               f"{_num(abs(ang))}° при допуске {_num(axis_lim)}°: " +
               ("укладка ровная." if ok else "это нарушение, пациента нужно уложить ровнее и переснять."))
    r_axis = hm.region("axis", "ось позвоночного столба", f"наклон {_num(abs(ang))}°, допуск {_num(axis_lim)}°", GOOD if ok else CRIT,
                       ax_text, ["ось", "оси", "осью", "наклон", "угол", "угл", "ровн", "криво", "сколиоз", "уклад"],
                       "ok" if ok else "bad")
    r_art = 0
    if g.get("artifact_boxes"):
        art_text = (f"Посторонний предмет: {met.get('bright_px', 0)} очень ярких пикселей вне позвоночного столба. "
                    f"Металл, пуговицы и украшения искажают плотность, снимок стоит переснять без них.")
        r_art = hm.region("artifact", "посторонний предмет", "яркий объект вне столба", CRIT, art_text,
                          ["предмет", "артефакт", "металл", "ярк", "пуговиц", "украш"], "bad")

    over = np.zeros((h, w, 4), np.uint8)
    colors = {}
    ax_pts = [(X(g["axis"][0][0]), Y(0)), (X(g["axis"][1][0]), Y(h - 1))]
    hm.line(r_axis, ax_pts, 12, "hit")
    hm.line(r_axis, ax_pts, 6, "paint")
    for sl in (slice(0, P["cw"]), slice(w - P["cw"], w)):
        m = np.zeros((h, w), bool)
        m[int(h * 0.5):, sl] = True
        _paint(over, m & P["mask"], ILIAC_COLOR, 95)
        hm.mask(r_iliac, m, "hit")
        hm.mask(r_iliac, m & P["mask"], "paint")
    for name, y0, y1 in P["levels"]:
        col = PAL[LEVEL_ORDER.index(name)]
        colors[name] = col
        m = np.zeros((h, w), bool)
        m[y0 + 2:y1 - 1] = True
        _paint(over, m & P["mask"] & P["band"], col, 110)
        hm.mask(lvl_ids[name], m & P["band"], "hit")
        hm.mask(lvl_ids[name], m & P["mask"] & P["band"], "paint")
    over_art = np.zeros_like(over)
    for bx in g.get("artifact_boxes", []):
        over_art[bx[1]:bx[3], bx[0]:bx[2]][edges(np.ones((bx[3] - bx[1], bx[2] - bx[0]), bool))] = (*CRIT, 255)
        hm.rect(r_art, [X(bx[0]), Y(bx[1]), X(bx[2]), Y(bx[3])], pad=6)

    L = Layers(W, H, a, (mL, top))
    L.overlay("zones", over)
    L.overlay("artifacts", over_art)
    d, da = L.draw["labels"], L.draw["axis"]
    calls: list[dict] = []
    da.line(ax_pts, fill=GOOD if ok else CRIT, width=3)
    for x, y in g["centerline"]:
        da.ellipse([X(x) - 2, Y(y) - 2, X(x) + 2, Y(y) + 2], fill=(235, 240, 255))

    left = [((X(P["xc"][int((y0 + y1) / 2)] - w * 0.13), Y((y0 + y1) / 2)), n, colors[n], LEVEL_RU[n], lvl_ids[n])
            for n, y0, y1 in P["levels"]]
    _callouts(d, left, 16, "left", top + 14, top + h * S - 10, hm=hm, sink=calls)

    right = []
    ya = h * 0.35
    xa = g["axis"][0][0] + (g["axis"][1][0] - g["axis"][0][0]) * ya / h
    axis_sub = "допуск 5° по ТЗ" if axis_lim == 5.0 else f"допуск {axis_lim:g}°, в ТЗ 5°"
    right.append(((X(xa), Y(ya)), f"ось столба {abs(ang):.1f}°", GOOD if ok else CRIT, axis_sub, r_axis))
    if P["crest_pts"]:
        for i, (px, py) in enumerate(sorted(P["crest_pts"], key=lambda p: -p[0])):
            if i == 0:
                right.append(((X(px), Y(py)), "гребни подвздошных костей", ILIAC_COLOR, "нижняя граница охвата", r_iliac))
            else:
                d.ellipse([X(px) - 5, Y(py) - 5, X(px) + 5, Y(py) + 5], fill=BG)
                d.ellipse([X(px) - 3.5, Y(py) - 3.5, X(px) + 3.5, Y(py) + 3.5], fill=ILIAC_COLOR)
                hm.disc(r_iliac, X(px), Y(py), 8)
    else:
        right.append(((X(w - P["cw"] / 2), Y(h - 8)), "гребни не видны", CRIT, "охват снизу недостаточен", r_iliac))
    for bx in g.get("artifact_boxes", []):
        L.draw["artifacts"].rectangle([X(bx[0]), Y(bx[1]), X(bx[2]), Y(bx[3])], outline=CRIT, width=3)
        right.append(((X(bx[2]), Y((bx[1] + bx[3]) / 2)), "посторонний предмет", CRIT, "яркий объект вне столба", r_art))
    _callouts(d, right, W - 16, "right", top + 14, top + h * S - 10, hm=hm, sink=calls)

    d.text((mL + 8, top + 6), "П", font=font(16, True), fill=(250, 210, 90))
    d.text((mL + w * S - 22, top + 6), "Л", font=font(16, True), fill=(250, 210, 90))
    hm.rect(r_verdict, _header(L.draw["frame"], W, "Поясничный отдел позвоночника · прямая проекция", res["quality_class"]), pad=3)
    ent = [(n, colors[n], lvl_ids[n]) for n in LEVEL_ORDER if n in colors] + [("подвздошные кости", ILIAC_COLOR, r_iliac)]
    _legend(L.draw["frame"], 20, top + h * S + 16, ent,
            "Уровни позвонков найдены по межпозвонковым щелям приблизительно · П и Л — стороны пациента", W, hm=hm)
    info = dict(levels=[n for n, _, _ in P["levels"]], crests=len(P["crest_pts"]))
    L.callouts = dict(size=[W, H], image_box=[mL, top, w * S, h * S], title="Поясничный отдел позвоночника · прямая проекция",
                      items=calls, marks=[dict(text="П", x=mL + 14, y=top + 16), dict(text="Л", x=mL + w * S - 14, y=top + 16)],
                      legend=[dict(label=e[0], color=_hex(e[1])) for e in ent],
                      note="Уровни позвонков найдены по межпозвонковым щелям приблизительно · П и Л — стороны пациента")
    th = over.copy()
    th[over_art[..., 3] > 0] = over_art[over_art[..., 3] > 0]
    return L, _thumb(a, th), info, hm


# ------------------------------------------------------------------ бедро

FEMUR_COLOR, PELVIS_COLOR = PAL[0], PAL[1]


def hip_parts(a: np.ndarray, region: str) -> dict | None:
    h, w = a.shape
    af = a.astype(np.float32)
    bb = A._blur(af, 5)
    thr = max(otsu(bb), 25)
    mask = bb > thr
    fmask = bb > max(thr * 0.6, 20)
    med = 1 if region == "hip_right" else -1
    col = A._blur(af, 9)[int(h * 0.72):].mean(0)
    c = int(np.argmax(np.convolve(col, np.ones(25) / 25, mode="same")))

    L = np.full(h, -1)
    R = np.full(h, -1)
    y = h - 3
    while y > int(h * 0.04):
        row = fmask[y]
        if not row[c]:
            near = [x for x in range(max(0, c - 14), min(w, c + 15)) if row[x]]
            if not near:
                break
            c = near[len(near) // 2]
        l = c
        while l > 0 and row[l - 1]:
            l -= 1
        r = c
        while r < w - 1 and row[r + 1]:
            r += 1
        if y + 1 < h and L[y + 1] >= 0:  # медиальный край не убегает в таз быстрее 1.3 px на строку
            if med == 1 and r > R[y + 1] + 2:
                r = int(R[y + 1] + 1.3)
            if med == -1 and l < L[y + 1] - 2:
                l = int(L[y + 1] - 1.3)
        if r - l < 6:
            break
        L[y], R[y] = l, r
        c = (l + r) // 2
        y -= 1

    rows = np.where(L >= 0)[0]
    if len(rows) < h * 0.3:
        return None
    lat = L if med == 1 else R
    medl = R if med == 1 else L
    upper = rows[rows < h * 0.7]
    if len(upper):
        gt_y = int(upper[np.argmin(lat[upper] * med)])
        cut = max(gt_y - int(h * 0.16), 0)
        L[:cut] = -1
        R[:cut] = -1
        rows = np.where(L >= 0)[0]
    else:
        gt_y = int(rows.min())
    ytop = int(rows.min())
    fem = np.zeros((h, w), bool)
    for yy in rows:
        fem[yy, L[yy]:R[yy] + 1] = True
    shaft_rows = rows[rows > h * 0.72]
    shaft_c = float(np.median((L[shaft_rows] + R[shaft_rows]) / 2)) if len(shaft_rows) else w / 2
    shaft_half = float(np.median((R[shaft_rows] - L[shaft_rows]) / 2)) if len(shaft_rows) else w * 0.1
    Xg = np.arange(w)[None, :]
    pel = mask & ~fem & ((Xg - shaft_c) * med > shaft_half)
    neck_y = min(ytop + 4, h - 1)
    pel_yx = np.argwhere(pel)
    return dict(
        femur=fem, pelvis=pel, med=med,
        gt=(int(lat[gt_y]), gt_y),
        neck=(int(medl[neck_y]), neck_y),
        shaft=(shaft_c, float(h * 0.86)),
        shaft_line=((shaft_c, h * 0.55), (shaft_c, h - 2)),
        pelvis_pt=(float(pel_yx[:, 1].mean()), float(pel_yx[:, 0].mean())) if len(pel_yx) > 30 else None,
    )


def render_hip(a: np.ndarray, res: dict):
    h, w = a.shape
    region = res["region"]
    P = hip_parts(a, region)
    if P is None:
        return None
    S, mL, mR, top, bot = SCALE, 230, 230, 50, 92
    W, H = w * S + mL + mR, h * S + top + bot
    X = lambda x: mL + x * S
    Y = lambda y: top + y * S
    has_pelvis = P["pelvis"].sum() > 30

    hm = HitMap(W, H, mL, top)
    r_verdict = _verdict_region(hm, res, hip=True)
    r_fem = hm.region("femur", "бедренная кость", "os femoris, проксимальный отдел", FEMUR_COLOR,
                      "Бедренная кость, проксимальный отдел, выделена по яркости. При денситометрии бедра плотность считают "
                      "в шейке и во всей проксимальной части, поэтому бедро укладывают выпрямленным и слегка развёрнутым внутрь.",
                      ["бедрен", "бедро", "кость бедр"])
    r_pel = hm.region("pelvis", "тазовая кость", "os coxae, вертлужная впадина", PELVIS_COLOR,
                      "Тазовая кость с вертлужной впадиной, в которой лежит головка бедра. По ТЗ на снимке бедра должна быть "
                      "видна седалищная кость: это граница поля вокруг зоны интереса.",
                      ["таз", "вертлуж", "седалищ"]) if has_pelvis else 0
    r_shaft = hm.region("shaft", "диафиз и его ось", "corpus femoris", AXIS_CYAN,
                        "Диафиз бедренной кости и его ось. Ось должна идти параллельно краю кадра, это признак того, что бедро "
                        "выпрямлено. В этой версии качество бедра не оценивается, линия показана как ориентир.",
                        ["диафиз", "ось", "оси", "осью", "стержн", "тело бедр"])
    r_gt = hm.region("gt", "большой вертел", "trochanter major", PAL[2],
                     "Большой вертел, выступ на наружной стороне бедра. По ТЗ он должен полностью попадать в кадр, "
                     "по нему сервис строит нижнюю часть зоны интереса. Точка найдена приблизительно.",
                     ["вертел"])
    r_neck = hm.region("neck", "шейка и головка бедра", "collum et caput femoris", FEMUR_COLOR,
                       "Шейка и головка бедра. Шейка — главная зона измерения плотности при диагностике остеопороза. "
                       "Правильная внутренняя ротация открывает шейку, а ротацию по ТЗ оценивают по малому вертелу: "
                       "при хорошей укладке он почти не виден. Точка найдена приблизительно.",
                       ["шейк", "шее", "шей", "головк", "голов"])

    over = np.zeros((h, w, 4), np.uint8)
    _paint(over, P["femur"], FEMUR_COLOR, 100)
    hm.mask(r_fem, P["femur"])
    if has_pelvis:
        _paint(over, P["pelvis"], PELVIS_COLOR, 100)
        hm.mask(r_pel, P["pelvis"])

    L = Layers(W, H, a, (mL, top))
    L.overlay("zones", over)
    d = L.draw["labels"]
    calls: list[dict] = []
    (sx0, sy0), (sx1, sy1) = P["shaft_line"]
    sh_pts = [(X(sx0), Y(sy0)), (X(sx1), Y(sy1))]
    L.draw["axis"].line(sh_pts, fill=AXIS_CYAN, width=3)
    hm.line(r_shaft, sh_pts, 14, "hit")
    hm.line(r_shaft, sh_pts, 6, "paint")
    for rid, (px, py) in ((r_gt, P["gt"]), (r_neck, P["neck"])):
        hm.disc(rid, X(px), Y(py), 18, "hit")
        hm.disc(rid, X(px), Y(py), 11, "paint")

    med_right = P["med"] == 1
    lat_items = [((X(P["gt"][0]), Y(P["gt"][1])), "большой вертел", PAL[2], "trochanter major", r_gt),
                 ((X(P["shaft"][0]), Y(P["shaft"][1])), "диафиз и его ось", AXIS_CYAN, "corpus femoris", r_shaft)]
    med_items = [((X(P["neck"][0]), Y(P["neck"][1])), "шейка и головка бедра", FEMUR_COLOR, "collum et caput femoris", r_neck)]
    if P["pelvis_pt"]:
        med_items.append(((X(P["pelvis_pt"][0]), Y(P["pelvis_pt"][1])), "тазовая кость", PELVIS_COLOR,
                          "os coxae, вертлужная впадина", r_pel))
    _callouts(d, med_items, W - 16 if med_right else 16, "right" if med_right else "left", top + 14, top + h * S - 10, hm=hm, sink=calls)
    _callouts(d, lat_items, 16 if med_right else W - 16, "left" if med_right else "right", top + 14, top + h * S - 10, hm=hm, sink=calls)

    side = "Правое бедро" if region == "hip_right" else "Левое бедро"
    hm.rect(r_verdict, _header(L.draw["frame"], W, f"{side} · проксимальный отдел · прямая проекция", res["quality_class"]), pad=3)
    lat_t, med_t = "латерально", "медиально"
    ft = font(13, True)
    d.text((mL + 8, top + 6), lat_t if med_right else med_t, font=ft, fill=(250, 210, 90))
    t = med_t if med_right else lat_t
    d.text((mL + w * S - 8 - d.textlength(t, font=ft), top + 6), t, font=ft, fill=(250, 210, 90))
    _legend(L.draw["frame"], 20, top + h * S + 16,
            [("бедренная кость", FEMUR_COLOR, r_fem), ("тазовая кость", PELVIS_COLOR, r_pel), ("ось диафиза", AXIS_CYAN, r_shaft)],
            "Кости выделены по яркости, ориентиры приблизительные · качество бедра в этой версии не оценивается", W, hm=hm)
    L.callouts = dict(size=[W, H], image_box=[mL, top, w * S, h * S], title=f"{side} · проксимальный отдел · прямая проекция",
                      items=calls, marks=[dict(text=lat_t if med_right else med_t, x=mL + 14, y=top + 16, align="left"),
                                          dict(text=t, x=mL + w * S - 14, y=top + 16, align="right")],
                      legend=[dict(label="бедренная кость", color=_hex(FEMUR_COLOR)), dict(label="тазовая кость", color=_hex(PELVIS_COLOR)),
                              dict(label="ось диафиза", color=_hex(AXIS_CYAN))],
                      note="Кости выделены по яркости, ориентиры приблизительные · качество бедра в этой версии не оценивается")
    return L, _thumb(a, over), dict(gt=P["gt"], neck=P["neck"]), hm


def render(pixels: np.ndarray, res: dict):
    """Атлас, цветная миниатюра, карта зон и пояснения к зонам; None, если для области атлас не строится."""
    region = res.get("region")
    if region == "lumbar_spine":
        out = render_spine(pixels, res)
    elif region in ("hip_right", "hip_left"):
        out = render_hip(pixels, res)
    else:
        return None
    if out is None:
        return None
    layers, thumb, info, hm = out
    return dict(atlas=layers.compose(), thumb=thumb, info=info, hit=hm.image(), regions=hm.regions,
                layers=layers.export(), image_box=layers.box, callouts=layers.callouts)
