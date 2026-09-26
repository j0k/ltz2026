# -*- coding: utf-8 -*-
"""Честная проверка эмбеддингов предобученных сетей (исследование 26.09).

Для каждой сети и критерия: стандартизация и PCA только на обучающих фолдах, логистическая регрессия,
порог по F1 на обучающих фолдах; 5 фолдов × N повторов по группам исследований.

    ../.venv-ml/bin/python scripts/ml_eval.py [--reps 20]
"""
import argparse, glob, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import quality as Q, hipfeat as HF

ML = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "_ml")


def load():
    m = np.load(os.path.join(ML, "meta.npz"), allow_pickle=True)
    meta = {k: m[k] for k in m.files}
    embs = {os.path.basename(p)[4:-4]: np.load(p)["emb"] for p in sorted(glob.glob(os.path.join(ML, "emb_*.npz")))}
    return meta, embs


def targets(meta):
    types = [set(t.split("|")) if t else set() for t in meta["types"]]
    hip = np.array([r.startswith("hip") and b >= 0 for r, b in zip(meta["region"], meta["bad"])])
    spine = np.array([r == "lumbar_spine" and b >= 0 for r, b in zip(meta["region"], meta["bad"])])
    return {
        "бедро: укладка": (hip, np.array([int("hip_positioning" in t) for t in types])),
        "бедро: итог": (hip, np.array([int(b == 1) for b in meta["bad"]])),
        "позвоночник: итог": (spine, np.array([int(b == 1) for b in meta["bad"]])),
        "позвоночник: предметы": (spine, np.array([int("artifact" in t) for t in types])),
        "позвоночник: ось": (spine, np.array([int("axis_tilt" in t) for t in types])),
    }


def cv(X, y, groups, k=16, l2=10.0, reps=20, seed=5):
    rng = np.random.default_rng(seed); A, F, P = [], [], np.zeros(len(y))
    for _ in range(reps):
        prob = np.zeros(len(y)); pred = np.zeros(len(y), int)
        for test in Q.folds(groups, 5, rng):
            tr = np.setdiff1d(np.arange(len(y)), test)
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
            Ztr, Zte = (X[tr] - mu) / sd, (X[test] - mu) / sd
            if k and k < Ztr.shape[1]:
                _, _, Vt = np.linalg.svd(Ztr - Ztr.mean(0), full_matrices=False)
                c = Ztr.mean(0); Ztr, Zte = (Ztr - c) @ Vt[:k].T, (Zte - c) @ Vt[:k].T
            m = HF.fit(Ztr, y[tr], l2=l2); t = Q.best_threshold(HF.predict(m, Ztr), y[tr])
            prob[test] = HF.predict(m, Zte); pred[test] = (prob[test] >= t).astype(int)
        A.append(Q.auc(prob, y)); F.append(Q.confusion(pred, y)["f1"]); P += prob / reps
    return np.mean(A), np.percentile(A, 2.5), np.percentile(A, 97.5), np.mean(F), P


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--reps", type=int, default=20); a = ap.parse_args()
    meta, embs = load()
    grp = Q.groups([dict(study=s, sha=h) for s, h in zip(meta["study"], meta["sha"])])
    print("модели:", ", ".join(f"{n} {e.shape[1]}" for n, e in embs.items()))
    for tname, (mask, y_all) in targets(meta).items():
        y = y_all[mask]; g = [grp[s] for s in meta["study"][mask]]
        base = 2 * y.mean() / (1 + y.mean())
        print(f"\n{tname}: {mask.sum()} снимков, нарушений {y.sum()} · «все бракованные» F1 {base:.2f}")
        for name, E in embs.items():
            best = None
            for k in (8, 16, 32):
                for l2 in (10.0, 100.0):
                    r = cv(E[mask], y, g, k=k, l2=l2, reps=a.reps)
                    if best is None or r[0] > best[0][0]:
                        best = (r, k, l2)
            (auc, lo, hi, f1, _), k, l2 = best
            print(f"  {name:14} AUC {auc:.2f} [{lo:.2f}–{hi:.2f}] F1 {f1:.2f}  (PCA {k}, L2 {l2:g})")
