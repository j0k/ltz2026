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
ARTIFACT_MIN_PIXELS = P.DEFAULTS["artifact_min_pixels"]
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
    bright = (af >= p["artifact_brightness"]) & out_band
    n_bright = int(bright.sum())
    art_boxes = _grid_boxes(bright) if n_bright > p["artifact_min_pixels"] else []

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
        expl.append(f"Вне позвоночного столба найдено {n_bright} очень ярких пикселей в {len(art_boxes)} "
                    f"областях: похоже на металл или посторонний предмет.")
    else:
        expl.append("Ярких посторонних объектов вне позвоночного столба не найдено.")

    return dict(
        quality_class=1 if violations else 0,
        violations=violations,
        explanations=expl,
        metrics=dict(angle_deg=round(angle, 2), abs_angle=round(abs(angle), 2), iliac_left=round(bl, 2),
                     iliac_right=round(br, 2), bright_px=n_bright),
        measurements={
            "угол оси, °": f"{angle:+.1f}",
            "допуск оси, °": f"±{axis_limit:g}",
            "подвздошные кости слева / справа": f"{bl:.1f} / {br:.1f}",
            "яркие пиксели вне столба": str(n_bright),
        },
        limits=dict(axis_limit_deg=axis_limit, iliac_min_brightness=iliac_min, artifact_min_pixels=p["artifact_min_pixels"]),
        geometry=dict(
            centerline=[[float(x), float(y)] for x, y in zip(xs[::3], ys[::3])],
            axis=[[float(axis_x[0]), 0.0], [float(axis_x[-1]), float(h - 1)]],
            axis_ok=abs(angle) <= axis_limit,
            thirds=[[x_top, y_top], [x_bot, y_bot]],
            iliac_boxes=[left_box, right_box],
            iliac_ok=iliac_ok,
            artifact_boxes=art_boxes,
        ),
    )


def analyze_hip(a: np.ndarray, region: str) -> dict:
    h, w = a.shape
    b = _blur(a.astype(np.float32), 9)
    col = b[int(h * 0.72):].mean(0)
    shaft = int(np.argmax(np.convolve(col, np.ones(25) / 25, mode="same")))
    side_ru = "правое" if region == "hip_right" else "левое"
    return dict(
        quality_class=None,
        violations=["hip_not_evaluated_v0"],
        explanations=[f"Определено {side_ru} бедро: таз и головка лежат по {'правую' if region == 'hip_right' else 'левую'} "
                      f"сторону от диафиза на изображении.",
                      "Проверка позиционирования, ротации по малому вертелу и полей зоны интереса появится в следующих версиях."],
        measurements={"центр диафиза, px": str(shaft), "ширина кадра, px": str(w)},
        metrics=dict(shaft_x=shaft),
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
