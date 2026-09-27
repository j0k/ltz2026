# -*- coding: utf-8 -*-
"""Итоговая фитнес-функция: одно число, по которому сравниваются модели и версии (#135).

Собрана из раздела 8.4 ТЗ: приоритет — F1 и ROC-AUC, отдельно по областям и типам нарушений, macro-F1 по типам,
95% доверительные интервалы, время и доля успешно обработанных файлов. Весов в ТЗ нет — они наши:

    fitness = 0.35 · F1_обл + 0.35 · AUC_обл + 0.30 · macroF1_типов

    F1_обл, AUC_обл — среднее по областям (позвоночник, бедро), брак = положительный класс; среднее, а не общий
                      пул, чтобы нельзя было «выиграть» одной областью и провалить другую;
    macroF1_типов   — среднее F1 по типам нарушений ТЗ, у которых в данных есть хотя бы один пример.

Жёсткие условия (иначе fitness = 0): все файлы обработаны (processing_status = Success, кроме заведомо не DXA),
у каждого снимка поясницы и бедра quality_class 0/1 (пустой класс — ошибка), время ≤ 180 с на исследование.

Оценивать только на предсказаниях «вне фолда»: фолды по исследованиям (общие снимки — в одной группе,
dxaqc.quality.groups), пороги подбираются внутри обучающей части. Интервал — бутстреп по исследованиям.

Вход — таблица, строка на снимок (CSV или список словарей):
    study, region (lumbar_spine | hip_left | hip_right), y_bad (0/1 — эксперты), score (вероятность брака),
    pred (0/1 — вердикт), для типов — y_<тип> и pred_<тип> (0/1); необязательно: status, seconds.

    python -m dxaqc.fitness oof.csv [--boots 1000]
"""
from __future__ import annotations

import csv
import json
import sys

import numpy as np

from dxaqc.quality import auc, confusion

WEIGHTS = dict(f1=0.35, auc=0.35, types=0.30)
REGIONS = {"spine": ("lumbar_spine",), "hip": ("hip_left", "hip_right")}
TYPES = ("coverage", "axis_tilt", "artifact", "hip_positioning", "hip_roi")
TIME_LIMIT = 180.0


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def components(rows: list[dict]) -> dict:
    """Все слагаемые и справочные метрики ТЗ 8.4 для набора строк."""
    out = dict(regions={}, types={})
    for name, regs in REGIONS.items():
        rr = [r for r in rows if r.get("region") in regs and _f(r.get("y_bad")) in (0.0, 1.0)]
        if not rr:
            continue
        y = np.array([int(_f(r["y_bad"])) for r in rr])
        if y.all() or not y.any():                        # нет обоих классов — область в этой выборке не оценить
            continue
        pred = np.array([int(_f(r.get("pred")) or 0) for r in rr])
        score = np.array([_f(r.get("score")) if _f(r.get("score")) is not None else _f(r.get("pred")) or 0.0 for r in rr])
        c = confusion(pred, y)
        sens, spec = c["sensitivity"], c["specificity"]
        out["regions"][name] = dict(n=len(rr), positives=int(y.sum()), f1=c["f1"], auc=auc(score, y), sensitivity=sens,
                                    specificity=spec, balanced_accuracy=(sens + spec) / 2 if sens is not None and spec is not None else None)
    for t in TYPES:
        rr = [r for r in rows if _f(r.get(f"y_{t}")) in (0.0, 1.0)]
        y = np.array([int(_f(r[f"y_{t}"])) for r in rr])
        if not len(y) or not y.sum():
            continue
        pred = np.array([int(_f(r.get(f"pred_{t}")) or 0) for r in rr])
        out["types"][t] = dict(n=len(rr), positives=int(y.sum()), f1=confusion(pred, y)["f1"])
    reg = list(out["regions"].values())
    f1_r = float(np.mean([r["f1"] for r in reg])) if reg else 0.0
    auc_r = float(np.mean([r["auc"] if r["auc"] is not None else 0.5 for r in reg])) if reg else 0.5
    macro = float(np.mean([t["f1"] for t in out["types"].values()])) if out["types"] else 0.0
    out.update(f1_regions=f1_r, auc_regions=auc_r, macro_f1_types=macro,
               fitness=WEIGHTS["f1"] * f1_r + WEIGHTS["auc"] * auc_r + WEIGHTS["types"] * macro)
    return out


def gates(rows: list[dict]) -> list[str]:
    """Нарушения жёстких условий; пустой список — всё выполнено."""
    bad = []
    failed = [r for r in rows if (r.get("status") or "Success") != "Success" and r.get("region") in sum(REGIONS.values(), ())]
    if failed:
        bad.append(f"не обработано снимков поясницы/бедра: {len(failed)}")
    empty = [r for r in rows if r.get("region") in sum(REGIONS.values(), ()) and _f(r.get("pred")) not in (0.0, 1.0)]
    if empty:
        bad.append(f"пустой quality_class у {len(empty)} снимков")
    per_study: dict = {}
    for r in rows:
        if _f(r.get("seconds")) is not None:
            per_study[r.get("study")] = per_study.get(r.get("study"), 0.0) + _f(r["seconds"])
    slow = [s for s, t in per_study.items() if t > TIME_LIMIT]
    if slow:
        bad.append(f"дольше {TIME_LIMIT:.0f} с на исследование: {len(slow)}")
    return bad


def evaluate(rows: list[dict], boots: int = 1000, seed: int = 7) -> dict:
    """Фитнес, его слагаемые и 95% интервал бутстрепом по исследованиям."""
    comp = components(rows)
    g = gates(rows)
    by = {}
    for r in rows:
        by.setdefault(r.get("study"), []).append(r)
    keys = list(by)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(boots if len(keys) > 1 else 0):
        sample = [r for k in rng.choice(len(keys), len(keys)) for r in by[keys[k]]]
        vals.append(components(sample)["fitness"])
    ci = [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else [None, None]
    return dict(comp, fitness=0.0 if g else comp["fitness"], fitness_raw=comp["fitness"], fitness_ci=ci, gates=g,
                weights=WEIGHTS)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Итоговая фитнес-функция по предсказаниям «вне фолда»")
    ap.add_argument("csv")
    ap.add_argument("--boots", type=int, default=1000)
    a = ap.parse_args(argv)
    with open(a.csv, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    res = evaluate(rows, boots=a.boots)
    ci = res["fitness_ci"]
    print(f"fitness {res['fitness']:.3f}" + (f" [{ci[0]:.3f}–{ci[1]:.3f}]" if ci[0] is not None else ""))
    print(f"  F1 по областям {res['f1_regions']:.3f} · AUC по областям {res['auc_regions']:.3f} · macro-F1 типов {res['macro_f1_types']:.3f}")
    for k, v in res["regions"].items():
        print(f"  {k:6} n={v['n']:<4} +{v['positives']:<3} F1 {v['f1']:.3f}  AUC {v['auc'] if v['auc'] is None else round(v['auc'], 3)}"
              f"  чувств. {v['sensitivity']}  спец. {v['specificity']}")
    for k, v in res["types"].items():
        print(f"  {k:16} +{v['positives']:<3} F1 {v['f1']:.3f}")
    if res["gates"]:
        print("  ЖЁСТКИЕ УСЛОВИЯ НАРУШЕНЫ → fitness 0:", "; ".join(res["gates"]))
    with open(a.csv + ".fitness.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
