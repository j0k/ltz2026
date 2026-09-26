# -*- coding: utf-8 -*-
"""Честная оценка качества сервиса на обучающем наборе: кросс-валидация по исследованиям, F1 и ROC-AUC с 95% ДИ.

Метрики ТЗ — F1 и ROC-AUC с доверительными интервалами, по областям и типам нарушений. Здесь они считаются двумя
способами:
- «как есть» — правила с текущими порогами; это то же, что показывает прогон набора, но с интервалами;
- кросс-валидация — порог каждого критерия подбирается только на обучающих фолдах и проверяется на отложенном,
  много раз с разными разбиениями. Это честная оценка того, что будет на новых данных.
Для ROC-AUC нужна оценка уверенности, а не только «да/нет»: у каждого критерия это отношение измеренной величины
к её порогу — больше 1 ровно там, где правило срабатывает.

Группы для разбиения: исследование плюс все исследования, где встречается тот же снимок (по совпадению пикселей),
чтобы копия не оказалась одновременно в обучении и в проверке. Сравнение с экспертами — на уровне исследования,
как дана разметка.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from dxaqc import __version__, analyze, datasets
from dxaqc import io as dio
from dxaqc import params as P

SPINE_CRITERIA = ("overall", "coverage", "axis_tilt", "artifact")
TITLES = {"overall": "позвоночник, итог", "coverage": "охват", "axis_tilt": "наклон оси", "artifact": "посторонние предметы",
          "hip_overall": "бедро, итог", "hip_positioning": "укладка бедра", "hip_roi": "поля вокруг зоны интереса"}


# ------------------------------------------------------------------ признаки снимков

def spine_scores(metrics: dict, p: dict) -> dict:
    """Оценки уверенности позвоночника: отношение величины к порогу, > 1 — правило срабатывает."""
    worst_iliac = min(metrics["iliac_left"], metrics["iliac_right"])
    s = dict(axis_tilt=metrics["abs_angle"] / p["axis_limit_deg"],
             coverage=p["iliac_min_brightness"] / max(worst_iliac, 0.05),
             artifact=metrics["bright_px"] / max(p["artifact_min_pixels"], 1))
    s["overall"] = max(s.values())
    return s


def extract(root: str, labels: dict, cache: str | None = None) -> list[dict]:
    """Признаки каждого уникального снимка набора: область, оценки, хеш пикселей, исследование, разметка экспертов."""
    if cache and os.path.isfile(cache):
        with open(cache, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("version") == __version__:
            return data["images"]
    p = P.normalize(None)
    images, _failures, _dups = dio.collect(root)
    out = []
    for img in images:
        res = analyze.analyze(img.pixels, p)
        study = img.rel_path.split(os.sep)[0] if os.sep in img.rel_path else img.study_uid
        row = dict(key=img.sha[:12], sha=img.sha, study=study, region=res["region"],
                   expert=datasets.expert_for(labels, study, res["region"]))
        if res["region"] == "lumbar_spine":
            row["scores"] = spine_scores(res["metrics"], p)
        out.append(row)
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(dict(version=__version__, images=out), fh, ensure_ascii=False)
    return out


def groups(images: list[dict]) -> dict:
    """Исследование → номер группы: исследования, делящие хоть один снимок, склеиваются (union-find)."""
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_sha: dict = {}
    for im in images:
        find(im["study"])
        if im["sha"] in by_sha:
            parent[find(im["study"])] = find(by_sha[im["sha"]])
        else:
            by_sha[im["sha"]] = im["study"]
    roots = {}
    return {s: roots.setdefault(find(s), len(roots)) for s in parent}


# ------------------------------------------------------------------ метрики

def confusion(pred: np.ndarray, y: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    sens = tp / (tp + fn) if tp + fn else None
    spec = tn / (tn + fp) if tn + fp else None
    prec = tp / (tp + fp) if tp + fp else None
    f1 = 2 * prec * sens / (prec + sens) if prec and sens else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, n=int(len(y)), f1=f1, sensitivity=sens, specificity=spec)


def auc(score: np.ndarray, y: np.ndarray) -> float | None:
    """ROC-AUC через ранги (Манн — Уитни), связи — средним рангом."""
    pos, neg = y == 1, y == 0
    if not pos.any() or not neg.any():
        return None
    order = score.argsort(kind="mergesort")
    ranks = np.empty(len(score)); ranks[order] = np.arange(1, len(score) + 1)
    for v in np.unique(score):                       # средние ранги для одинаковых оценок
        m = score == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    n_pos, n_neg = pos.sum(), neg.sum()
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def best_threshold(score: np.ndarray, y: np.ndarray) -> float:
    """Порог с наибольшим F1 на обучающей части; при равенстве — ближе к середине между соседними оценками."""
    cand = np.unique(score)
    best, best_f1 = cand[-1] + 1, -1.0
    for t in cand:
        f1 = confusion((score >= t).astype(int), y)["f1"]
        if f1 > best_f1 + 1e-12:
            best, best_f1 = t, f1
    below = cand[cand < best]
    return float((best + below[-1]) / 2) if len(below) else float(best)


def ci(values, lo=2.5, hi=97.5):
    v = np.asarray([x for x in values if x is not None and not np.isnan(x)])
    return [float(np.percentile(v, lo)), float(np.percentile(v, hi))] if len(v) else [None, None]


def study_table(images: list[dict], criterion: str) -> tuple[list, np.ndarray, np.ndarray]:
    """Исследования позвоночника с разметкой: оценка — максимум по снимкам, метка эксперта — по исследованию."""
    rows = {}
    for im in images:
        e = im.get("expert")
        if im["region"] != "lumbar_spine" or not e or "scores" not in im:
            continue
        label = int(e["bad"] == 1) if criterion == "overall" else int(criterion in e["types"])
        r = rows.setdefault(im["study"], dict(score=-np.inf, y=label))
        r["score"] = max(r["score"], im["scores"][criterion])
    studies = sorted(rows)
    return studies, np.array([rows[s]["score"] for s in studies]), np.array([rows[s]["y"] for s in studies])


def folds(study_groups: list[int], k: int, rng) -> list[np.ndarray]:
    ids = np.unique(study_groups)
    rng.shuffle(ids)
    part = {g: i % k for i, g in enumerate(ids)}
    fold_of = np.array([part[g] for g in study_groups])
    return [np.where(fold_of == i)[0] for i in range(k)]


def evaluate_criterion(images, grp: dict, criterion: str, k: int = 5, repeats: int = 50, boots: int = 1000, seed: int = 7) -> dict:
    studies, score, y = study_table(images, criterion)
    rng = np.random.default_rng(seed)
    n = len(y)
    asis = confusion((score > 1).astype(int), y)
    boot_idx = [rng.integers(0, n, n) for _ in range(boots)]
    asis_f1_ci = ci([confusion((score[i] > 1).astype(int), y[i])["f1"] for i in boot_idx])
    auc_all = auc(score, y)
    auc_ci = ci([auc(score[i], y[i]) for i in boot_idx])
    g = [grp[s] for s in studies]
    cv_f1, cv_sens, cv_spec, cv_boot = [], [], [], []
    thresholds = []
    for _ in range(repeats):
        pred = np.zeros(n, dtype=int)
        for test in folds(g, k, rng):
            train = np.setdiff1d(np.arange(n), test)
            t = best_threshold(score[train], y[train]) if y[train].any() else np.inf
            thresholds.append(t)
            pred[test] = (score[test] >= t).astype(int)
        c = confusion(pred, y)
        cv_f1.append(c["f1"]); cv_sens.append(c["sensitivity"]); cv_spec.append(c["specificity"])
        for i in boot_idx[: max(1, boots // repeats)]:
            cv_boot.append(confusion(pred[i], y[i])["f1"])
    mean = lambda v: float(np.mean([x for x in v if x is not None])) if any(x is not None for x in v) else None
    return dict(criterion=criterion, title=TITLES[criterion], studies=n, positives=int(y.sum()),
                as_is=dict(asis, f1_ci=asis_f1_ci),
                cv=dict(f1=mean(cv_f1), f1_ci=ci(cv_boot), sensitivity=mean(cv_sens), specificity=mean(cv_spec),
                        threshold_median=float(np.median(thresholds)), threshold_ci=ci(thresholds)),
                roc_auc=auc_all, roc_auc_ci=auc_ci)


def report(images: list[dict], k: int = 5, repeats: int = 50, boots: int = 1000) -> dict:
    grp = groups(images)
    shared = len(grp) - len(set(grp.values()))
    hips = [im for im in images if im["region"].startswith("hip") and im.get("expert")]
    return dict(
        version=__version__, created=time.time(), method=dict(k=k, repeats=repeats, bootstrap=boots, level="study",
                                                              groups="исследование + общие снимки"),
        data=dict(images=len(images), studies=len(grp), groups=len(set(grp.values())), studies_sharing_images=shared,
                  spine_images=sum(1 for im in images if im["region"] == "lumbar_spine"),
                  hip_images=sum(1 for im in images if im["region"].startswith("hip"))),
        spine=[evaluate_criterion(images, grp, c, k, repeats, boots) for c in SPINE_CRITERIA],
        hips=dict(evaluated=False, labeled=len(hips), bad=sum(1 for im in hips if im["expert"]["bad"] == 1),
                  note="бедро в этой версии не оценивается — вердикта нет, метрики не считаются"),
    )


def run(root: str | None = None, out: str | None = None, cache: str | None = None, **kw) -> dict:
    root = root or os.path.join(datasets.ROOT, datasets.REGISTRY["train"]["path"])
    images = extract(root, datasets.load_labels("train") or {}, cache)
    rep = report(images, **kw)
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    return rep
