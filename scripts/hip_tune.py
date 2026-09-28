# -*- coding: utf-8 -*-
"""Подбор настроек ExtraTrees для бедра против переобучения (28.09): лист, глубина, доля признаков, веса классов.
Проверка — вероятности «вне фолда» (5 фолдов по исследованиям × повторы): ROC-AUC, F1 при лучшем пороге, Brier.

    ../.venv-ml/bin/python scripts/hip_tune.py <part 0|1> <out.json>
"""
import itertools, json, os, sys, time, warnings
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import quality as Q
warnings.filterwarnings("ignore")
z = np.load(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "_ml", "trees.npz"))
X, g, types = z["hip_X"], list(z["hip_group"]), list(z["hip_types"])
Y = {"bad": z["hip_bad"], "hip_positioning": z["hip_Y"][:, types.index("hip_positioning")], "hip_roi": z["hip_Y"][:, types.index("hip_roi")]}
grid = list(itertools.product([3, 6, 10, 16, 25], [None, 6, 3], ["sqrt", 0.35], ["balanced", None]))
part = int(sys.argv[1]); grid = grid[part::2]
res = []
for leaf, depth, feat, cw in grid:
    t0, row = time.time(), dict(leaf=leaf, depth=depth, feat=feat, cw=cw)
    for key, y in Y.items():
        A, F, B = [], [], []
        for r in range(3):
            prob = np.zeros(len(y))
            for test in Q.folds(g, 5, np.random.default_rng(100 + r)):
                tr = np.setdiff1d(np.arange(len(y)), test)
                m = ExtraTreesClassifier(n_estimators=150, min_samples_leaf=leaf, max_depth=depth, max_features=feat,
                                         class_weight=cw, n_jobs=-1, random_state=r).fit(X[tr], y[tr])
                prob[test] = m.predict_proba(X[test])[:, 1]
            A.append(Q.auc(prob, y)); B.append(float(np.mean((prob - y) ** 2)))
            F.append(Q.confusion((prob >= Q.best_threshold(prob, y)).astype(int), y)["f1"])
        row[key] = dict(auc=float(np.mean(A)), f1=float(np.mean(F)), brier=float(np.mean(B)))
    res.append(row)
    print(leaf, depth, feat, cw, {k: round(row[k]["auc"], 3) for k in Y}, f"{time.time() - t0:.0f}s", flush=True)
json.dump(res, open(sys.argv[2], "w"), indent=1)
