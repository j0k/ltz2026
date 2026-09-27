# -*- coding: utf-8 -*-
"""Честная оценка качества на обучающем наборе организатора.

    DXAQC_DATASETS=<папка наборов> .venv/bin/python scripts/evaluate.py [--repeats 50] [--out results/quality_cv.json]

Печатает F1 и ROC-AUC с 95% ДИ «как есть» и по кросс-валидации, пишет JSON для страницы «Качество».
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dxaqc import quality  # noqa: E402


def fmt(x, digits=2):
    return "—" if x is None else f"{x:.{digits}f}".replace(".", ",")


def rng(ci):
    return "—" if not ci or ci[0] is None else f"{fmt(ci[0])}–{fmt(ci[1])}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=50)
    ap.add_argument("--boots", type=int, default=1000)
    ap.add_argument("--out", default=os.path.join("results", "quality_cv.json"))
    ap.add_argument("--cache", default=os.path.join("results", "features_cache.json"))
    a = ap.parse_args()
    t0 = time.time()
    rep = quality.run(out=a.out, cache=a.cache, repeats=a.repeats, boots=a.boots)
    d = rep["data"]
    print(f"версия {rep['version']} · снимков {d['images']} (позвоночник {d['spine_images']}, бёдра {d['hip_images']}) · "
          f"исследований {d['studies']} в {d['groups']} группах · {rep['method']['k']} фолдов × {rep['method']['repeats']} повторов")
    print(f"{'критерий':22} {'иссл/+':>7} | {'F1 как есть':>18} | {'F1 кросс-валидация':>18} | {'ROC-AUC':>16} | порог CV")
    for r in rep["spine"]:
        print(f"{r['title']:22} {r['studies']:>3}/{r['positives']:<3} | {fmt(r['as_is']['f1']):>5} [{rng(r['as_is']['f1_ci']):>10}] | "
              f"{fmt(r['cv']['f1']):>5} [{rng(r['cv']['f1_ci']):>10}] | {fmt(r['roc_auc']):>4} [{rng(r['roc_auc_ci']):>9}] | "
              f"{fmt(r['cv']['threshold_median'])}")
    h = rep["hips"]
    if not h["evaluated"]:
        print(f"бёдра: не оцениваются · размечено {h['labeled']} снимков, из них с нарушением {h['bad']}")
    for t, c in (h.get("cv") or {}).items():
        print(f"бедро, {quality.TITLES.get('hip_overall' if t == 'bad' else t, t):16} +{h['positives'][t]:<3} | F1 CV {fmt(c['f1']['mean'])} "
              f"[{rng(c['f1']['ci'])}] | ROC-AUC {fmt(c['auc']['mean'])} [{rng(c['auc']['ci'])}] | порог {fmt(h['thresholds'][t])}")
    print(f"за {time.time() - t0:.0f} с → {a.out}")


if __name__ == "__main__":
    main()
