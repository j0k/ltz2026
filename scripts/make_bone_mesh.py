# -*- coding: utf-8 -*-
"""Модель таза и тазобедренных суставов для главной: гладкий кортикальный слой, губчатая трабекулярная решётка
на срезе шейки бедра (зона, которую меряет денситометрия), запечённое затенение в порах и складках.

Кости заданы неявными функциями (приближённое расстояние со знаком, отрицательное внутри) и сглаженно
объединены; поверхность — marching cubes, упрощение — fast-simplification. Единицы — мм, y вверх,
пациент смотрит на камеру (+z), его левая сторона — +x.

    ../.venv-ml/bin/python scripts/make_bone_mesh.py [voxel_mm] [target_tris]
    → dxaqc/web/static/bone/pelvis.bin.gz
"""
import gzip
import os
import struct
import sys
import time

import numpy as np

VOX = float(sys.argv[1]) if len(sys.argv) > 1 else 1.3
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 220_000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dxaqc", "web", "static", "bone")
LO, HI = np.array([-182.0, -250.0, -70.0]), np.array([182.0, 128.0, 100.0])
t0 = time.time()

# ------------------------------------------------------------------ примитивы (поля на сетке float32)

nx, ny, nz = (np.ceil((HI - LO) / VOX)).astype(int) + 1
X = (LO[0] + np.arange(nx, dtype=np.float32) * VOX)[:, None, None]
Y = (LO[1] + np.arange(ny, dtype=np.float32) * VOX)[None, :, None]
Z = (LO[2] + np.arange(nz, dtype=np.float32) * VOX)[None, None, :]
print(f"сетка {nx}×{ny}×{nz} = {nx * ny * nz / 1e6:.1f} млн ячеек", flush=True)


