# -*- coding: utf-8 -*-
"""Эксперимент 26.09: широкий поиск признаков укладки бедра (края кадра, контраст, профили), честная проверка.

    DXAQC_DATASETS=<папка наборов> .venv/bin/python scripts/hip_scan.py
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import analyze as AN, datasets, quality as Q, hipfeat as HF
from dxaqc.hipmodel import features as scan  # признаки переехали в продукт (#129)
from dxaqc import io as dio
from dxaqc.atlas import otsu


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
