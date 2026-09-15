# -*- coding: utf-8 -*-
"""Кадры для демо: вид из кабины, мини-карта сверху, панель решения, экран метрик."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import sim, detect

W, H = 1920, 854                    # под полосы подписей FilmKit: 1920x1080 минус 74 и 152
F = "/usr/share/fonts/truetype/noto/"

BG = (7, 9, 13)
PANEL = (15, 20, 27)
PANEL2 = (22, 28, 37)
INK = (236, 240, 245)
INK2 = (160, 170, 184)
INK3 = (104, 114, 128)
ENV = (57, 135, 229)
BRAKE = (227, 73, 72)
WARN = (237, 161, 0)
CLEAR = (27, 175, 122)
AMBER = (237, 161, 0)
RAMP = [(0.0, (228, 240, 255)), (25.0, (150, 196, 246)), (60.0, (80, 148, 232)), (125.0, (40, 88, 160))]


def font(size, bold=False, display=False):
    name = "NotoSansDisplay-Bold.ttf" if display else ("NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf")
    return ImageFont.truetype(F + name, size)


def _ramp(depth):
    stops = np.array([s for s, _ in RAMP])
    cols = np.array([c for _, c in RAMP], dtype=np.float32)
    out = np.empty((len(depth), 3), dtype=np.float32)
    for k in range(3):
        out[:, k] = np.interp(depth, stops, cols[:, k])
    return out.astype(np.uint8)


class Camera:
    """Камера за лобовым стеклом: чуть позади и выше лидара, небольшой наклон вниз."""

    def __init__(self, x0, w, h, fov_deg=40.0, pitch_deg=2.2, back=2.5, height=2.05):
        self.C = np.array([x0 - back, 0.0, height])
        p = np.deg2rad(pitch_deg)
        self.f = np.array([np.cos(p), 0.0, -np.sin(p)])
        self.up = np.array([np.sin(p), 0.0, np.cos(p)])
        self.right = np.array([0.0, -1.0, 0.0])
        self.w, self.h = w, h
        self.fpx = (w / 2) / np.tan(np.deg2rad(fov_deg / 2))
        self.cx, self.cy = w / 2, h * 0.44

    def project(self, P):
        rel = np.asarray(P, dtype=np.float64) - self.C
        depth = rel @ self.f
        sx = self.cx + self.fpx * (rel @ self.right) / np.maximum(depth, 1e-3)
        sy = self.cy - self.fpx * (rel @ self.up) / np.maximum(depth, 1e-3)
        return sx, sy, depth


def _splat(img, sx, sy, depth, colors, size):
    h, w = img.shape[:2]
    order = np.argsort(-depth)
    sx, sy, colors, size = sx[order], sy[order], colors[order], size[order]
    for s in (1, 2, 3):
        m = size == s
        if not m.any():
            continue
        x = sx[m].astype(np.int32)
        y = sy[m].astype(np.int32)
        c = colors[m]
        for dx in range(s):
            for dy in range(s):
                xx, yy = x + dx, y + dy
                ok = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
                img[yy[ok], xx[ok]] = c[ok]


def driver_view(pts, x0, w, h, highlight=None, dim=False):
    """Облако точек из кабины. highlight: {индекс точки: цвет}."""
    cam = Camera(x0, w, h)
    sx, sy, depth = cam.project(pts)
    ok = depth > 0.8
    sx, sy, depth = sx[ok], sy[ok], depth[ok]
    idx_all = np.nonzero(ok)[0]
    colors = _ramp(depth)
    if dim:
        colors = (colors * 0.55).astype(np.uint8)
    size = np.clip(np.round(14.0 / np.maximum(depth, 1.0)), 1, 3).astype(np.int32)
    if highlight:
        pos = {j: i for i, j in enumerate(idx_all)}
        for j, col in highlight.items():
            i = pos.get(int(j))
            if i is not None:
                colors[i] = col
                size[i] = 3
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = BG
    # мягкий градиент у свода, чтобы кадр не был плоским
    grad = np.linspace(18, 0, h // 2).astype(np.uint8)
    img[: h // 2] += grad[:, None, None] // 3
    _splat(img, sx, sy, depth, colors, size)
    return Image.fromarray(img), cam


def draw_envelope(im, cam, x0, braking=None, color=ENV):
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    poly = detect.ENV_POLY
    dists = [12, 20, 30, 45, 60, 80, 100]
    prev = None
    for k, dd in enumerate(dists):
        P = np.array([[x0 + dd, u, z] for u, z in poly])
        sx, sy, _ = cam.project(P)
        pts = list(zip(sx, sy))
        a = int(110 * (1 - k / len(dists)) + 30)
        d.line(pts, fill=color + (a,), width=2 if dd < 30 else 1)
        if prev is not None:
            for p0, p1 in zip(prev, pts):
                d.line([p0, p1], fill=color + (int(a * 0.6),), width=1)
        prev = pts
    if braking:
        P = np.array([[x0 + braking, u, z] for u, z in poly])
        sx, sy, _ = cam.project(P)
        d.line(list(zip(sx, sy)), fill=AMBER + (220,), width=3)
    im.paste(Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"))


def box_corners(lo, hi):
    return np.array([[x, u, z] for x in (lo[0], hi[0]) for u in (lo[1], hi[1]) for z in (lo[2], hi[2])])


EDGES = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]


def draw_box3d(im, cam, lo, hi, color, label=None, dashed=False, pad=0.12):
    d = ImageDraw.Draw(im)
    lo = np.asarray(lo) - pad
    hi = np.asarray(hi) + pad
    sx, sy, dep = cam.project(box_corners(lo, hi))
    for a, b in EDGES:
        if dashed:
            n = 8
            for k in range(0, n, 2):
                t0, t1 = k / n, (k + 1) / n
                d.line([(sx[a] + (sx[b] - sx[a]) * t0, sy[a] + (sy[b] - sy[a]) * t0),
                        (sx[a] + (sx[b] - sx[a]) * t1, sy[a] + (sy[b] - sy[a]) * t1)], fill=color, width=2)
        else:
            d.line([(sx[a], sy[a]), (sx[b], sy[b])], fill=color, width=3)
    bb = [float(sx.min()), float(sy.min()), float(sx.max()), float(sy.max())]
    if label:
        f = font(21, True)
        tw = d.textlength(label, font=f)
        x = max(8, min(bb[0], im.width - tw - 28))
        y = max(8, bb[1] - 44)
        d.rounded_rectangle([x, y, x + tw + 22, y + 34], radius=8, fill=color)
        d.text((x + 11, y + 4), label, font=f, fill=(12, 12, 12) if color in (WARN, AMBER) else (255, 255, 255))
    return bb


def minimap(pts, x0, w, h, dets=(), braking=None, span=120.0):
    im = Image.new("RGB", (w, h), PANEL)
    d = ImageDraw.Draw(im)
    pad = 16
    umax = 2.9

    def X(rel):
        return pad + rel / span * (w - 2 * pad)

    top = 30

    def Y(u):
        return top + (h - top - 26) / 2 - u / umax * ((h - top - 26) / 2)

    d.rectangle([X(0), Y(detect.ENV_HALF_U), X(span), Y(-detect.ENV_HALF_U)], fill=(18, 34, 58))
    sel = (pts[:, 0] > x0) & (pts[:, 0] < x0 + span)
    P = pts[sel][::3]
    for x, u in zip(X(P[:, 0] - x0), Y(P[:, 1])):
        d.point((x, u), fill=(70, 96, 130))
    for s in (-1, 1):
        d.line([X(0), Y(s * sim.RAIL_U), X(span), Y(s * sim.RAIL_U)], fill=(90, 110, 140), width=1)
    if braking:
        d.line([X(braking), top, X(braking), h - 26], fill=AMBER, width=2)
    for det in dets:
        col = {"brake": BRAKE, "warn": WARN}.get(det.decision, (150, 150, 150))
        d.rectangle([X(det.lo[0] - x0) - 3, Y(det.hi[1]) - 3, X(det.hi[0] - x0) + 3, Y(det.lo[1]) + 3], outline=col, width=3)
    for m in range(0, int(span), 20):
        d.text((X(m) + 3, h - 22), f"{m} м", font=font(15), fill=INK3)
    d.rectangle([0, 0, w, top - 4], fill=PANEL)
    d.text((pad, 5), "ВИД СВЕРХУ  ·  синяя полоса: габарит поезда  ·  жёлтая линия: тормозной путь", font=font(15, True), fill=INK3)
    return im


STATUS_TEXT = {"brake": ("ЭКСТРЕННОЕ ТОРМОЖЕНИЕ", BRAKE), "warn": ("ПРЕДУПРЕЖДЕНИЕ", WARN),
               "clear": ("ПУТЬ СВОБОДЕН", CLEAR)}
DEC_TEXT = {"brake": "в габарите, тормозим", "warn": "в габарите, дальше тормозного пути",
            "log": "вне габарита, в журнал"}


def hud(res, w, h, braking, speed=detect.SPEED_KMH):
    im = Image.new("RGB", (w, h), PANEL)
    d = ImageDraw.Draw(im)
    x = 34
    d.text((x, 26), "TUNNELGUARD", font=font(20, True), fill=INK3)
    d.text((x, 70), "СКОРОСТЬ", font=font(17, True), fill=INK3)
    d.text((x, 92), f"{speed:.0f} км/ч", font=font(46, display=True), fill=INK)
    d.text((x, 162), "ТОРМОЗНОЙ ПУТЬ", font=font(17, True), fill=INK3)
    d.text((x, 184), f"{braking:.0f} м", font=font(46, display=True), fill=AMBER)
    txt, col = STATUS_TEXT[res.status]
    sb = [x, 266, w - 34, 340]
    d.rounded_rectangle(sb, radius=12, fill=col)
    f = font(25, True)
    tw = d.textlength(txt, font=f)
    d.text(((sb[0] + sb[2] - tw) / 2, 288), txt, font=f, fill=(12, 12, 12) if col == WARN else (255, 255, 255))
    y = 372
    d.text((x, y), "ОБНАРУЖЕНО", font=font(17, True), fill=INK3)
    y += 30
    for det in res.detections[:4]:
        col = {"brake": BRAKE, "warn": WARN}.get(det.decision, (130, 138, 150))
        d.ellipse([x, y + 8, x + 14, y + 22], fill=col)
        t = f"{det.label_guess} · {det.distance:.1f} м"
        f21 = font(21, True)
        while d.textlength(t, font=f21) > w - x - 40 and f21.size > 15:
            f21 = font(f21.size - 1, True)
        d.text((x + 26, y), t, font=f21, fill=INK)
        sub = DEC_TEXT[det.decision] + (f" · {det.ttc:.1f} с" if det.in_envelope else "")
        d.text((x + 26, y + 28), sub, font=font(17), fill=INK2)
        y += 66
    if not res.detections:
        d.text((x, y), "ничего в габарите", font=font(20), fill=INK2)
    d.text((x, h - 44), f"обработка скана {res.latency_ms:.0f} мс", font=font(17), fill=INK3)
    return im, (sb[0], sb[1], sb[2] - sb[0], sb[3] - sb[1])


def compose_live(pts, x0, res, highlight=True, show_env=True, labels=True, braking=None, label_log=False):
    """Кадр «кабина + мини-карта + панель решения». Возвращает кадр и рамки для курсора."""
    braking = braking or detect.braking_distance()
    vw, vh = 1440, 690
    hl = {}
    if highlight:
        for det in res.detections:
            col = {"brake": BRAKE, "warn": WARN}.get(det.decision, (150, 150, 150))
            for j in det.idx:
                hl[int(j)] = col
    view, cam = driver_view(pts, x0, vw, vh, highlight=hl)
    if show_env:
        draw_envelope(view, cam, x0, braking)
    boxes = {}
    if highlight and labels:
        for i, det in enumerate(res.detections):
            if det.distance > 118:
                continue
            col = {"brake": BRAKE, "warn": WARN}.get(det.decision, (160, 160, 160))
            is_log = det.decision == "log"
            if is_log:
                lab = "вне габарита" if label_log else None
            else:
                lab = f"{det.label_guess} · {det.distance:.0f} м"
            bb = draw_box3d(view, cam, det.lo, det.hi, col, lab, dashed=is_log)
            boxes[i] = bb
    frame = Image.new("RGB", (W, H), BG)
    frame.paste(view, (0, 0))
    mm = minimap(pts, x0, vw, H - vh, res.detections if highlight else (), braking)
    frame.paste(mm, (0, vh))
    panel, sb = hud(res, W - vw, H, braking)
    frame.paste(panel, (vw, 0))
    status_box = [vw + sb[0], sb[1], sb[2], sb[3]]
    return frame, cam, boxes, status_box


def to_xywh(bb, margin=10):
    x0, y0, x1, y1 = bb
    return [int(x0 - margin), int(y0 - margin), int(x1 - x0 + 2 * margin), int(y1 - y0 + 2 * margin)]
