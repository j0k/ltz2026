# -*- coding: utf-8 -*-
"""Эксперимент 26.09: есть ли в снимках бедра сигнал укладки. Признаки ориентиров (dxaqc/hipfeat.py) и
логистическая регрессия, честная кросс-валидация по исследованиям. Итог: AUC ~0,61, F1 ~0,38 — на уровне
«пометить все бёдра бракованными» (0,39). Внешний вид (PCA миниатюр) — хуже, AUC 0,53–0,59.

    DXAQC_DATASETS=<папка наборов> .venv/bin/python scripts/hip_explore.py
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import datasets, analyze, quality as Q, hipfeat as HF
from dxaqc import io as dio
root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
images, _, _ = dio.collect(root)
rows = []
for img in images:
    reg = analyze.detect_region(img.pixels)[0]
    if not reg.startswith("hip"):
        continue
    study = img.rel_path.split(os.sep)[0]
    e = datasets.expert_for(labels, study, reg)
    f = HF.features(img.pixels, reg)
    if e is None or f is None:
        continue
    rows.append((study, img.sha, e, f))
print("бёдер с разметкой и признаками:", len(rows))
X = np.array([HF.vector(f) for *_, f in rows]); studies = [s for s, *_ in rows]
grp = Q.groups([dict(study=s, sha=h) for s, h, *_ in rows]); g = [grp[s] for s in studies]
targets = {"укладка": np.array([int("hip_positioning" in e["types"]) for _, _, e, _ in rows]),
           "итог бедра": np.array([int(e["bad"] == 1) for _, _, e, _ in rows]),
           "зона интереса": np.array([int("hip_roi" in e["types"]) for _, _, e, _ in rows])}
# сигнал отдельных признаков
y = targets["укладка"]
single = sorted(((Q.auc(X[:, j], y) or .5, n) for j, n in enumerate(HF.NAMES)), key=lambda t: -abs(t[0] - .5))
print("лучшие одиночные признаки (AUC, укладка):", [(n, round(a, 2)) for a, n in single[:8]])
rng = np.random.default_rng(3)
for name, y in targets.items():
    for l2 in (1.0, 10.0):
        aucs, f1s = [], []
        for _ in range(30):
            prob = np.zeros(len(y)); pred = np.zeros(len(y), int)
            for test in Q.folds(g, 5, rng):
                train = np.setdiff1d(np.arange(len(y)), test)
                m = HF.fit(X[train], y[train], l2=l2)
                ptr = HF.predict(m, X[train]); t = Q.best_threshold(ptr, y[train])
                prob[test] = HF.predict(m, X[test]); pred[test] = (prob[test] >= t).astype(int)
            aucs.append(Q.auc(prob, y)); f1s.append(Q.confusion(pred, y)["f1"])
        print(f"{name:14} (+{y.sum():2}/{len(y)}) l2={l2:>4}: AUC {np.mean(aucs):.2f} [{np.percentile(aucs,2.5):.2f}–{np.percentile(aucs,97.5):.2f}]"
              f"  F1 {np.mean(f1s):.2f} [{np.percentile(f1s,2.5):.2f}–{np.percentile(f1s,97.5):.2f}]")
