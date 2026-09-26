# -*- coding: utf-8 -*-
"""Эксперимент 26.09: широкий поиск признаков укладки бедра (края кадра, контраст, профили), честная проверка.

    DXAQC_DATASETS=<папка наборов> .venv/bin/python scripts/hip_scan.py
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import analyze as AN, datasets, quality as Q, hipfeat as HF
from dxaqc import io as dio
from dxaqc.atlas import otsu


def scan(a, region):
    if region == "hip_left":
        a = a[:, ::-1]                                  # таз всегда справа, наружная сторона — слева
    h, w = a.shape
    af = a.astype(np.float32)
    b = AN._blur(af, 5)
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
    local = af - AN._blur(af, 21)
    f["contrast_p999"] = float(np.percentile(local, 99.9))
    gy, gx = np.gradient(AN._blur(af, 3)); g = np.hypot(gx, gy)
    f["grad_p99"] = float(np.percentile(g, 99))
    f["mean"] = float(af.mean()) / 255; f["bone_mean"] = float(af[bone].mean()) / 255 if bone.any() else 0
    prof = bone.mean(1)                                 # профиль ширины кости по строкам
    f["prof_max_row"] = float(np.argmax(prof)) / h; f["prof_std"] = float(prof.std())
    hf = HF.features(a if region == "hip_right" else a[:, ::-1], region)
    if hf:
        f.update({f"geo_{k}": v for k, v in hf.items()})
    return f


root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
images, _, _ = dio.collect(root)
recs = []
for img in images:
    reg = AN.detect_region(img.pixels)[0]
    if not reg.startswith("hip"):
        continue
    study = img.rel_path.split(os.sep)[0]; e = datasets.expert_for(labels, study, reg)
    if e is None:
        continue
    recs.append((study, img.sha, e, scan(img.pixels, reg)))
names = sorted(set.intersection(*[set(r[3]) for r in recs]))
X = np.array([[r[3][n] for n in names] for r in recs])
y = np.array([int("hip_positioning" in r[2]["types"]) for r in recs])
yb = np.array([int(r[2]["bad"] == 1) for r in recs])
print(f"бёдер: {len(recs)}, признаков: {len(names)}, укладка +{y.sum()}, итог +{yb.sum()}")
aucs = sorted(((max(Q.auc(X[:, j], y), 1 - Q.auc(X[:, j], y)), n, Q.auc(X[:, j], y) > 0.5) for j, n in enumerate(names)), reverse=True)
print("лучшие одиночные признаки (укладка, AUC; ↑ — чем больше, тем хуже):")
for a, n, up in aucs[:10]:
    print(f"  {n:24} {a:.2f} {'↑' if up else '↓'}")
grp = Q.groups([dict(study=s, sha=h) for s, h, *_ in recs]); g = [grp[s] for s, *_ in recs]


def cv(cols, yy, l2=10.0, reps=40, seed=4, select=None):
    """Логистическая регрессия; при select=k отбор k лучших признаков по AUC внутри обучающих фолдов (без подглядывания)."""
    rng = np.random.default_rng(seed); A, F = [], []
    for _ in range(reps):
        prob = np.zeros(len(yy)); pred = np.zeros(len(yy), int)
        for test in Q.folds(g, 5, rng):
            tr = np.setdiff1d(np.arange(len(yy)), test)
            c = cols
            if select:
                sc = [(abs((Q.auc(X[tr, j], yy[tr]) or .5) - .5), j) for j in cols]
                c = [j for _, j in sorted(sc, reverse=True)[:select]]
            m = HF.fit(X[tr][:, c], yy[tr], l2=l2); t = Q.best_threshold(HF.predict(m, X[tr][:, c]), yy[tr])
            prob[test] = HF.predict(m, X[test][:, c]); pred[test] = (prob[test] >= t).astype(int)
        A.append(Q.auc(prob, yy)); F.append(Q.confusion(pred, yy)["f1"])
    return np.mean(A), np.percentile(A, 2.5), np.percentile(A, 97.5), np.mean(F)


allc = list(range(len(names)))
print(f"\nбазовая линия «все бракованные»: F1 укладки {2 * y.mean() / (1 + y.mean()):.2f}")
for k in (3, 5, 8, None):
    a, lo, hi, f1 = cv(allc, y, select=k)
    print(f"укладка, {'все признаки' if k is None else f'{k} лучших (отбор внутри фолдов)':32}: AUC {a:.2f} [{lo:.2f}–{hi:.2f}] F1 {f1:.2f}")
a, lo, hi, f1 = cv(allc, yb, select=5)
print(f"итог бедра, 5 лучших                                : AUC {a:.2f} [{lo:.2f}–{hi:.2f}] F1 {f1:.2f}")
