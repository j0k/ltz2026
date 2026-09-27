# -*- coding: utf-8 -*-
"""Квадрат ошибки (Brier) во время обучения: по числу деревьев и по объёму обучающих данных, по каждому типу нарушения.

Brier = среднее (p − y)², p — вероятность брака, y — оценка экспертов (0/1). Обучение и проверка — фолды по исследованиям
(общие снимки в одной группе), 5 фолдов × повторы. Бедро — ExtraTrees как в сервисе (scripts/train_hip.py);
позвоночник — правила, обучается только калибровка оценки правила в вероятность (логистическая по log оценки).
Ориентир — «константа»: всегда доля брака в обучающей части, её Brier ≈ p(1−p).

    ../.venv-ml/bin/python scripts/learning_curves.py <out.json>
"""
import json, os, sys
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import quality as Q

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML = os.path.join(os.path.dirname(ROOT), "data", "_ml")
FRACS = [0.2, 0.35, 0.5, 0.65, 0.8, 1.0]
TREES = [1, 2, 3, 5, 8, 12, 20, 30, 50, 80, 120, 200]
REPS = 10


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def et(seed):
    return ExtraTreesClassifier(n_estimators=200, min_samples_leaf=3, max_features="sqrt", class_weight="balanced",
                                n_jobs=-1, random_state=seed)


def platt(seed):
    return LogisticRegression(C=10.0, max_iter=1000)


def curves(X, y, g, make, trees=False):
    by_n = {f: dict(train=[], val=[], const=[]) for f in FRACS}
    by_t = {t: dict(train=[], val=[]) for t in TREES} if trees else None
    groups = np.array(g)
    for r in range(REPS):
        rng = np.random.default_rng(100 + r)
        for test in Q.folds(list(g), 5, rng):
            tr_all = np.setdiff1d(np.arange(len(y)), test)
            ug = np.unique(groups[tr_all])
            for f in FRACS:
                keep = set(rng.choice(ug, max(2, int(round(f * len(ug)))), replace=False))
                tr = np.array([i for i in tr_all if groups[i] in keep])
                if y[tr].min() == y[tr].max():
                    continue
                m = make(r).fit(X[tr], y[tr])
                by_n[f]["train"].append(brier(m.predict_proba(X[tr])[:, 1], y[tr]))
                by_n[f]["val"].append(brier(m.predict_proba(X[test])[:, 1], y[test]))
                by_n[f]["const"].append(brier(np.full(len(test), y[tr].mean()), y[test]))
                if trees and f == 1.0:
                    ptr = np.array([e.predict_proba(X[tr])[:, 1] for e in m.estimators_]).cumsum(0)
                    pte = np.array([e.predict_proba(X[test])[:, 1] for e in m.estimators_]).cumsum(0)
                    for t in TREES:
                        by_t[t]["train"].append(brier(ptr[t - 1] / t, y[tr]))
                        by_t[t]["val"].append(brier(pte[t - 1] / t, y[test]))
    agg = lambda d: {k: [float(np.mean(v)), float(np.percentile(v, 10)), float(np.percentile(v, 90))] for k, v in d.items() if v}
    return dict(size={str(f): agg(v) for f, v in by_n.items()}, trees={str(t): agg(v) for t, v in by_t.items()} if trees else None,
                n=int(len(y)), positives=int(y.sum()))


out = {}
# позвоночник: оценки правил из кэша признаков (версия правил 0.5.3 = 0.5.4)
cache = json.load(open(os.path.join(ROOT, "results", "features_cache.json")))["images"]
sp = [im for im in cache if im["region"] == "lumbar_spine" and im.get("expert") and im["expert"]["bad"] in (0, 1) and "scores" in im]
grp = Q.groups(sp); gs = [grp[im["study"]] for im in sp]
for crit, title in (("overall", "Позвоночник: итог"), ("coverage", "Охват"), ("axis_tilt", "Наклон оси"), ("artifact", "Посторонние предметы")):
    X = np.log(np.array([[max(im["scores"][crit], 1e-3)] for im in sp]))
    y = np.array([int(im["expert"]["bad"] == 1) if crit == "overall" else int(crit in im["expert"]["types"]) for im in sp])
    out[crit] = dict(title=title, model="правило + калибровка", **curves(X, y, gs, platt))
    print(title, "готово", flush=True)
z = np.load(os.path.join(ML, "trees.npz"))
X, g = z["hip_X"], list(z["hip_group"])
types = list(z["hip_types"])
for key, title, y in (("hip_bad", "Бедро: итог", z["hip_bad"]),
                      ("hip_positioning", "Укладка бедра", z["hip_Y"][:, types.index("hip_positioning")]),
                      ("hip_roi", "Поля зоны интереса", z["hip_Y"][:, types.index("hip_roi")])):
    out[key] = dict(title=title, model="ExtraTrees", **curves(X, np.asarray(y), g, et, trees=True))
    print(title, "готово", flush=True)
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