def smin(a, b, k):
    """Сглаженный минимум: кости срастаются плавно, без швов."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return (b * (1 - h) + a * h - k * h * (1 - h)).astype(np.float32)


def smax(a, b, k):
    """Сглаженный максимум: пересечение со скруглённой кромкой — край крыла без зубцов."""
    return -smin(-a, -b, k)


def sphere(c, r):
    return np.sqrt((X - c[0]) ** 2 + (Y - c[1]) ** 2 + (Z - c[2]) ** 2) - r


def ellipsoid(c, r):
    q = np.sqrt(((X - c[0]) / r[0]) ** 2 + ((Y - c[1]) / r[1]) ** 2 + ((Z - c[2]) / r[2]) ** 2)
    return (q - 1) * min(r)


def capsule(a, b, ra, rb=None):
    """Отрезок a→b с радиусом, плавно меняющимся от ra до rb."""
    rb = ra if rb is None else rb
    a, b = np.array(a, np.float32), np.array(b, np.float32)
    ab = b - a
    t = ((X - a[0]) * ab[0] + (Y - a[1]) * ab[1] + (Z - a[2]) * ab[2]) / float(ab @ ab)
    t = np.clip(t, 0, 1)
    d = np.sqrt((X - a[0] - t * ab[0]) ** 2 + (Y - a[1] - t * ab[1]) ** 2 + (Z - a[2] - t * ab[2]) ** 2)
    return d - (ra + (rb - ra) * t)


def curve(points, r0, r1):
    """Изогнутая трубка по ломаной — лобковые и седалищные ветви, гребень подвздошной кости."""
    d, n = None, len(points) - 1
    for i in range(n):
        ri, rj = r0 + (r1 - r0) * i / n, r0 + (r1 - r0) * (i + 1) / n
        c = capsule(points[i], points[i + 1], ri, rj)
        d = c if d is None else smin(d, c, 3.0)
    return d


def _frame(a, b, c):
    """Локальный базис пластины: u — вдоль a→b, n — нормаль плоскости abc, v — в плоскости."""
    a, b, c = (np.array(x, np.float32) for x in (a, b, c))
    eu = (b - a) / np.linalg.norm(b - a)
    n = np.cross(eu, c - a); n /= np.linalg.norm(n)
    ev = np.cross(n, eu)
    return a, eu, ev, n


def wing(s):
    """Крыло подвздошной кости: изогнутая чаша-веер — тонкая в середине (подвздошная ямка), утолщённая по краю
    (гребень); вогнутость смотрит вперёд и внутрь, к полости таза."""
    si, asis, top = (s * 40, 6, -44), (s * 122, 16, 32), (s * 78, 86, -24)
    o, eu, ev, n = _frame(si, asis, top)
    if s < 0:                                          # одинаковая сторона нормали у обоих крыльев — вперёд
        n = -n
    if n[2] < 0:
        n = -n
    px, py, pz = X - o[0], Y - o[1], Z - o[2]
    u = px * eu[0] + py * eu[1] + pz * eu[2]
    v = px * ev[0] + py * ev[1] + pz * ev[2]
    w = px * n[0] + py * n[1] + pz * n[2]
    uc, vc = 50.0, 34.0                                # центр веера в плоскости
    ru, rv = 66.0, 52.0
    e = np.sqrt(((u - uc) / ru) ** 2 + ((v - vc) / rv) ** 2)       # < 1 внутри контура
    outline = (e - 1) * min(ru, rv)
    outline = np.maximum(outline, -(v + 24))                        # снизу крыло переходит в тело кости
    bowl = 0.0065 * ((u - uc) ** 2 + 0.8 * (v - vc) ** 2)           # вогнутость
    rim = np.clip((e - 0.72) / 0.28, 0, 1)
    thick = 3.4 + 5.0 * rim ** 2                                     # ямка тонкая, гребень толстый и скруглённый
    plate = smax(np.abs(w - bowl + 10) - thick, outline, 3.5)
    return plate


def half_pelvis(s):
    d = wing(s)
    acet = np.array([s * 88, -40, 26], np.float32)
    d = smin(d, capsule((s * 66, 2, -2), acet, 18, 22), 12)                              # тело подвздошной кости
    d = smin(d, capsule((s * 58, 22, -26), (s * 70, -12, 4), 16, 18), 12)                # крыло срастается с телом
    d = smin(d, capsule((s * 96, 14, 22), (s * 90, -20, 26), 11, 16), 10)                # передний край к впадине
    d = smin(d, sphere(acet, 27), 8)                                                     # масса вокруг вертлужной впадины
    d = smin(d, curve([acet, (s * 82, -72, 6), (s * 70, -98, -4)], 13, 11), 7)          # седалищная кость
    d = smin(d, ellipsoid((s * 68, -104, -6), (15, 12, 14)), 5)                         # седалищный бугор
    d = smin(d, curve([(s * 72, -44, 44), (s * 44, -56, 58), (s * 14, -66, 64)], 9, 8), 5)     # верхняя ветвь лобковой
    d = smin(d, curve([(s * 12, -82, 60), (s * 30, -98, 44), (s * 58, -106, 14)], 7, 9), 5)    # нижняя ветвь → седалищная
    d = smin(d, ellipsoid((s * 12, -72, 62), (7, 15, 9)), 4)                            # тело лобковой кости
    d = smin(d, capsule((s * 40, 20, -30), (s * 30, -10, -36), 12, 10), 8)               # у крестцово-подвздошного сустава
    cup = sphere((s * 104, -41, 34), 25.5)                                               # впадина открыта наружу-вперёд
    return np.maximum(d, -cup)


def sacrum():
    """Крестец: широкая треугольная пластина между крестцово-подвздошными суставами, изогнутая назад, с отверстиями;
    сверху тело позвонка L5, снизу копчик."""
    t = np.clip((20 - Y) / 100, 0, 1)                      # 0 — основание, 1 — верхушка
    w = 56 - 44 * t ** 0.9
    zc = -42 - 18 * t - 10 * np.sin(np.pi * t)
    th = 17 - 9 * t
    q = np.maximum((np.abs(X) - w) * 0.9, np.abs(Z - zc) - th)
    d = np.maximum(q, np.maximum(Y - 20, -82 - Y))
    d = smin(d, ellipsoid((0, 16, -40), (30, 12, 20)), 8)                # основание крестца, мыс
    d = smin(d, capsule((0, -80, -56), (0, -100, -44), 6, 3.5), 3)                       # копчик
    for yy, xx in ((2, 24), (-20, 21), (-42, 17), (-60, 13)):                           # крестцовые отверстия
        for sx in (-1, 1):
            d = np.maximum(d, -capsule((sx * xx, yy, -90), (sx * xx, yy, 0), 3.6))
    return d


def femur(s):
    head = np.array([s * 102, -41, 33], np.float32)
    d = sphere(head, 23)
    neck_end = np.array([s * 140, -66, 22], np.float32)
    d = smin(d, capsule(head, neck_end, 14, 17), 7)                                     # шейка, угол ~130°
    d = smin(d, ellipsoid((s * 150, -58, 12), (15, 24, 17)), 7)                          # большой вертел
    d = smin(d, sphere((s * 124, -98, 8), 9), 6)                                        # малый вертел
    d = smin(d, capsule((s * 142, -80, 18), (s * 128, -242, 26), 16, 14), 9)             # диафиз
    d = smin(d, capsule((s * 150, -62, 6), (s * 124, -96, 6), 7), 5)                     # межвертельный гребень
    return d, head, neck_end


print("поля костей…", flush=True)
B = half_pelvis(1)
B = np.minimum(B, half_pelvis(-1))
B = smin(B, sacrum(), 6)
fl, head_l, neck_l = femur(1)
fr, _, _ = femur(-1)
B = np.minimum(B, np.minimum(fl, fr)).astype(np.float32)          # бедро отделено от таза суставной щелью
del fl, fr
print(f"  {time.time() - t0:.0f} с", flush=True)

# ------------------------------------------------------------------ срез левой шейки бедра и губчатая решётка

T_CORT = 2.6                                                     # кортикальный слой, мм
cut_c = (head_l + neck_l) / 2 + np.array([12, 6, 0], np.float32)
R_CUT = 44.0
z_cut = float(head_l[2]) + 2.0                                   # передняя половина головки и шейки снята
dist_c = np.sqrt((X - cut_c[0]) ** 2 + (Y - cut_c[1]) ** 2 + (Z - cut_c[2]) ** 2)
removal = np.maximum(z_cut - Z, dist_c - R_CUT)                   # < 0 — удалённая часть
near = np.minimum(Z - (z_cut - 18), R_CUT + 4 - dist_c)           # > 0 — у поверхности среза: там решётка
P = 2 * np.pi / 6.5                                              # гироид, период 6,5 мм — трабекулы
# лёгкое искривление координат: перемычки органичные, не как у кристалла
Xw = X + 1.8 * np.sin(Y * 0.21 + Z * 0.13)
Yw = Y + 1.8 * np.sin(Z * 0.19 + X * 0.11)
Zw = Z + 1.8 * np.sin(X * 0.17 + Y * 0.15)
g = np.sin(Xw * P) * np.cos(Yw * P) + np.sin(Yw * P) * np.cos(Zw * P) + np.sin(Zw * P) * np.cos(Xw * P)
del Xw, Yw, Zw
lat = (np.abs(g) - 0.42) / P                                     # < 0 — перемычки решётки
del g
shell = np.maximum(B, -(B + T_CORT))
fill = np.maximum(B, np.minimum(lat, near))       # у среза — решётка, в глубине — сплошная кость
S = np.maximum(np.minimum(shell, fill), -removal).astype(np.float32)
del lat, shell, fill, near, removal, dist_c
print(f"поле готово, {time.time() - t0:.0f} с", flush=True)

# ------------------------------------------------------------------ поверхность, затенение, упрощение

from skimage.measure import marching_cubes
verts, faces, normals, _ = marching_cubes(S, level=0.0, spacing=(VOX, VOX, VOX))
verts += LO.astype(np.float32)
print(f"marching cubes: {len(verts)} вершин, {len(faces)} треугольников, {time.time() - t0:.0f} с", flush=True)

# сглаживание Таубина: убирает ступеньки marching cubes, не сжимая форму
from scipy.sparse import coo_matrix, diags
nv = len(verts)
ij = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
Adj = coo_matrix((np.ones(len(ij) * 2, np.float32), (np.r_[ij[:, 0], ij[:, 1]], np.r_[ij[:, 1], ij[:, 0]])), shape=(nv, nv)).tocsr()
Adj.data[:] = 1.0
Lap = diags(1.0 / np.maximum(np.asarray(Adj.sum(1)).ravel(), 1)) @ Adj
for _ in range(6):
    for lam in (0.5, -0.53):
        verts = verts + lam * (Lap @ verts - verts)
verts = verts.astype(np.float32)
print(f"сглажено, {time.time() - t0:.0f} с", flush=True)

import fast_simplification
if len(faces) > TARGET:
    verts, faces = fast_simplification.simplify(verts.astype(np.float32), faces.astype(np.int32), 1 - TARGET / len(faces))
    print(f"упрощено до {len(faces)} треугольников, {time.time() - t0:.0f} с", flush=True)

# нормали вершин по граням
vn = np.zeros_like(verts)
fn = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]], verts[faces[:, 2]] - verts[faces[:, 0]])
for k in range(3):
    np.add.at(vn, faces[:, k], fn)
vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-9
# marching cubes даёт нормали наружу от отрицательной области: проверка по полю
from scipy.ndimage import map_coordinates


def sample(p):
    idx = ((p - LO) / VOX).T
    return map_coordinates(S, idx, order=1, mode="nearest")


probe = sample(verts + vn * 1.5)
if np.mean(probe > 0) < 0.5:
    vn = -vn
# запечённое затенение (ambient occlusion по полю): чем ближе стенки вокруг — тем темнее
ao = np.zeros(len(verts), np.float32)
for dist in (2.0, 4.0, 8.0, 14.0):
    ao += np.clip(sample(verts + vn * dist) / dist, 0, 1)
ao /= 4
ao = np.clip(ao, 0, 1) ** 0.8
print(f"затенение, {time.time() - t0:.0f} с; среднее {ao.mean():.2f}", flush=True)

# ------------------------------------------------------------------ упаковка: uint16 координаты, int8 нормали, uint8 затенение

vmin, vmax = verts.min(0), verts.max(0)
q = np.round((verts - vmin) / (vmax - vmin) * 65535).astype(np.uint16)
nq = np.round(vn * 127).astype(np.int8)
aq = np.round(ao * 255).astype(np.uint8)
idx_dtype = np.uint32
header = struct.pack("<4sII6f", b"DXB1", len(verts), len(faces), *vmin.tolist(), *vmax.tolist())
blob = header + q.tobytes() + nq.tobytes() + aq.tobytes() + faces.astype(idx_dtype).tobytes()
os.makedirs(OUT, exist_ok=True)
with gzip.open(os.path.join(OUT, "pelvis.bin.gz"), "wb", compresslevel=9) as f:
    f.write(blob)
print(f"pelvis.bin.gz: {os.path.getsize(os.path.join(OUT, 'pelvis.bin.gz')) / 1e6:.2f} МБ "
      f"({len(verts)} вершин, {len(faces)} треугольников), всего {time.time() - t0:.0f} с")
