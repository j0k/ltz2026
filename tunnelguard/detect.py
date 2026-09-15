# -*- coding: utf-8 -*-
"""Детектор посторонних объектов: сравнение скана с цифровым двойником тоннеля.

Конвейер:
  1. фон: точка считается известной статикой, если лежит ближе порога к поверхности двойника;
  2. кандидаты группируются в кластеры по вокселям;
  3. кластер проверяется на вхождение в габарит поезда;
  4. по дистанции и скорости считается решение: тормозить, предупредить или только записать.
"""
from dataclasses import dataclass, field
import time
import numpy as np

from . import sim

BG_THRESHOLD = 0.12     # м: шум дальности, ошибка локализации и допуск обделки
VOXEL = 0.30            # м: размер вокселя для кластеризации
MIN_POINTS = 4
# габарит приближения: прямоугольник со срезанным верхом, чтобы не задевать свод тоннеля
ENV_HALF_U = 1.70       # полуширина до высоты ENV_SHOULDER, м
ENV_SHOULDER = 3.00
ENV_TOP_HALF_U = 1.20   # полуширина верхней части, м
ENV_TOP = 3.50
MIN_IN_ENV = 3

ENV_POLY = [(-ENV_HALF_U, 0.0), (-ENV_HALF_U, ENV_SHOULDER), (-ENV_TOP_HALF_U, ENV_SHOULDER),
            (-ENV_TOP_HALF_U, ENV_TOP), (ENV_TOP_HALF_U, ENV_TOP), (ENV_TOP_HALF_U, ENV_SHOULDER),
            (ENV_HALF_U, ENV_SHOULDER), (ENV_HALF_U, 0.0)]


def in_envelope(P):
    u, z = np.abs(P[:, 1]), P[:, 2]
    low = (u <= ENV_HALF_U) & (z >= 0.0) & (z <= ENV_SHOULDER)
    top = (u <= ENV_TOP_HALF_U) & (z > ENV_SHOULDER) & (z <= ENV_TOP)
    return low | top

SPEED_KMH = 40.0
DECEL = 1.2             # экстренное замедление, м/с²
REACTION = 0.5          # задержка системы и тормозов, с
MARGIN = 10.0           # запас к тормозному пути, м


def braking_distance(speed_kmh=SPEED_KMH):
    v = speed_kmh / 3.6
    return v * REACTION + v * v / (2 * DECEL)


_STATIC = sim.static_boxes()
_LO = np.stack([b.lo for b in _STATIC]).astype(np.float32)
_HI = np.stack([b.hi for b in _STATIC]).astype(np.float32)


def background_distance(p):
    """Расстояние от точек до ближайшей поверхности цифрового двойника."""
    r = np.sqrt(p[:, 1] ** 2 + (p[:, 2] - sim.AXIS_Z) ** 2)
    d = np.abs(sim.TUNNEL_R - r)
    on_floor = np.abs(p[:, 1]) <= sim.FLOOR_HALF + 0.05
    d = np.where(on_floor, np.minimum(d, np.abs(p[:, 2] - sim.FLOOR_Z)), d)
    for s in range(0, len(p), 8000):
        q = p[s:s + 8000, None, :]
        gap = np.maximum(np.maximum(_LO[None] - q, q - _HI[None]), 0.0)
        db = np.sqrt((gap ** 2).sum(-1)).min(axis=1)
        d[s:s + 8000] = np.minimum(d[s:s + 8000], db)
    return d


def _components(keys):
    """Связные компоненты вокселей по 26-соседству."""
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    index = {tuple(k): i for i, k in enumerate(uniq)}
    comp = -np.ones(len(uniq), dtype=np.int32)
    offs = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) != (0, 0, 0)]
    cid = 0
    for i in range(len(uniq)):
        if comp[i] >= 0:
            continue
        comp[i] = cid
        stack = [i]
        while stack:
            j = stack.pop()
            x, y, z = uniq[j]
            for a, b, c in offs:
                k = index.get((x + a, y + b, z + c))
                if k is not None and comp[k] < 0:
                    comp[k] = cid
                    stack.append(k)
        cid += 1
    return comp[inv]


@dataclass
class Detection:
    idx: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    distance: float
    in_envelope: bool
    n_points: int
    label_guess: str
    decision: str
    ttc: float
    truth: int = 0          # мажоритарная метка истины, заполняется в оценке


@dataclass
class Result:
    detections: list = field(default_factory=list)
    candidates: np.ndarray = None
    status: str = "clear"
    latency_ms: float = 0.0


def _guess(ext):
    dx, du, dz = ext
    if dz > 1.1 and max(dx, du) < 0.9:
        return "похоже на человека"
    if max(dx, du) > 1.2 and dz < 0.35:
        return "предмет поперёк пути"
    return "предмет"


def detect(pts, x0, speed_kmh=SPEED_KMH):
    t0 = time.perf_counter()
    res = Result()
    d = background_distance(pts)
    cand = np.nonzero(d > BG_THRESHOLD)[0]
    # позади и под датчиком ничего не ищем
    cand = cand[pts[cand, 0] > x0 + 1.5]
    res.candidates = cand
    if len(cand) == 0:
        res.latency_ms = (time.perf_counter() - t0) * 1000
        return res
    keys = np.floor(pts[cand] / VOXEL).astype(np.int32)
    comp = _components(keys)
    brake = braking_distance(speed_kmh)
    v = speed_kmh / 3.6
    for c in np.unique(comp):
        idx = cand[comp == c]
        if len(idx) < MIN_POINTS:
            continue
        P = pts[idx]
        inside = in_envelope(P)
        in_env = int(inside.sum()) >= MIN_IN_ENV
        dist = float((P[inside, 0].min() if in_env else P[:, 0].min()) - x0)
        lo, hi = P.min(0), P.max(0)
        if in_env and dist <= brake + MARGIN:
            decision = "brake"
        elif in_env:
            decision = "warn"
        else:
            decision = "log"
        res.detections.append(Detection(idx, lo, hi, dist, in_env, len(idx), _guess(hi - lo),
                                        decision, dist / v if v > 0 else np.inf))
    res.detections.sort(key=lambda z: z.distance)
    if any(z.decision == "brake" for z in res.detections):
        res.status = "brake"
    elif any(z.decision == "warn" for z in res.detections):
        res.status = "warn"
    res.latency_ms = (time.perf_counter() - t0) * 1000
    return res
