# -*- coding: utf-8 -*-
"""Обучение модели качества бедра (#129): ExtraTrees по 47 признакам dxaqc.hipmodel, выгрузка весов в npz.

Проверка честная: 5 фолдов по группам исследований (общие снимки — в одной группе) × повторы; порог F1 внутри
обучающей части. Порог рабочей модели — по вероятностям «вне фолда» на всём наборе. Итоговые модели обучаются на всех
размеченных снимках бедра; предсказание numpy-кодом из dxaqc/hipmodel.py сверяется с sklearn.

    DXAQC_DATASETS=<папка наборов> ../.venv-ml/bin/python scripts/train_hip.py [--reps 5] [--out dxaqc/models/hip_trees.npz]
"""
import argparse, json, os, sys, time, warnings
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.model_selection import StratifiedKFold
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import __version__, analyze as AN, datasets, hipmodel as HM, io as dio, quality as Q

warnings.filterwarnings("ignore")
PARAMS = dict(n_estimators=200, min_samples_leaf=3, max_features="sqrt", class_weight="balanced")


def model(seed=0):
    return ExtraTreesClassifier(**PARAMS, n_jobs=-1, random_state=seed)


def oof(X, y, seed, k=3):
    out = np.zeros(len(y))
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=seed).split(X, y):
        out[te] = model(seed).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return out


def metrics(pred, prob, y):
    c = Q.confusion(pred, y)
    sens = c["tp"] / max(c["tp"] + c["fn"], 1); spec = c["tn"] / max(c["tn"] + c["fp"], 1)
    return dict(auc=Q.auc(prob, y), f1=c["f1"], sensitivity=sens, specificity=spec, balanced_accuracy=(sens + spec) / 2)


def cross_validate(X, y, g, reps):
    """Внешние фолды по группам; внутри обучающей части — порог. Возвращает средние и 95% интервалы по повторам,
    а также средние вероятности «вне фолда» для выбора рабочего порога."""
    runs, probs = [], []
    for r in range(reps):
        rng = np.random.default_rng(100 + r); prob = np.zeros(len(y)); pred = np.zeros(len(y), int)
        for test in Q.folds(list(g), 5, rng):
            tr = np.setdiff1d(np.arange(len(y)), test)
            thr = Q.best_threshold(oof(X[tr], y[tr], r), y[tr])
            prob[test] = model(r).fit(X[tr], y[tr]).predict_proba(X[test])[:, 1]
            pred[test] = (prob[test] >= thr).astype(int)
        runs.append(metrics(pred, prob, y)); probs.append(prob)
    out = {k: dict(mean=float(np.mean([m[k] for m in runs])), ci=[float(v) for v in Q.ci([m[k] for m in runs])])
           for k in runs[0]}
    return out, np.mean(probs, 0)


def export(clf) -> list:
    trees = []
    for est in clf.estimators_:
        t = est.tree_
        v = t.value[:, 0, :]
        trees.append(dict(feature=t.feature.astype(np.int32), threshold=t.threshold.astype(np.float64),
                          left=t.children_left.astype(np.int32), right=t.children_right.astype(np.int32),
                          value=(v[:, 1] / np.maximum(v.sum(1), 1e-12)).astype(np.float64)))
    return trees


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default=HM.MODEL_PATH)
    a = ap.parse_args()
    t0 = time.time()
    root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
    images, _, _ = dio.collect(root)
    recs = []
    for img in images:
        reg = AN.detect_region(img.pixels)[0]
        if not reg.startswith("hip"):
            continue
        study = img.rel_path.split(os.sep)[0]; e = datasets.expert_for(labels, study, reg)
        if e is None or e["bad"] not in (0, 1):
            continue
        recs.append((study, img.sha, e, HM.features(img.pixels, reg)))
    names = sorted({n for r in recs for n in r[3]})
    X = np.array([[r[3].get(n, np.nan) for n in names] for r in recs], float)
    med = np.nanmedian(X, 0)
    X = np.where(np.isnan(X), med, X)
    grp = Q.groups([dict(study=s, sha=h) for s, h, *_ in recs]); g = np.array([grp[s] for s, *_ in recs])
    ys = {"bad": np.array([int(r[2]["bad"] == 1) for r in recs])}
    for t in ("hip_positioning", "hip_roi"):
        ys[t] = np.array([int(t in r[2]["types"]) for r in recs])
    print(f"бёдер {len(recs)}, признаков {len(names)}, неполных снимков {int(np.isnan([[r[3].get(n, np.nan) for n in names] for r in recs]).any(1).sum())}")

    meta = dict(version=__version__, trained=time.strftime("%Y-%m-%d"), algorithm="ExtraTreesClassifier", params=PARAMS,
                features=names, medians=[float(v) for v in med], images=len(recs), studies=len(set(grp.values())),
                thresholds={}, positives={}, cv={}, method=dict(k=5, repeats=a.reps, level="study", threshold="F1 внутри обучающей части"))
    arrays = {}
    for t, y in ys.items():
        cv, prob = cross_validate(X, y, g, a.reps)
        thr = float(Q.best_threshold(prob, y))
        meta["thresholds"][t] = thr; meta["positives"][t] = int(y.sum()); meta["cv"][t] = cv
        clf = model(0).fit(X, y)
        trees = export(clf)
        arrays[f"{t}_n_trees"] = np.array(len(trees))
        for i, tr in enumerate(trees):
            for k, v in tr.items():
                arrays[f"{t}_{i}_{k}"] = v
        # сверка numpy-предсказания с sklearn
        ref = clf.predict_proba(X)[:, 1]
        mine = np.array([HM._forest_proba([tuple(tr[k] for k in ("feature", "threshold", "left", "right", "value")) for tr in trees], x) for x in X])
        assert np.abs(ref - mine).max() < 1e-9, np.abs(ref - mine).max()
        print(f"{t:16} брак {y.sum():3}  AUC {cv['auc']['mean']:.2f} [{cv['auc']['ci'][0]:.2f}–{cv['auc']['ci'][1]:.2f}]  "
              f"F1 {cv['f1']['mean']:.2f}  чувств. {cv['sensitivity']['mean']:.2f}  спец. {cv['specificity']['mean']:.2f}  порог {thr:.3f}")
    np.savez_compressed(a.out, meta=np.array(json.dumps(meta, ensure_ascii=False)), **arrays)
    print(f"веса: {a.out} ({os.path.getsize(a.out) / 1e3:.0f} КБ), {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
