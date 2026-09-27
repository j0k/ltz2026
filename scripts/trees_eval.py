# -*- coding: utf-8 -*-
"""Эксперимент 27.09 (#129): деревья решений и их каскады против логистической регрессии, честная проверка.

Модели: одно дерево; случайный лес и ExtraTrees; градиентный бустинг (последовательный каскад деревьев, каждое
исправляет ошибки предыдущих); каскадный лес в духе gcForest (Zhou, Feng 2017: уровни лесов, каждый следующий
получает признаки и вероятности предыдущего, глубина растёт, пока помогает); отсеивающий каскад в духе Viola–Jones
(первая ступень с полнотой ≥ 95% отсеивает явно годные, вторая решает по остальным).
Проверка: 5 фолдов по группам исследований × повторы; порог по F1 — на внутренней кросс-валидации обучающей части.

    ../.venv-ml/bin/python scripts/trees_eval.py [--reps 10]
"""
import argparse, os, sys, time, warnings
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.decomposition import PCA
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dxaqc import quality as Q

warnings.filterwarnings("ignore")
ML = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "_ml")
BAL = "balanced"


def forest(kind, n=300, seed=0):
    C = RandomForestClassifier if kind == "rf" else ExtraTreesClassifier
    return C(n_estimators=n, min_samples_leaf=3, max_features="sqrt", class_weight=BAL, n_jobs=-1, random_state=seed)


def inner_oof(model, X, y, k=3, seed=0):
    """Вероятности «вне фолда» внутри обучающей части: по ним и порог, и входы следующего уровня каскада."""
    out = np.zeros(len(y))
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=seed).split(X, y):
        out[te] = clone(model).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return out


class CascadeForest(ClassifierMixin, BaseEstimator):
    """Каскадный лес: на уровне 2 RF + 2 ExtraTrees; вход уровня = исходные признаки + вероятности прошлого уровня."""
    def __init__(self, max_levels=4, n=150, seed=0):
        self.max_levels, self.n, self.seed = max_levels, n, seed

    def _level(self, lv):
        return [forest(k, self.n, self.seed + 10 * lv + i) for i, k in enumerate(("rf", "rf", "et", "et"))]

    def fit(self, X, y):
        self.levels, aug, best = [], X, -1
        for lv in range(self.max_levels):
            ms = self._level(lv)
            oof = np.column_stack([inner_oof(m, aug, y, seed=self.seed + lv) for m in ms])
            score = Q.auc(oof.mean(1), y) or 0.5
            if score <= best + 1e-3:                       # уровень не помог — каскад останавливается
                break
            self.levels.append([clone(m).fit(aug, y) for m in ms]); best = score
            self.oof_ = oof.mean(1)                        # честные вероятности обучающей части — для порога
            aug = np.hstack([X, oof])
        return self

    def predict_proba(self, X):
        aug = X
        for ms in self.levels:
            p = np.column_stack([m.predict_proba(aug)[:, 1] for m in ms])
            aug = np.hstack([X, p])
        s = p.mean(1)
        return np.column_stack([1 - s, s])


class RejectCascade(ClassifierMixin, BaseEstimator):
    """Отсеивающий каскад: неглубокое дерево с полнотой ≥ 95% отсеивает явно годные, лес решает по остальным."""
    def __init__(self, seed=0):
        self.seed = seed

    def fit(self, X, y):
        self.s1 = DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, class_weight=BAL, random_state=self.seed)
        oof = inner_oof(self.s1, X, y, seed=self.seed)
        pos = np.sort(oof[y == 1])
        self.t1 = pos[int(0.05 * len(pos))] if len(pos) else 0.0
        self.s1.fit(X, y)
        keep = oof >= self.t1
        self.s2 = forest("rf", 300, self.seed).fit(X[keep], y[keep]) if len(set(y[keep])) > 1 else None
        return self

    def predict_proba(self, X):
        p1 = self.s1.predict_proba(X)[:, 1]
        s = np.where(p1 >= self.t1, 0.5 + 0.5 * (self.s2.predict_proba(X)[:, 1] if self.s2 else 1), 0.5 * p1)
        return np.column_stack([1 - s, s])


