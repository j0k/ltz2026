# -*- coding: utf-8 -*-
"""Плагин hip_trees: дообучение модели бедра (ExtraTrees по 47 признакам формы) на правках врачей.

Обучение — scikit-learn (в образе стенда есть; в приложении для компьютера — нет, там плагин недоступен).
Сервис применяет модель numpy-кодом (dxaqc/hipmodel.py): деревья выгружаются в тот же формат npz.
Ворота качества — ROC-AUC брака бедра по кросс-валидации по исследованиям (5 фолдов × повторы).
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from dxaqc import __version__, hipmodel as HM, quality as Q
from dxaqc.learning import Learner, Sample, register

PARAMS = dict(n_estimators=200, min_samples_leaf=3, max_features="sqrt", class_weight="balanced")


@register
class HipTrees(Learner):
    name = "hip_trees"
    title = "Модель бедра (ExtraTrees)"
    regions = ("hip_left", "hip_right")
    min_feedback = 5
    reps = 5

    def available(self):
        try:
            import sklearn  # noqa: F401
            return True, ""
        except ImportError:
            return False, "нужен scikit-learn (есть в образе стенда)"

    def _matrix(self, samples: list[Sample]):
        feats = [HM.features(s.pixels, s.region) for s in samples]
        cur = HM.load()                                  # порядок признаков — как у действующей модели: веса совместимы
        names = list(cur["meta"]["features"]) if cur else sorted({n for f in feats for n in f})
        X = np.array([[f.get(n, np.nan) for n in names] for f in feats], float)
        with np.errstate(all="ignore"):
            med = np.nanmedian(X, 0) if len(X) else np.zeros(len(names))
        med = np.where(np.isnan(med), 0.0, med)
        X = np.where(np.isnan(X), med, X)
        ys = {"bad": np.array([s.bad for s in samples]),
              "hip_positioning": np.array([int("hip_positioning" in s.types) for s in samples]),
              "hip_roi": np.array([int("hip_roi" in s.types) for s in samples])}
        grp = Q.groups([dict(study=s.study, sha=s.sha) for s in samples])
        return X, ys, [grp[s.study] for s in samples], names, med

    def _cv(self, X, y, g):
        from sklearn.ensemble import ExtraTreesClassifier
        aucs, probs = [], []
        for r in range(self.reps):
            rng = np.random.default_rng(100 + r)
            prob = np.zeros(len(y))
            for test in Q.folds(list(g), 5, rng):
                tr = np.setdiff1d(np.arange(len(y)), test)
                if len(set(y[tr])) < 2:
                    continue
                prob[test] = ExtraTreesClassifier(**PARAMS, n_jobs=-1, random_state=r).fit(X[tr], y[tr]).predict_proba(X[test])[:, 1]
            aucs.append(Q.auc(prob, y) or 0.5)
            probs.append(prob)
        return float(np.mean(aucs)), [float(v) for v in Q.ci(aucs)], np.mean(probs, 0)

    def train(self, samples):
        from sklearn.ensemble import ExtraTreesClassifier
        X, ys, g, names, med = self._matrix(samples)
        out = dict(names=names, med=med, models={}, thresholds={}, cv={}, positives={}, n=len(samples),
                   studies=len(set(g)))
        for t, y in ys.items():
            if len(set(y)) < 2:
                continue
            auc, ci, prob = self._cv(X, y, g)
            out["cv"][t] = dict(auc=dict(mean=auc, ci=ci))
            out["thresholds"][t] = float(Q.best_threshold(prob, y))
            out["positives"][t] = int(y.sum())
            out["models"][t] = ExtraTreesClassifier(**PARAMS, n_jobs=-1, random_state=0).fit(X, y)
        return out

    def evaluate(self, cand, samples):
        cv = cand["cv"].get("bad", {}).get("auc", {})
        return dict(score=round(cv.get("mean", 0.0), 4), auc_bad=round(cv.get("mean", 0.0), 4), auc_bad_ci=cv.get("ci"),
                    auc_positioning=round(cand["cv"].get("hip_positioning", {}).get("auc", {}).get("mean", 0.0), 4),
                    samples=cand["n"], studies=cand["studies"])

    def baseline(self):
        act = self.active()
        if act and act.get("metrics"):
            return act["metrics"]
        m = HM.load()
        if not m:
            return {}
        a = m["meta"].get("cv", {}).get("bad", {}).get("auc", {})
        return dict(score=round(a.get("mean", 0.0), 4), auc_bad=round(a.get("mean", 0.0), 4), auc_bad_ci=a.get("ci"))

    def install(self, cand, metrics, version_dir):
        arrays = {}
        for t, clf in cand["models"].items():
            trees = []
            for est in clf.estimators_:
                tr = est.tree_
                v = tr.value[:, 0, :]
                trees.append(dict(feature=tr.feature.astype(np.int32), threshold=tr.threshold.astype(np.float64),
                                  left=tr.children_left.astype(np.int32), right=tr.children_right.astype(np.int32),
                                  value=(v[:, 1] / np.maximum(v.sum(1), 1e-12)).astype(np.float64)))
            arrays[f"{t}_n_trees"] = np.array(len(trees))
            for i, tr in enumerate(trees):
                for k, v in tr.items():
                    arrays[f"{t}_{i}_{k}"] = v
        meta = dict(version=__version__ + "+learned", trained=time.strftime("%Y-%m-%d %H:%M"), algorithm="ExtraTreesClassifier",
                    params=PARAMS, features=cand["names"], medians=[float(x) for x in cand["med"]], images=cand["n"],
                    studies=cand["studies"], thresholds=cand["thresholds"], positives=cand["positives"], cv=cand["cv"],
                    method=dict(k=5, repeats=self.reps, level="study", threshold="F1 вне фолда", source="дообучение на правках врачей"))
        missing = [t for t in HM.TARGETS if t not in cand["models"]]
        if missing:                                      # тип брака без примеров в данных — модель из действующей версии
            cur = np.load(HM.active_path(), allow_pickle=False)
            cur_meta = json.loads(str(cur["meta"]))
            if cur_meta.get("features") != cand["names"]:
                raise ValueError(f"нет примеров для {', '.join(missing)}, а признаки действующей модели другие — обучение невозможно")
            for t in missing:
                for k in cur.files:
                    if k.startswith(t + "_"):
                        arrays[k] = cur[k]
                meta["thresholds"][t] = cur_meta["thresholds"][t]
        path = os.path.join(version_dir, "hip_trees.npz")
        np.savez_compressed(path, meta=np.array(json.dumps(meta, ensure_ascii=False)), **arrays)
        return path
