# -*- coding: utf-8 -*-
"""Анализ одного снимка DXA, версия 0.1: правила без обученной модели.

Калибровка на обучающем наборе (99 исследований позвоночника, метки на уровне исследования):
- область по ширине кадра GE Lunar Prodigy: 300 px позвоночник, 280 px бедро — совпало во всех исследованиях;
- сторона бедра по массе таза относительно диафиза — обе стороны найдены в 72 из 72 исследований;
- ось: угол хорды центра столба между верхней и нижней третью, AUC 0.75 против метки оси;
- охват снизу по подвздошным костям в нижних углах, AUC 0.86 против метки укладки;
- посторонние предметы: яркие пиксели вне столба, AUC 0.62 — слабый признак.

Пороги задаются параметрами (dxaqc/params.py); константы ниже — значения по умолчанию.
Контракт результата analyze(): см. docstring функции.
"""
from __future__ import annotations

import numpy as np

from dxaqc import params as P

AXIS_LIMIT_DEG = P.DEFAULTS["axis_limit_deg"]
ILIAC_MIN_BRIGHTNESS = P.DEFAULTS["iliac_min_brightness"]
SPINE_BAND_HALF = P.DEFAULTS["spine_band_half"]


def _blur(a: np.ndarray, k: int) -> np.ndarray:
    p = k // 2
    c = np.pad(a, p, mode="edge").cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def _running_median(x: np.ndarray, win: int = 9) -> np.ndarray:
    h = win // 2
    return np.array([np.median(x[max(0, i - h):i + h + 1]) for i in range(len(x))])


def detect_region(a: np.ndarray) -> tuple[str, str]:
    h, w = a.shape
    if w == 300:
        region, basis = "lumbar_spine", "ширина кадра 300 px, протокол позвоночника GE Lunar"
    elif w == 280:
        region, basis = "hip", "ширина кадра 280 px, протокол бедра GE Lunar"
    else:
        third = w // 3
        centre = a[:, third:2 * third].mean()
        sides = (a[:, :third].mean() + a[:, 2 * third:].mean()) / 2
        mirror = np.corrcoef(a.ravel(), a[:, ::-1].ravel())[0, 1]
        if centre > 1.6 * max(sides, 1) and mirror > 0.6:
            region, basis = "lumbar_spine", f"нестандартная ширина {w} px, симметричный яркий столб по центру"
        else:
            region, basis = "hip", f"нестандартная ширина {w} px, асимметричное изображение"
    if region == "hip":
        side, why = hip_side(a)
        return side, basis + "; " + why
    return region, basis


def hip_side(a: np.ndarray) -> tuple[str, str]:
    h, w = a.shape
    b = _blur(a.astype(np.float32), 9)
    col = b[int(h * 0.72):].mean(0)
    shaft = int(np.argmax(np.convolve(col, np.ones(25) / 25, mode="same")))
    up = b[: int(h * 0.5)]
    left, right = float(up[:, :shaft].sum()), float(up[:, shaft:].sum())
    if right > left:
        return "hip_right", "таз и головка справа от диафиза на изображении"
    return "hip_left", "таз и головка слева от диафиза на изображении"


def _spine_centerline(b: np.ndarray):
    h, w = b.shape
    ys = np.arange(int(h * 0.10), int(h * 0.90), 2)
    kern = np.ones(56) / 56
    lo, hi = int(w * 0.22), int(w * 0.78)
    xs = []
    for y in ys:
        row = b[max(0, y - 6): y + 7].mean(0)
        conv = np.convolve(row, kern, mode="same")
        xs.append(lo + int(np.argmax(conv[lo:hi])))
    return ys, _running_median(np.array(xs, float), 9)


def _grid_boxes(mask: np.ndarray, cell: int = 12, min_px: int = 6):
    h, w = mask.shape
    gh, gw = (h + cell - 1) // cell, (w + cell - 1) // cell
    grid = np.zeros((gh, gw), bool)
    for gy in range(gh):
        for gx in range(gw):
            if mask[gy * cell:(gy + 1) * cell, gx * cell:(gx + 1) * cell].sum() >= min_px:
                grid[gy, gx] = True
    seen, boxes = np.zeros_like(grid), []
    for gy in range(gh):
        for gx in range(gw):
            if not grid[gy, gx] or seen[gy, gx]:
                continue
            stack, cells = [(gy, gx)], []
            seen[gy, gx] = True
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            ys_, xs_ = [c[0] for c in cells], [c[1] for c in cells]
            boxes.append([min(xs_) * cell, min(ys_) * cell, min(w, (max(xs_) + 1) * cell), min(h, (max(ys_) + 1) * cell)])
    return boxes


