# -*- coding: utf-8 -*-
"""Предсказания «вне фолда» текущей версии для фитнес-функции (#135): строка на снимок, формат dxaqc/fitness.py.

Позвоночник — правила с порогами по умолчанию (они совпали с подобранными кросс-валидацией, см. results/quality_cv.json),
оценка брака — dxaqc.quality.spine_scores. Бедро — ExtraTrees из scripts/train_hip.py, 5 фолдов по исследованиям,
порог F1 внутри обучающей части; вероятности и вердикты — только для снимков тестового фолда.

    DXAQC_DATASETS=<папка наборов> ../.venv-ml/bin/python scripts/baseline_oof.py <out.csv> [--seed 100]
"""
import argparse, csv, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dxaqc import analyze as AN, datasets, hipmodel as HM, io as dio, params as P, quality as Q
import train_hip as T

ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--seed", type=int, default=100)
a = ap.parse_args()
p = P.normalize(None)
root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
images, _, _ = dio.collect(root)
rows, hips = [], []
for img in images:
    res = AN.analyze(img.pixels, p)
    reg = res["region"]; study = img.rel_path.split(os.sep)[0]
    e = datasets.expert_for(labels, study, reg)
    if e is None or e["bad"] not in (0, 1) or reg not in ("lumbar_spine", "hip_left", "hip_right"):
        continue
    r = dict(study=study, sha=img.sha, region=reg, y_bad=int(e["bad"] == 1), status="Success", seconds="")
    for t in ("coverage", "axis_tilt", "artifact", "hip_positioning", "hip_roi"):
        r[f"y_{t}"] = int(t in e["types"]) if (t.startswith("hip") == reg.startswith("hip")) else ""
    if reg == "lumbar_spine":
        r["score"] = Q.spine_scores(res["metrics"], p)["overall"]
        r["pred"] = int(res["quality_class"] == 1)
        for t in ("coverage", "axis_tilt", "artifact"):
            r[f"pred_{t}"] = int(t in res["violations"])
        rows.append(r)
    else:
        r["_f"] = HM.features(img.pixels, reg); hips.append(r)

names = sorted({n for r in hips for n in r["_f"]})
X = np.array([[r["_f"].get(n, np.nan) for n in names] for r in hips], float)
X = np.where(np.isnan(X), np.nanmedian(X, 0), X)
grp = Q.groups([dict(study=r["study"], sha=r["sha"]) for r in hips]); g = [grp[r["study"]] for r in hips]
ys = {"bad": np.array([r["y_bad"] for r in hips]), "hip_positioning": np.array([r["y_hip_positioning"] for r in hips]),
      "hip_roi": np.array([r["y_hip_roi"] for r in hips])}
prob = {k: np.zeros(len(hips)) for k in ys}; pred = {k: np.zeros(len(hips), int) for k in ys}
for test in Q.folds(g, 5, np.random.default_rng(a.seed)):
    tr = np.setdiff1d(np.arange(len(hips)), test)
    for k, y in ys.items():
        thr = Q.best_threshold(T.oof(X[tr], y[tr], a.seed), y[tr])
        prob[k][test] = T.model(a.seed).fit(X[tr], y[tr]).predict_proba(X[test])[:, 1]
        pred[k][test] = (prob[k][test] >= thr).astype(int)
for i, r in enumerate(hips):
    r.pop("_f"); r["score"] = round(float(prob["bad"][i]), 4); r["pred"] = int(pred["bad"][i])
    # тип — как в сервисе: только у брака; сработавшие модели типов, иначе более вероятный
    if r["pred"]:
        ratio = {t: prob[t][i] for t in ("hip_positioning", "hip_roi")}
        on = [t for t in ratio if pred[t][i]] or [max(ratio, key=ratio.get)]
    else:
        on = []
    for t in ("hip_positioning", "hip_roi"):
        r[f"pred_{t}"] = int(t in on)
    rows.append(r)
cols = ["study", "sha", "region", "y_bad", "score", "pred", "status", "seconds"] + \
       [f"{k}_{t}" for t in ("coverage", "axis_tilt", "artifact", "hip_positioning", "hip_roi") for k in ("y", "pred")]
with open(a.out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print(f"{a.out}: {len(rows)} строк (позвоночник {sum(r['region'] == 'lumbar_spine' for r in rows)}, бедро {len(hips)})")
