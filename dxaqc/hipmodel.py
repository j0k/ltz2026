# -*- coding: utf-8 -*-
"""Качество снимка бедра: обученная модель ExtraTrees по 47 признакам формы, краёв кадра и ориентиров атласа.

Обучение — scripts/train_hip.py (scikit-learn в исследовательском окружении), сюда попадают только веса:
деревья выгружены в dxaqc/models/hip_trees.npz массивами узлов, предсказание считается на numpy без sklearn.
Три модели: брак в целом, укладка и ротация (hip_positioning), поля вокруг зоны интереса (hip_roi); пороги подобраны
по F1 на кросс-валидации по исследованиям при обучении.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

import numpy as np

from dxaqc import hipfeat as HF
from dxaqc.atlas import otsu

MODEL_PATH = os.environ.get("DXAQC_HIP_MODEL", os.path.join(os.path.dirname(__file__), "models", "hip_trees.npz"))
TARGETS = ("bad", "hip_positioning", "hip_roi")


def _blur(a, k):
    from dxaqc.analyze import _blur as b
    return b(a, k)


def features(a: np.ndarray, region: str) -> dict:
    """Признаки снимка в одной ориентации: таз справа, наружная сторона бедра слева."""
    if region == "hip_left":
        a = a[:, ::-1]
    h, w = a.shape
    af = a.astype(np.float32)
    b = _blur(af, 5)
    thr = max(otsu(b), 25)
    bone = b > thr
    f = {"rows": h}
    e = max(2, int(min(h, w) * 0.04))                  # полоса у края кадра
    for name, band in (("top", bone[:e]), ("bottom", bone[-e:]), ("lateral", bone[:, :e]), ("medial", bone[:, -e:]),
                       ("lat_top", bone[: h // 2, :e]), ("med_bottom", bone[h // 2:, -e:]), ("med_top", bone[: h // 2, -e:])):
        f[f"edge_{name}"] = float(band.mean())
    ys, xs = np.nonzero(bone)
    if len(xs):
        f["bone_left"] = xs.min() / w; f["bone_right"] = xs.max() / w; f["bone_top"] = ys.min() / h
        f["bone_frac"] = bone.mean(); f["bone_cx"] = xs.mean() / w; f["bone_cy"] = ys.mean() / h
    for q in range(3):                                  # сколько кости в каждой трети по высоте и ширине
        f[f"row_third_{q}"] = float(bone[q * h // 3:(q + 1) * h // 3].mean())
        f[f"col_third_{q}"] = float(bone[:, q * w // 3:(q + 1) * w // 3].mean())
    local = af - _blur(af, 21)
    f["contrast_p999"] = float(np.percentile(local, 99.9))
    gy, gx = np.gradient(_blur(af, 3)); g = np.hypot(gx, gy)
    f["grad_p99"] = float(np.percentile(g, 99))
    f["mean"] = float(af.mean()) / 255; f["bone_mean"] = float(af[bone].mean()) / 255 if bone.any() else 0
    prof = bone.mean(1)                                 # профиль ширины кости по строкам
    f["prof_max_row"] = float(np.argmax(prof)) / h; f["prof_std"] = float(prof.std())
    hf = HF.features(a if region == "hip_right" else a[:, ::-1], region)
    if hf:
        f.update({f"geo_{k}": v for k, v in hf.items()})
    return {k: float(v) for k, v in f.items()}


@lru_cache(maxsize=2)
def load(path: str = MODEL_PATH) -> dict | None:
    if not os.path.isfile(path):
        return None
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    models = {}
    for t in TARGETS:
        n = int(z[f"{t}_n_trees"])
        models[t] = [tuple(z[f"{t}_{i}_{k}"] for k in ("feature", "threshold", "left", "right", "value")) for i in range(n)]
    return dict(meta=meta, models=models)


def _forest_proba(trees, x: np.ndarray) -> float:
    """Средняя по деревьям доля брака в листе — как predict_proba у sklearn."""
    total = 0.0
    for feat, thr, left, right, value in trees:
        node = 0
        while left[node] >= 0:
            node = left[node] if x[feat[node]] <= thr[node] else right[node]
        total += value[node]
    return total / len(trees)


def vector(f: dict, meta: dict) -> np.ndarray:
    """Признаки в порядке обучения; отсутствующие (ориентиры не найдены) — медианой обучающего набора."""
    return np.array([f.get(n, m) if np.isfinite(f.get(n, m)) else m for n, m in zip(meta["features"], meta["medians"])],
                    dtype=np.float64)


def predict(a: np.ndarray, region: str, model: dict | None = None) -> dict | None:
    model = model or load()
    if model is None:
        return None
    meta = model["meta"]
    x = vector(features(a, region), meta)
    prob = {t: _forest_proba(model["models"][t], x) for t in TARGETS}
    thr = meta["thresholds"]
    bad = prob["bad"] >= thr["bad"]
    types = []
    if bad:                                             # тип — по тому, чья вероятность дальше за своим порогом
        ratio = {t: prob[t] / max(thr[t], 1e-6) for t in ("hip_positioning", "hip_roi")}
        types = [t for t in ratio if prob[t] >= thr[t]] or [max(ratio, key=ratio.get)]
    return dict(prob=prob, thresholds=thr, quality_class=int(bad), violations=types, version=meta["version"])
