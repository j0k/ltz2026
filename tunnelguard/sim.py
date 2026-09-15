# -*- coding: utf-8 -*-
"""Процедурный тоннель метро и эмулятор лидара.

Система координат пути: x вдоль оси пути вперёд, u влево от оси пути, z вверх от головки рельса.
Первая версия моделирует прямой участок; кривые учитываются переходом в координаты пути
по плану путей, это задача второй версии.
"""
from dataclasses import dataclass
import numpy as np

TUNNEL_R = 2.75        # внутренний радиус обделки, м
AXIS_Z = 1.45          # высота оси тоннеля над головкой рельса, м
FLOOR_Z = -0.18        # уровень путевого бетона, м
FLOOR_HALF = float(np.sqrt(TUNNEL_R ** 2 - (AXIS_Z - FLOOR_Z) ** 2))  # полуширина пола
RAIL_U = 0.795         # ось рельса от оси пути, колея 1520 мм
SENSOR_Z = 1.10        # высота лидара на лобовой части поезда
RANGE_MAX = 130.0
ROUTE = (-60.0, 420.0)  # протяжённость моделируемого участка

LBL_STATIC = 0         # обделка, пол, рельсы и известное оборудование
LBL_CLUTTER = -2       # статика, которой нет в цифровом двойнике: кронштейны, короба
LBL_DUST = -1          # пыль и ложные отражения


@dataclass
class Box:
    lo: np.ndarray
    hi: np.ndarray
    label: int = LBL_STATIC
    kind: str = "static"


def box(cx, cu, z0, dx, du, dz, label=LBL_STATIC, kind="static"):
    """Параллелепипед по центру в плане (cx, cu), низу z0 и размерам."""
    lo = np.array([cx - dx / 2, cu - du / 2, z0], dtype=np.float64)
    hi = np.array([cx + dx / 2, cu + du / 2, z0 + dz], dtype=np.float64)
    return Box(lo, hi, label, kind)


def static_boxes():
    """Известная статика тоннеля: то, что лежит в цифровом двойнике."""
    L = ROUTE[1] - ROUTE[0] + 200
    cx = (ROUTE[0] + ROUTE[1]) / 2
    out = []
    for s in (-1, 1):
        out.append(box(cx, s * RAIL_U, FLOOR_Z, L, 0.072, -FLOOR_Z, kind="rail"))
        out.append(box(cx, s * 2.45, 1.0, L, 0.24, 0.24, kind="tray"))
    out.append(box(cx, -1.58, FLOOR_Z, L, 0.08, 0.34, kind="contact_rail"))
    for xl in np.arange(ROUTE[0], ROUTE[1], 25.0):
        out.append(box(xl, 2.38, 2.42, 1.2, 0.2, 0.16, kind="light"))
    for xs in np.arange(ROUTE[0] + 10, ROUTE[1], 60.0):
        out.append(box(xs, -2.45, 1.35, 0.5, 0.26, 0.55, kind="signal"))
    return out


def clutter_boxes(rng, n=14):
    """Неучтённая статика на стенах: не в двойнике, но и не в габарите поезда."""
    out = []
    for _ in range(n):
        s = rng.choice([-1, 1])
        z0 = rng.uniform(1.75, 2.35)
        out.append(box(rng.uniform(*ROUTE), s * rng.uniform(2.25, 2.35), z0,
                       rng.uniform(0.2, 0.8), 0.14, rng.uniform(0.1, 0.25),
                       label=LBL_CLUTTER, kind="clutter"))
    return out


# ---------------------------------------------------------------- посторонние объекты

def person(x, u, label):
    return [box(x, u, FLOOR_Z + 0.02, 0.32, 0.48, 1.55, label, "person"),
            box(x, u, FLOOR_Z + 1.57, 0.22, 0.22, 0.24, label, "person")]


def crate(x, u, label, dx=0.6, du=0.5, dz=0.45):
    return [box(x, u, 0.0, dx, du, dz, label, "crate")]


def pipe(x, label, length=2.4, u=0.0):
    return [box(x, u, 0.02, 0.09, length, 0.09, label, "pipe")]


def bag_by_wall(x, side, label):
    """Сумка у стены на полу: вне габарита, тормозить из-за неё не нужно."""
    return [box(x, side * 1.98, FLOOR_Z, 0.45, 0.28, 0.32, label, "bag")]


def random_objects(rng, x0, k_max=3):
    """Случайные объекты перед поездом. Возвращает боксы и описание истины."""
    boxes, truth = [], []
    k = rng.integers(1, k_max + 1)
    for i in range(k):
        lab = i + 1
        x = x0 + rng.uniform(8, 118)
        r = rng.random()
        if r < 0.30:
            u = rng.uniform(-1.2, 1.2)
            bb, kind = person(x, u, lab), "person"
        elif r < 0.55:
            u = rng.uniform(-1.1, 1.1)
            bb, kind = crate(x, u, lab, *rng.uniform([0.3, 0.3, 0.25], [0.8, 0.8, 0.7])), "crate"
        elif r < 0.72:
            bb, kind = pipe(x, lab, length=rng.uniform(1.4, 2.8), u=rng.uniform(-0.3, 0.3)), "pipe"
        else:
            bb, kind = bag_by_wall(x, rng.choice([-1, 1]), lab), "bag"
        boxes += bb
        truth.append(dict(label=lab, kind=kind, x=float(min(b.lo[0] for b in bb)),
                          in_envelope=kind != "bag"))
    return boxes, truth


