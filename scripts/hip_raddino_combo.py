# -*- coding: utf-8 -*-
"""Бедро: признаки формы (ExtraTrees, как в сервисе) против RAD-DINO и их сочетаний на одних и тех же фолдах
по исследованиям, 5 повторов (28.09, вопрос Юрия «можно улучшить бёдра?»).

Итог 28.09: итог AUC 0,662 (форма) / 0,641 (RAD-DINO) / 0,672 (среднее); укладка 0,619 / 0,606 / 0,640 —
прирост в пределах интервалов, а RAD-DINO требует PyTorch и ~1 с на снимок. В сервис не встроено.

    DXAQC_DATASETS=<папка наборов> ../.venv-ml/bin/python scripts/hip_raddino_combo.py
Нужны data/_ml/meta.npz и emb_rad-dino.npz (scripts/ml_embed.py rad-dino)."""
import os, sys, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ML = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', '_ml')
from dxaqc import analyze as AN, datasets, io as dio, quality as Q, hipmodel as HM, hipfeat as HF
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
P = dict(n_estimators=200, min_samples_leaf=3, max_features="sqrt", class_weight="balanced")
root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
imgs, _, _ = dio.collect(root)
recs = []
for img in imgs:
    reg = AN.detect_region(img.pixels)[0]
    if not reg.startswith("hip"): continue
    study = img.rel_path.split(os.sep)[0]; e = datasets.expert_for(labels, study, reg)
    if e is None or e["bad"] not in (0, 1): continue
    recs.append((study, img.sha, e, HM.features(img.pixels, reg)))
names = sorted({n for r in recs for n in r[3]})
X = np.array([[r[3].get(n, np.nan) for n in names] for r in recs], float); X = np.where(np.isnan(X), np.nanmedian(X, 0), X)
m = np.load(os.path.join(ML, 'meta.npz'), allow_pickle=True); E = np.load(os.path.join(ML, 'emb_rad-dino.npz'))['emb']
idx = {s: i for i, s in enumerate(m['sha'])}
R = np.array([E[idx[r[1]]] for r in recs])
grp = Q.groups([dict(study=s, sha=h) for s, h, *_ in recs]); g = [grp[s] for s, *_ in recs]
ys = {"итог": np.array([int(r[2]["bad"] == 1) for r in recs]), "укладка": np.array([int("hip_positioning" in r[2]["types"]) for r in recs])}
print(f"бёдер {len(recs)}, признаков формы {X.shape[1]}, RAD-DINO {R.shape[1]}", flush=True)

def pca(tr, te, k):
    mu, sd = tr.mean(0), tr.std(0) + 1e-6; a, b = (tr - mu) / sd, (te - mu) / sd
    c = a.mean(0); _, _, Vt = np.linalg.svd(a - c, full_matrices=False)
    return (a - c) @ Vt[:k].T, (b - c) @ Vt[:k].T

def rank(p): return np.argsort(np.argsort(p)) / max(len(p) - 1, 1)

for tname, y in ys.items():
    res = {k: [] for k in ("форма (сейчас)", "RAD-DINO", "среднее", "вместе")}
    for rep in range(5):
        rng = np.random.default_rng(100 + rep); pr = {k: np.zeros(len(y)) for k in res}
        for test in Q.folds(list(g), 5, rng):
            tr = np.setdiff1d(np.arange(len(y)), test)
            et = ExtraTreesClassifier(**P, n_jobs=-1, random_state=rep).fit(X[tr], y[tr])
            pr["форма (сейчас)"][test] = et.predict_proba(X[test])[:, 1]
            Ztr, Zte = pca(R[tr], R[test], 32)
            lr = LogisticRegression(C=0.01, class_weight="balanced", max_iter=2000).fit(Ztr, y[tr])
            pr["RAD-DINO"][test] = lr.predict_proba(Zte)[:, 1]
            pr["среднее"][test] = 0.5 * pr["форма (сейчас)"][test] + 0.5 * pr["RAD-DINO"][test]
            Z16tr, Z16te = pca(R[tr], R[test], 16)
            et2 = ExtraTreesClassifier(**P, n_jobs=-1, random_state=rep).fit(np.hstack([X[tr], Z16tr]), y[tr])
            pr["вместе"][test] = et2.predict_proba(np.hstack([X[test], Z16te]))[:, 1]
        for k in res: res[k].append(Q.auc(pr[k], y))
    print(f"\n{tname}: {len(y)} бёдер, брак {y.sum()}")
    for k, v in res.items(): print(f"  {k:16} AUC {np.mean(v):.3f} [{np.percentile(v,2.5):.2f}–{np.percentile(v,97.5):.2f}]", flush=True)
