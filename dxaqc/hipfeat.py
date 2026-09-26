# -*- coding: utf-8 -*-
"""Признаки укладки бедра из сегментации атласа: ориентиры, которые по ТЗ должны быть в кадре, и признаки ротации.

Все признаки приведены к одной ориентации: medial > 0 — в сторону таза, поэтому левые и правые бёдра сравнимы.
Координаты — в долях ширины и высоты кадра, углы — в градусах.
"""
from __future__ import annotations

import numpy as np

NAMES = ["height", "aspect", "shaft_angle", "shaft_offset", "shaft_width", "gt_lateral_margin", "gt_y", "gt_from_shaft",
         "femur_top", "femur_area", "neck_width", "lesser_troch", "lesser_troch_y", "pelvis_area", "pelvis_low",
         "pelvis_medial_margin", "pelvis_y", "femur_brightness", "pelvis_brightness", "background", "contrast"]


def _edges(fem: np.ndarray):
    rows = np.where(fem.any(1))[0]
    L = np.array([np.argmax(fem[y]) for y in rows])
    R = np.array([fem.shape[1] - 1 - np.argmax(fem[y][::-1]) for y in rows])
    return rows, L, R


def features(a: np.ndarray, region: str) -> dict | None:
    from dxaqc.atlas import hip_parts
    parts = hip_parts(a, region)
    if parts is None:
        return None
    h, w = a.shape
    med = parts["med"]
    fem, pel = parts["femur"], parts["pelvis"]
    rows, L, R = _edges(fem)
    if len(rows) < 10:
        return None
    lat_edge = np.where(med == 1, L, R)          # наружный край бедра
    med_edge = np.where(med == 1, R, L)          # внутренний, в сторону таза
    centre = (L + R) / 2
    low = rows > h * 0.55
    if low.sum() >= 5:
        k = np.polyfit(rows[low], centre[low], 1)[0]
        angle = float(np.degrees(np.arctan(k))) * med
    else:
        angle = 0.0
    shaft_c, _ = parts["shaft"]
    half = float(np.median((R[low] - L[low]) / 2)) if low.any() else w * 0.1
    gt_x, gt_y = parts["gt"]
    lat_margin = (gt_x if med == 1 else (w - 1 - gt_x)) / w       # от большого вертела до наружного края кадра
    ytop = int(rows.min())
    neck = rows < ytop + h * 0.12
    neck_w = float(np.median(R[neck] - L[neck])) / w if neck.any() else 0.0
    # малый вертел: насколько внутренний край выступает медиально над линией диафиза ниже большого вертела
    zone = (rows > gt_y) & (rows < gt_y + h * 0.35)
    line = shaft_c + med * half
    prot = (med_edge[zone] - line) * med if zone.any() else np.array([0.0])
    lt = float(max(prot.max(), 0.0)) / max(half, 1.0)
    lt_y = float(rows[zone][int(np.argmax(prot))]) / h if zone.any() else 0.0
    pel_yx = np.argwhere(pel)
    af = a.astype(np.float32)
    bone = fem | pel
    bg = float(af[~bone].mean()) if (~bone).any() else 0.0
    fb = float(af[fem].mean())
    pb = float(af[pel].mean()) if pel.any() else bg
    if len(pel_yx):
        pel_low = float(pel_yx[:, 0].max()) / h
        pel_med_margin = ((w - 1 - pel_yx[:, 1].max()) if med == 1 else pel_yx[:, 1].min()) / w
        pel_y = float(pel_yx[:, 0].mean()) / h
    else:
        pel_low, pel_med_margin, pel_y = 0.0, 1.0, 0.0
    return dict(height=h / 300.0, aspect=h / w, shaft_angle=angle, shaft_offset=(shaft_c - w / 2) * med / w,
                shaft_width=2 * half / w, gt_lateral_margin=float(lat_margin), gt_y=gt_y / h,
                gt_from_shaft=abs(gt_x - shaft_c) / w, femur_top=ytop / h, femur_area=float(fem.mean()), neck_width=neck_w,
                lesser_troch=lt, lesser_troch_y=lt_y, pelvis_area=float(pel.mean()), pelvis_low=pel_low,
                pelvis_medial_margin=float(pel_med_margin), pelvis_y=pel_y, femur_brightness=fb / 255, pelvis_brightness=pb / 255,
                background=bg / 255, contrast=(fb - bg) / 255)


def vector(f: dict) -> np.ndarray:
    return np.array([f[n] for n in NAMES], dtype=np.float64)


# ------------------------------------------------------------------ модель: логистическая регрессия с L2 на numpy

def fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 400) -> dict:
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    wgt = np.zeros(Z.shape[1]); b = 0.0
    pos = y.mean() if 0 < y.mean() < 1 else 0.5
    cw = np.where(y == 1, 0.5 / pos, 0.5 / (1 - pos))        # баланс классов: нарушений меньше, чем нормы
    for _ in range(iters):                                    # метод Ньютона: быстро и без подбора шага
        p = 1 / (1 + np.exp(-(Z @ wgt + b)))
        g = cw * (p - y)
        grad_w = Z.T @ g / len(y) + l2 * wgt / len(y)
        grad_b = g.mean()
        s = cw * p * (1 - p)
        H = (Z.T * s) @ Z / len(y) + np.eye(Z.shape[1]) * l2 / len(y)
        Hb = s.mean() + 1e-9
        wgt -= np.linalg.solve(H, grad_w)
        b -= grad_b / Hb
        if np.abs(grad_w).max() < 1e-7:
            break
    return dict(mu=mu, sd=sd, w=wgt, b=b)


def predict(model: dict, X: np.ndarray) -> np.ndarray:
    Z = (X - model["mu"]) / model["sd"]
    return 1 / (1 + np.exp(-(Z @ model["w"] + model["b"])))