# ---------------------------------------------------------------- лидар

def _beam_elevations():
    dense = np.linspace(-6.0, 3.0, 61)          # плотная зона у горизонта
    low = np.linspace(-24.0, -6.6, 22)
    high = np.linspace(3.6, 14.0, 13)
    return np.deg2rad(np.concatenate([low, dense, high]))


ELEV = _beam_elevations()
AZIM = np.deg2rad(np.linspace(-26.0, 26.0, 521))
_E, _A = np.meshgrid(ELEV, AZIM, indexing="ij")
DIRS = np.stack([np.cos(_E) * np.cos(_A), np.cos(_E) * np.sin(_A), np.sin(_E)], -1).reshape(-1, 3)
BEAM_ID = np.repeat(np.arange(len(ELEV)), len(AZIM))


def _raycast(origin, dirs, boxes, chunk=6000):
    n = len(dirs)
    t_out = np.full(n, np.inf)
    lab_out = np.zeros(n, dtype=np.int16)
    lo = np.stack([b.lo for b in boxes])
    hi = np.stack([b.hi for b in boxes])
    labs = np.array([b.label for b in boxes], dtype=np.int16)
    oy, oz = origin[1], origin[2] - AXIS_Z
    for s in range(0, n, chunk):
        d = dirs[s:s + chunk]
        dy, dz = d[:, 1], d[:, 2]
        a = dy * dy + dz * dz
        b = oy * dy + oz * dz
        c = oy * oy + oz * oz - TUNNEL_R ** 2
        root = np.sqrt(np.maximum(b * b - a * c, 0.0))
        t = np.where(a > 1e-12, (-b + root) / np.maximum(a, 1e-12), np.inf)
        down = dz < -1e-9
        t_floor = np.full(len(d), np.inf)
        t_floor[down] = (FLOOR_Z - origin[2]) / dz[down]
        t = np.minimum(t, t_floor)
        lab = np.zeros(len(d), dtype=np.int16)

        inv = 1.0 / np.where(np.abs(d) < 1e-9, 1e-9, d)
        t1 = (lo[None] - origin) * inv[:, None, :]
        t2 = (hi[None] - origin) * inv[:, None, :]
        tmin = np.minimum(t1, t2).max(axis=2)
        tmax = np.maximum(t1, t2).min(axis=2)
        hit = (tmax >= tmin) & (tmin > 0.05)
        tb = np.where(hit, tmin, np.inf)
        j = tb.argmin(axis=1)
        tbest = tb[np.arange(len(d)), j]
        closer = tbest < t
        t = np.where(closer, tbest, t)
        lab = np.where(closer, labs[j], lab)
        t_out[s:s + chunk] = t
        lab_out[s:s + chunk] = lab
    return t_out, lab_out


def scan(x0, objects, rng, clutter=(), noise=True, pose_sigma=0.03):
    """Один оборот лидара с поезда в точке x0.

    Возвращает точки в координатах карты с учётом ошибки локализации, метки истины
    и номер луча по вертикали.
    """
    origin = np.array([x0, 0.0, SENSOR_Z])
    boxes = static_boxes() + list(clutter) + list(objects)
    t, lab = _raycast(origin, DIRS, boxes)
    ok = t < RANGE_MAX
    if noise:
        ok &= rng.random(len(t)) > 0.03                       # выпадения
        t = t + rng.normal(0, 0.015, len(t))                   # шум дальности
    pts = origin + DIRS[ok] * t[ok, None]
    lab = lab[ok].copy()
    beam = BEAM_ID[ok]

    # точность изготовления обделки: радиус гуляет на пару сантиметров
    wall = (lab == LBL_STATIC) & (pts[:, 2] > FLOOR_Z + 0.05)
    ru = pts[wall, 1]
    rz = pts[wall, 2] - AXIS_Z
    r = np.sqrt(ru ** 2 + rz ** 2)
    shell = r > TUNNEL_R - 0.05
    dev = 0.02 * np.sin(2 * np.pi * pts[wall, 0] / 7.3) + 0.01 * np.sin(2 * np.pi * pts[wall, 0] / 1.1)
    k = np.where(shell, 1 + dev / TUNNEL_R, 1.0)
    pts[wall, 1] = ru * k
    pts[wall, 2] = AXIS_Z + rz * k

    if noise:
        m = rng.poisson(28)                                    # пыль в тоннеле
        idx = rng.integers(0, len(DIRS), m)
        rr = rng.uniform(2.0, 60.0, m)
        dust = origin + DIRS[idx] * rr[:, None]
        pts = np.vstack([pts, dust])
        lab = np.concatenate([lab, np.full(m, LBL_DUST, dtype=np.int16)])
        beam = np.concatenate([beam, BEAM_ID[idx]])
        # ошибка локализации: смещение и лёгкий поворот по курсу
        err = rng.normal(0, pose_sigma, 3)
        yaw = np.deg2rad(rng.normal(0, 0.03))
        rel = pts - origin
        c, s_ = np.cos(yaw), np.sin(yaw)
        rel = np.stack([c * rel[:, 0] - s_ * rel[:, 1], s_ * rel[:, 0] + c * rel[:, 1], rel[:, 2]], 1)
        pts = origin + err + rel
    return pts.astype(np.float32), lab, beam
