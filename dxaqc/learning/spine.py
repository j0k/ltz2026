# -*- coding: utf-8 -*-
"""Плагин spine_thresholds: подстройка порогов проверок поясничного отдела по правкам врачей.

Учатся два порога — контраст постороннего предмета и яркость подвздошных костей (охват). Допуск наклона оси — 5° по
ТЗ, его плагин не меняет. Порог выбирается по F1 на всех примерах; ворота качества — средний F1 двух критериев по
кросс-валидации по исследованиям (порог подбирается только на обучающих фолдах).
"""
from __future__ import annotations

import json
import os

import numpy as np

from dxaqc import analyze as AN, params as P, quality as Q
from dxaqc.learning import Learner, register

CRIT = {"artifact": ("artifact_contrast", "artifact", +1), "coverage": ("iliac_min_brightness", "coverage", -1)}


def learned_params() -> dict:
    """Пороги, установленные плагином, — поверх значений по умолчанию (читает dxaqc.params)."""
    from dxaqc.learning import home
    p = os.path.join(home(), "spine_thresholds", "active.json")
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            info = json.load(f)
        with open(info["path"], encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, KeyError):
        return {}


@register
class SpineThresholds(Learner):
    name = "spine_thresholds"
    title = "Пороги проверок позвоночника"
    regions = ("lumbar_spine",)
    min_feedback = 3
    reps = 20

    def _scores(self, samples):
        p = P.normalize(None)
        rows = []
        for s in samples:
            m = AN.analyze_spine(s.pixels, p)["metrics"]
            rows.append(dict(artifact=m["artifact_contrast"], coverage=min(m["iliac_left"], m["iliac_right"])))
        return rows

    @staticmethod
    def _label(s, crit):
        return int(crit in s.types)          # брак без указанного типа (например, сколиоз) — не этот критерий

    def train(self, samples):
        rows = self._scores(samples)
        grp = Q.groups([dict(study=s.study, sha=s.sha) for s in samples])
        g = [grp[s.study] for s in samples]
        cand = dict(thresholds={}, cv={})
        for crit, (param, _code, sign) in CRIT.items():
            y = np.array([self._label(s, crit) for s in samples])
            score = np.array([sign * r[crit] for r in rows], float)
            if len(set(y)) < 2:
                continue
            thr = Q.best_threshold(score, y)
            lo, hi = P.BY_NAME[param]["min"], P.BY_NAME[param]["max"]
            v = float(np.clip(sign * thr, lo, hi))
            cand["thresholds"][param] = int(round(v)) if P.BY_NAME[param]["kind"] is int else round(v, 2)
            cand["cv"][crit] = self._cv(score, y, g)
            base = np.array([s.source == "организатор" for s in samples])
            if base.any() and len(set(y[base])) == 2:     # та же процедура только на базовом наборе — честное сравнение
                cand["cv"][crit + "_base"] = self._cv(score[base], y[base], [gi for gi, b in zip(g, base) if b])
            cand["cv"][crit + "_current"] = self._fixed(score, y, sign * P.normalize(None)[param])
        return cand

    def _cv(self, score, y, g):
        f1 = []
        for r in range(self.reps):
            rng = np.random.default_rng(7 + r)
            pred = np.zeros(len(y), int)
            for test in Q.folds(g, 5, rng):
                tr = np.setdiff1d(np.arange(len(y)), test)
                t = Q.best_threshold(score[tr], y[tr])
                pred[test] = (score[test] >= t).astype(int)
            f1.append(Q.confusion(pred, y)["f1"])
        return float(np.mean(f1))

    @staticmethod
    def _fixed(score, y, t):
        return float(Q.confusion((score >= t).astype(int), y)["f1"])

    def evaluate(self, cand, samples):
        cv = cand["cv"]
        crits = [c for c in CRIT if c in cv]
        new = float(np.mean([cv[c] for c in crits])) if crits else 0.0
        cur = float(np.mean([cv[c + "_current"] for c in crits])) if crits else 0.0
        base = [cv[c + "_base"] for c in crits if c + "_base" in cv]
        return dict(score=round(new, 4), f1_cv_learned=round(new, 4), f1_cv_base=round(float(np.mean(base)), 4) if base else None,
                    f1_current_thresholds_insample=round(cur, 4),
                    thresholds={k: round(v, 2) for k, v in cand["thresholds"].items()}, samples=len(samples))

    def baseline(self):
        act = self.active()
        return act["metrics"] if act and act.get("metrics") else {}

    def accept(self, metrics, baseline):
        # сравнение одинаковых величин: F1 процедуры подбора порога по кросс-валидации — на базовом наборе (как у
        # действующих порогов) и на базовом наборе с правками врачей; с установленной версией — по её же метрике
        ref = max(metrics.get("f1_cv_base") or 0.0, float((baseline or {}).get("score", 0.0)))
        new = metrics.get("score", 0.0)
        if new + self.tolerance >= ref:
            return True, f"F1 {new:.3f} против {ref:.3f} у действующих порогов — не хуже (допуск {self.tolerance})"
        return False, f"F1 {new:.3f} хуже действующих порогов {ref:.3f} — версия не установлена"

    def install(self, cand, metrics, version_dir):
        path = os.path.join(version_dir, "params.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cand["thresholds"], f, ensure_ascii=False, indent=1)
        return path