def _rib_like(boxes: list, axis_x: np.ndarray, h: int) -> list[int]:
    """Номера пятен, похожих на рёбра: крупные, в верхней трети кадра, по обе стороны от оси на сходном расстоянии."""
    big = [(i, (b[0] + b[2]) / 2 - axis_x[min(h - 1, (b[1] + b[3]) // 2)]) for i, b in enumerate(boxes)
           if b[3] <= h * 0.35 and b[2] - b[0] >= 48]
    left = [(i, -o) for i, o in big if o < 0]
    right = [(i, o) for i, o in big if o > 0]
    if not left or not right:
        return []
    l, r = max(left, key=lambda t: t[1]), max(right, key=lambda t: t[1])
    return sorted([l[0], r[0]]) if abs(l[1] - r[1]) < 0.25 * max(l[1], r[1]) else []


def analyze_spine(a: np.ndarray, params: dict | None = None) -> dict:
    p = P.normalize(params)
    axis_limit, iliac_min = p["axis_limit_deg"], p["iliac_min_brightness"]
    h, w = a.shape
    af = a.astype(np.float32)
    b = _blur(af, 7)
    ys, xs = _spine_centerline(b)

    t = len(ys) // 3
    y_top, y_bot = float(np.median(ys[:t])), float(np.median(ys[-t:]))
    x_top, x_bot = float(np.median(xs[:t])), float(np.median(xs[-t:]))
    angle = float(np.degrees(np.arctan((x_bot - x_top) / max(y_bot - y_top, 1.0))))

    # продлеваем хорду на всю высоту для рисования и полосы столба
    slope = (x_bot - x_top) / max(y_bot - y_top, 1.0)
    axis_x = x_top + slope * (np.arange(h) - y_top)

    bb = _blur(af, 9)
    corner_h, corner_w = int(h * 0.18), int(w * 0.28)
    left_box = [0, h - corner_h, corner_w, h]
    right_box = [w - corner_w, h - corner_h, w, h]
    bl = float(bb[h - corner_h:, :corner_w].mean())
    br = float(bb[h - corner_h:, w - corner_w:].mean())

    out_band = np.abs(np.arange(w)[None, :] - axis_x[:, None]) > p["spine_band_half"]
    # посторонний предмет — пятно, заметно ярче своего окружения, а не просто очень яркий пиксель: на этих снимках
    # пуговицы и застёжки не белые, а резко светлее фона вокруг (ROC-AUC 0,85 против 0,55 у порога яркости 240)
    local = af - _blur(af, 21)
    contrast = float(np.percentile(local[out_band], 99.9)) if out_band.any() else 0.0
    spot = (local > p["artifact_contrast"]) & out_band
    art_boxes = _grid_boxes(spot) if contrast >= p["artifact_contrast"] else []
    # 29.09, Алексей: на «Для теста» за предмет приняты симметричные пятна вверху кадра — похоже на XII рёбра.
    # Вердикт не меняем: на 99 размеченных поясницах такой узор у 3 снимков, у 2 из них эксперты отметили
    # предмет (скорее всего бюстгальтер — он на том же уровне), а исключение верхней зоны роняет ROC-AUC с 0,85
    # до 0,53–0,74. Но в пояснении и на выноске честно пишем, что это могут быть рёбра.
    doubt = _rib_like(art_boxes, axis_x, h)

    violations, expl = [], []
    if abs(angle) > axis_limit:
        violations.append("axis_tilt")
        expl.append(f"Ось столба отклонена на {abs(angle):.1f}° при допуске {axis_limit:g}°: центр столба в нижней трети "
                    f"смещён на {abs(x_bot - x_top):.0f} px относительно верхней.")
    else:
        expl.append(f"Ось столба отклонена на {abs(angle):.1f}°, это в пределах допуска {axis_limit:g}°.")

    iliac_ok = [bl >= iliac_min, br >= iliac_min]
    if not all(iliac_ok):
        violations.append("coverage")
        miss = " и ".join(s for s, ok in zip(("слева", "справа"), iliac_ok) if not ok)
        expl.append(f"В нижних углах кадра не видно подвздошных костей {miss}: нижняя граница сканирования, "
                    f"вероятно, выше гребней подвздошных костей.")
    else:
        expl.append("Верхние края подвздошных костей видны в обоих нижних углах кадра.")
    expl.append("Уровень Th12 в верхней границе кадра пока не проверяется.")

    if art_boxes:
        violations.append("artifact")
        expl.append(f"Вне позвоночного столба есть пятно, заметно ярче своего окружения (контраст {contrast:.0f} "
                    f"при пороге {p['artifact_contrast']:g}), в {len(art_boxes)} областях: похоже на посторонний предмет.")
        if doubt:
            expl.append("Два крупных пятна в верхней части кадра лежат симметрично по обе стороны от позвоночника. "
                        "Так выглядят и косточки или застёжка бюстгальтера, и нижние (XII) рёбра — проверьте снимок "
                        "глазами. В обучающем наборе эксперты в 2 из 3 таких случаев отметили посторонний предмет.")
    else:
        expl.append(f"Пятен, заметно ярче окружения, вне позвоночного столба не найдено (контраст {contrast:.0f} "
                    f"при пороге {p['artifact_contrast']:g}).")

    return dict(
        quality_class=1 if violations else 0,
        violations=violations,
        explanations=expl,
        metrics=dict(angle_deg=round(angle, 2), abs_angle=round(abs(angle), 2), iliac_left=round(bl, 2),
                     iliac_right=round(br, 2), artifact_contrast=round(contrast, 1)),
        measurements={
            "угол оси, °": f"{angle:+.1f}",
            "допуск оси, °": f"±{axis_limit:g}",
            "подвздошные кости слева / справа": f"{bl:.1f} / {br:.1f}",
            "контраст пятна вне столба": f"{contrast:.0f} (порог {p['artifact_contrast']:g})",
        },
        limits=dict(axis_limit_deg=axis_limit, iliac_min_brightness=iliac_min, artifact_contrast=p["artifact_contrast"]),
        geometry=dict(
            centerline=[[float(x), float(y)] for x, y in zip(xs[::3], ys[::3])],
            axis=[[float(axis_x[0]), 0.0], [float(axis_x[-1]), float(h - 1)]],
            axis_ok=abs(angle) <= axis_limit,
            thirds=[[x_top, y_top], [x_bot, y_bot]],
            iliac_boxes=[left_box, right_box],
            iliac_ok=iliac_ok,
            artifact_boxes=art_boxes,
            artifact_doubt=doubt,
        ),
    )


def analyze_hip(a: np.ndarray, region: str) -> dict:
    h, w = a.shape
    b = _blur(a.astype(np.float32), 9)
    col = b[int(h * 0.72):].mean(0)
    shaft = int(np.argmax(np.convolve(col, np.ones(25) / 25, mode="same")))
    side_ru = "правое" if region == "hip_right" else "левое"
    where = (f"Определено {side_ru} бедро: таз и головка лежат по {'правую' if region == 'hip_right' else 'левую'} "
             f"сторону от диафиза на изображении.")
    from dxaqc import hipmodel
    m = hipmodel.predict(a, region)
    measurements = {"центр диафиза, px": str(shaft), "ширина кадра, px": str(w)}
    if m is None:                                        # весов нет — поведение версии 0.5
        return dict(quality_class=None, violations=["hip_not_evaluated_v0"],
                    explanations=[where, "Модель качества бедра не найдена, снимок не оценён."],
                    measurements=measurements, metrics=dict(shaft_x=shaft), geometry=dict(shaft_x=shaft))
    p, t = m["prob"], m["thresholds"]
    expl = [where]
    if m["quality_class"]:
        what = {"hip_positioning": "укладка или ротация бедра", "hip_roi": "поля вокруг зоны интереса"}
        expl.append(f"Обученная модель считает снимок бракованным: вероятность брака {p['bad']:.2f} при пороге {t['bad']:.2f}; "
                    f"вероятнее всего — {', '.join(what[v] for v in m['violations'])}.")
    else:
        expl.append(f"Обученная модель считает снимок годным: вероятность брака {p['bad']:.2f} при пороге {t['bad']:.2f}.")
    expl.append("Модель бедра — ExtraTrees по 47 признакам формы кости, краёв кадра и ориентиров; обучена на 150 снимках, "
                "по кросс-валидации ROC-AUC около 0,66 — это подсказка для проверки, а не окончательный вывод.")
    measurements.update({"вероятность брака": f"{p['bad']:.2f}", "укладка": f"{p['hip_positioning']:.2f}",
                         "поля зоны интереса": f"{p['hip_roi']:.2f}"})
    return dict(
        quality_class=m["quality_class"],
        violations=m["violations"],
        explanations=expl,
        measurements=measurements,
        metrics=dict(shaft_x=shaft, hip_prob_bad=round(p["bad"], 4), hip_prob_positioning=round(p["hip_positioning"], 4),
                     hip_prob_roi=round(p["hip_roi"], 4)),
        geometry=dict(shaft_x=shaft),
    )


def analyze(pixels: np.ndarray, params: dict | None = None) -> dict:
    """Результат: region, region_basis, quality_class (0/1/None), violations (коды),
    explanations (русский текст), measurements (подпись -> значение), geometry (для отрисовки).
    params — пороги из dxaqc/params.py, по умолчанию значения версии 0.1."""
    region, basis = detect_region(pixels)
    if region == "lumbar_spine":
        res = analyze_spine(pixels, params)
    elif region in ("hip_right", "hip_left"):
        res = analyze_hip(pixels, region)
    else:
        res = dict(quality_class=None, violations=[], explanations=["Область не определена."], measurements={}, metrics={}, geometry={})
    res["region"] = region
    res["region_basis"] = basis
    res["explanations"] = [f"Область: {basis}."] + res["explanations"]
    return res
