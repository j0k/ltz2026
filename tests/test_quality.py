# -*- coding: utf-8 -*-
"""Оценка качества: метрики, группы для разбиения и отчёт кросс-валидации на обучающем наборе."""
from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
needs_data = pytest.mark.skipif(not (ROOT / "data" / "train" / "Исследования").exists(), reason="нет данных организатора")


def Q():
    return importlib.import_module("dxaqc.quality")


def test_auc_threshold_and_confusion():
    q = Q()
    y = np.array([0, 0, 1, 1]); s = np.array([0.1, 0.4, 0.35, 0.8])
    assert q.auc(s, y) == pytest.approx(0.75)
    assert q.auc(np.array([1.0, 1.0]), np.array([0, 1])) == pytest.approx(0.5), "связи — средним рангом"
    assert q.auc(s, np.zeros(4, int)) is None
    t = q.best_threshold(np.array([0.1, 0.2, 0.8, 0.9]), np.array([0, 0, 1, 1]))
    assert 0.2 < t <= 0.8, "порог разделяет классы"
    c = q.confusion(np.array([1, 0, 1, 0]), np.array([1, 1, 0, 0]))
    assert (c["tp"], c["fn"], c["fp"], c["tn"]) == (1, 1, 1, 1) and c["f1"] == pytest.approx(0.5)


def test_groups_merge_studies_sharing_an_image():
    q = Q()
    images = [dict(study="A", sha="x"), dict(study="B", sha="x"), dict(study="C", sha="y")]
    g = q.groups(images)
    assert g["A"] == g["B"] != g["C"], "копия снимка не должна попасть и в обучение, и в проверку"


def test_spine_scores_cross_one_exactly_where_rules_fire():
    q = Q(); P = importlib.import_module("dxaqc.params")
    p = P.normalize(None)
    s = q.spine_scores(dict(abs_angle=p["axis_limit_deg"] * 1.2, iliac_left=50, iliac_right=50, bright_px=0), p)
    assert s["axis_tilt"] > 1 and s["coverage"] < 1 and s["artifact"] == 0 and s["overall"] == s["axis_tilt"]


@needs_data
def test_report_on_training_set(client):
    rep = Q().run(repeats=5, boots=100)
    assert rep["data"]["images"] == 252 and rep["data"]["studies"] == 100
    crit = {r["criterion"]: r for r in rep["spine"]}
    assert set(crit) == {"overall", "coverage", "axis_tilt", "artifact"}
    for r in crit.values():
        assert 0 <= r["cv"]["f1"] <= 1 and r["roc_auc"] is not None and r["as_is"]["f1_ci"][0] <= r["as_is"]["f1"] <= r["as_is"]["f1_ci"][1]
    assert crit["overall"]["positives"] == 32 and rep["hips"]["labeled"] == 150
    assert crit["overall"]["as_is"]["f1"] == pytest.approx(0.45, abs=0.01), "«как есть» совпадает с прогоном набора"