def models(seed):
    return {
        "логистическая регрессия": make_pipeline(StandardScaler(), LogisticRegression(C=0.1, class_weight=BAL, max_iter=2000)),
        "одно дерево, глубина 3": DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, class_weight=BAL, random_state=seed),
        "случайный лес": forest("rf", 300, seed),
        "ExtraTrees": forest("et", 300, seed),
        "градиентный бустинг": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=1.0,
                                                               min_samples_leaf=8, class_weight=BAL, random_state=seed),
        "каскадный лес (gcForest)": CascadeForest(seed=seed),
        "отсеивающий каскад (Viola–Jones)": RejectCascade(seed=seed),
    }


def evaluate(name_filter, X, y, g, reps, pca=None):
    res = {}
    for name in models(0):
        if name_filter and not any(f in name for f in name_filter):
            continue
        A, F, t0 = [], [], time.time()
        for r in range(reps):
            rng = np.random.default_rng(100 + r); prob = np.zeros(len(y)); pred = np.zeros(len(y), int)
            for test in Q.folds(list(g), 5, rng):
                tr = np.setdiff1d(np.arange(len(y)), test)
                Xtr, Xte = X[tr], X[test]
                if pca:                                    # эмбеддинги: сжатие только по обучающей части
                    sc = StandardScaler().fit(Xtr[:, pca:]); pc = PCA(16, random_state=r).fit(sc.transform(Xtr[:, pca:]))
                    Xtr = np.hstack([Xtr[:, :pca], pc.transform(sc.transform(Xtr[:, pca:]))])
                    Xte = np.hstack([Xte[:, :pca], pc.transform(sc.transform(Xte[:, pca:]))])
                m = models(r)[name]
                if isinstance(m, CascadeForest):
                    m.fit(Xtr, y[tr]); thr = Q.best_threshold(m.oof_, y[tr])
                else:
                    thr = Q.best_threshold(inner_oof(m, Xtr, y[tr], seed=r), y[tr]); m.fit(Xtr, y[tr])
                prob[test] = m.predict_proba(Xte)[:, 1]; pred[test] = (prob[test] >= thr).astype(int)
            A.append(Q.auc(prob, y)); F.append(Q.confusion(pred, y)["f1"])
        res[name] = (np.mean(A), np.percentile(A, 2.5), np.percentile(A, 97.5), np.mean(F), time.time() - t0)
        a, lo, hi, f, s = res[name]
        print(f"  {name:34} AUC {a:.2f} [{lo:.2f}–{hi:.2f}]  F1 {f:.2f}   {s:5.0f} с", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--only", nargs="*", help="части названий моделей")
    ap.add_argument("--task", nargs="*", default=["hip", "spine"])
    a = ap.parse_args()
    z = np.load(os.path.join(ML, "trees.npz"))
    for part in a.task:
        X, g, types, Y, bad = (z[f"{part}_{k}"] for k in ("X", "group", "types", "Y", "bad"))
        targets = [(f"{part}: итог", bad)] + [(f"{part}: {t}", Y[:, i]) for i, t in enumerate(types)]
        for title, y in targets:
            triv = 2 * y.mean() / (1 + y.mean())
            print(f"\n{title}: {len(y)} снимков, брак {y.sum()}, признаков {X.shape[1]}; F1 «всё брак» {triv:.2f}", flush=True)
            evaluate(a.only, X, y, g, a.reps)
        if part == "hip" and os.path.exists(os.path.join(ML, "emb_dinov2-small.npz")):
            m = np.load(os.path.join(ML, "meta.npz"), allow_pickle=True); e = np.load(os.path.join(ML, "emb_dinov2-small.npz"))["emb"]
            idx = {s: i for i, s in enumerate(m["sha"])}
            XE = np.hstack([X, e[[idx[s] for s in z["hip_sha"]]]])
            print(f"\nhip: итог, признаки + DINOv2-small (PCA 16 внутри фолда)", flush=True)
            evaluate(a.only, XE, bad, g, a.reps, pca=X.shape[1])


if __name__ == "__main__":
    main()
