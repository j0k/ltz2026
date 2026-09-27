# -*- coding: utf-8 -*-
"""Эксперимент 27.09 (#129): выгрузка признаков для деревьев решений в npz вне репозитория.

Бедро — 47 признаков dxaqc.hipmodel (края кадра, контраст, геометрия ориентиров),
позвоночник — метрики и измерения анализатора 0.5.3. Модели считает scripts/trees_eval.py в .venv-ml.

    DXAQC_DATASETS=<папка наборов> .venv/bin/python scripts/trees_dump.py <out.npz>
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dxaqc.hipmodel import features as scan  # noqa: E402
from dxaqc import analyze as AN, datasets, params as P, quality as Q, io as dio  # noqa: E402

root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
images, _, _ = dio.collect(root)
hip, spine = [], []
for img in images:
    reg = AN.detect_region(img.pixels)[0]
    study = img.rel_path.split(os.sep)[0]; e = datasets.expert_for(labels, study, reg)
    if e is None:
        continue
    if reg.startswith("hip"):
        hip.append((study, img.sha, e, scan(img.pixels, reg)))
    elif reg == "lumbar_spine":
        res = AN.analyze_spine(img.pixels, P.normalize(None)) if hasattr(AN, "analyze_spine") else None
        f = {}
        for part in ("metrics", "measurements"):
            for k, v in ((res or {}).get(part) or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    f[f"{part[0]}_{k}"] = float(v)
        spine.append((study, img.sha, e, f))


def pack(recs, pref):
    names = sorted(set.intersection(*[set(r[3]) for r in recs]))
    grp = Q.groups([dict(study=s, sha=h) for s, h, *_ in recs])
    types = sorted({t for r in recs for t in r[2]["types"]})
    return {f"{pref}_X": np.array([[r[3][n] for n in names] for r in recs], float), f"{pref}_names": np.array(names),
            f"{pref}_group": np.array([grp[r[0]] for r in recs]), f"{pref}_bad": np.array([int(r[2]["bad"] == 1) for r in recs]),
            f"{pref}_types": np.array(types), f"{pref}_sha": np.array([r[1] for r in recs]),
            f"{pref}_Y": np.array([[int(t in r[2]["types"]) for t in types] for r in recs])}


out = dict(**pack(hip, "hip"), **pack(spine, "spine"))
np.savez(sys.argv[1], **out)
print({k: v.shape for k, v in out.items() if k.endswith("_X")}, list(out["hip_types"]), list(out["spine_types"]))
