# -*- coding: utf-8 -*-
"""Эксперимент 26.09: признаки посторонних предметов и оси позвоночника, проверка честной кросс-валидацией.

    DXAQC_DATASETS=<папка наборов> .venv/bin/python scripts/spine_explore.py
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import analyze as AN, datasets, quality as Q
from dxaqc import io as dio


def spine_features(a):
    h, w = a.shape
    af = a.astype(np.float32)
    b = AN._blur(af, 7)
    ys, xs = AN._spine_centerline(b)
    f = {}
    # --- ось: хорда по третям (как сейчас), прямая по всей линии, кривизна
    t = len(ys) // 3
    chord = np.degrees(np.arctan((np.median(xs[-t:]) - np.median(xs[:t])) / max(np.median(ys[-t:]) - np.median(ys[:t]), 1)))
    k1 = np.polyfit(ys, xs, 1); k2 = np.polyfit(ys, xs, 2)
    f["angle_chord"] = abs(chord)
    f["angle_fit"] = abs(np.degrees(np.arctan(k1[0])))
    lin_res = xs - np.polyval(k1, ys)
    f["curve_dev"] = float(np.abs(lin_res).max()) / w               # изгиб: отклонение линии от прямой
    f["curve_quad"] = abs(float(k2[0])) * (h ** 2) / w
    f["tilt_minus_curve"] = f["angle_fit"] - 40 * f["curve_dev"]
    f["centre_offset"] = abs(float(np.median(xs)) - w / 2) / w
    # --- посторонние предметы: яркое относительно позвонков и маленькие резкие пятна где угодно
    axis_x = np.polyval(k1, np.arange(h))
    band = np.abs(np.arange(w)[None, :] - axis_x[:, None]) <= 45
    rows = slice(int(h * 0.1), int(h * 0.9))
    spine_px = af[rows][band[rows]]
    ref = float(np.percentile(spine_px, 95)) if spine_px.size else 200.0
    bg = AN._blur(af, 21)
    top = af - bg                                                    # «цилиндр»: насколько пиксель ярче своего окружения
    f["tophat_max"] = float(np.percentile(top, 99.95))
    f["tophat_in_band"] = float(np.percentile(top[band], 99.9)) if band.any() else 0.0
    f["tophat_out_band"] = float(np.percentile(top[~band], 99.9)) if (~band).any() else 0.0
    for k in (20, 35, 50):
        f[f"tophat_px_{k}"] = float((top > k).sum())
    for r in (1.05, 1.15, 1.3):
        f[f"above_spine_{r}"] = float((af > ref * r).sum())
    f["max_over_spine"] = float(af.max()) / max(ref, 1)
    f["bright_out_old"] = float(((af >= 240) & ~band).sum())
    gy, gx = np.gradient(AN._blur(af, 3))
    grad = np.hypot(gx, gy)
    f["sharp_edges"] = float((grad > np.percentile(grad, 99.5) * 1.5).sum())
    f["grad_max"] = float(np.percentile(grad, 99.9))
    return f


root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
images, _, _ = dio.collect(root)
rows = {}
for img in images:
    if AN.detect_region(img.pixels)[0] != "lumbar_spine":
        continue
    study = img.rel_path.split(os.sep)[0]
    e = datasets.expert_for(labels, study, "lumbar_spine")
    if e is None:
        continue
    f = spine_features(img.pixels)
    r = rows.setdefault(study, dict(f={}, e=e))
    for k, v in f.items():
        r["f"][k] = max(r["f"].get(k, -np.inf), v)
studies = sorted(rows); names = list(rows[studies[0]]["f"])
X = np.array([[rows[s]["f"][n] for n in names] for s in studies])
Y = {c: np.array([int(c in rows[s]["e"]["types"]) for s in studies]) for c in ("artifact", "axis_tilt", "coverage")}
Y["overall"] = np.array([int(rows[s]["e"]["bad"] == 1) for s in studies])
print(f"исследований позвоночника: {len(studies)}")
for c in ("artifact", "axis_tilt"):
    y = Y[c]
    res = sorted(((Q.auc(X[:, j], y) or .5, n) for j, n in enumerate(names)), key=lambda t: -t[0])
    print(f"\n{c} (+{y.sum()}): одиночные признаки, ROC-AUC")
    rng = np.random.default_rng(1)
    for a, n in res[:7]:
        j = names.index(n)
        boots = [Q.auc(X[i, j], y[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(500))]
        lo, hi = Q.ci(boots)
        print(f"  {n:20} {a:.2f} [{lo:.2f}–{hi:.2f}]")


# ------------------------------------------------------------------ честная проверка: пороги только внутри фолдов
def cv_combo(feats, reps=50, seed=11):
    """feats: критерий → индекс признака. Каждый порог подбирается на обучающих фолдах по своему критерию,
    итог позвоночника — «хотя бы одно нарушение». F1 по каждому критерию и итогу — на отложенных фолдах."""
    rng = np.random.default_rng(seed); n = len(studies); g = list(range(n))
    out = {c: [] for c in list(feats) + ["overall"]}
    for _ in range(reps):
        pred = {c: np.zeros(n, int) for c in feats}
        for test in Q.folds(g, 5, rng):
            tr = np.setdiff1d(np.arange(n), test)
            for c, j in feats.items():
                t = Q.best_threshold(X[tr, j], Y[c][tr]); pred[c][test] = (X[test, j] >= t).astype(int)
        for c in feats:
            out[c].append(Q.confusion(pred[c], Y[c])["f1"])
        overall = np.max(np.vstack([pred[c] for c in feats]), axis=0)
        out["overall"].append(Q.confusion(overall, Y["overall"])["f1"])
    return {c: (np.mean(v), np.percentile(v, 2.5), np.percentile(v, 97.5)) for c, v in out.items()}


idx = {n: i for i, n in enumerate(names)}
coverage_col = None
# охват — тем же признаком, что сейчас в сервисе: минимальная яркость нижних углов (чем темнее, тем хуже)
cov = []
for s in studies:
    pass
print("\nчестная кросс-валидация, 5 фолдов × 50 повторов, пороги подбираются только на обучающих фолдах:")
for label, art in (("старый детектор", "bright_out_old"), ("новый: контраст вне столба", "tophat_out_band")):
    r = cv_combo({"artifact": idx[art], "axis_tilt": idx["angle_chord"]})
    print(f"  {label:28} посторонние F1 {r['artifact'][0]:.2f} [{r['artifact'][1]:.2f}–{r['artifact'][2]:.2f}] · "
          f"ось F1 {r['axis_tilt'][0]:.2f} · итог (без охвата) F1 {r['overall'][0]:.2f} [{r['overall'][1]:.2f}–{r['overall'][2]:.2f}]")
j = idx["tophat_out_band"]
print("  контраст вне столба: у экспертов «есть предмет» медиана", round(float(np.median(X[Y['artifact'] == 1, j])), 1),
      "· «нет» медиана", round(float(np.median(X[Y['artifact'] == 0, j])), 1), "· порог по всему набору",
      round(Q.best_threshold(X[:, j], Y["artifact"]), 1))
