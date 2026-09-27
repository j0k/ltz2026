"""Модель бедра (#129): веса в репозитории, предсказание на numpy, вердикт 0/1 вместо «не оценено»."""
import glob
import os

import numpy as np
import pytest

from dxaqc import analyze as AN, hipmodel as HM

TEST_SET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "Для теста")


def test_weights_ship_with_code():
    m = HM.load()
    assert m is not None, "dxaqc/models/hip_trees.npz должен быть в репозитории и образе"
    meta = m["meta"]
    assert set(m["models"]) == set(HM.TARGETS) and len(meta["features"]) == 47
    assert all(0 < meta["thresholds"][t] < 1 for t in HM.TARGETS)
    assert meta["cv"]["bad"]["auc"]["mean"] > 0.6, "кросс-валидация из обучения хранится вместе с весами"


def test_forest_walk_matches_hand_built_tree():
    # корень: признак 0 <= 0.5 -> лист 0.2, иначе лист 0.9
    tree = (np.array([0, -2, -2]), np.array([0.5, -2, -2]), np.array([1, -1, -1]), np.array([2, -1, -1]), np.array([0, .2, .9]))
    assert HM._forest_proba([tree], np.array([0.1])) == pytest.approx(0.2)
    assert HM._forest_proba([tree, tree], np.array([0.7])) == pytest.approx(0.9)


def test_missing_features_fall_back_to_medians():
    meta = dict(features=["a", "b"], medians=[1.0, 2.0])
    assert list(HM.vector({"a": 5.0, "b": float("nan")}, meta)) == [5.0, 2.0]
    assert list(HM.vector({}, meta)) == [1.0, 2.0]


def test_without_weights_hip_stays_not_evaluated(monkeypatch):
    import importlib
    # другие тесты перезагружают пакет — берём модули, которые analyze увидит сейчас
    monkeypatch.setattr(importlib.import_module("dxaqc.hipmodel"), "load", lambda *a, **k: None)
    res = importlib.import_module("dxaqc.analyze").analyze_hip(np.zeros((200, 150), np.uint8), "hip_right")
    assert res["quality_class"] is None and res["violations"] == ["hip_not_evaluated_v0"]


@pytest.mark.skipif(not os.path.isdir(TEST_SET), reason="нет тестового набора организатора")
def test_hips_of_test_set_get_verdict_and_are_deterministic():
    from dxaqc import io as dio
    images, _, _ = dio.collect(TEST_SET)
    hips = [im for im in images if AN.detect_region(im.pixels)[0].startswith("hip")]
    assert hips
    for im in hips:
        a, b = AN.analyze(im.pixels), AN.analyze(im.pixels)
        assert a["quality_class"] in (0, 1) and a["quality_class"] == b["quality_class"]
        assert a["metrics"]["hip_prob_bad"] == b["metrics"]["hip_prob_bad"]
        assert set(a["violations"]) <= {"hip_positioning", "hip_roi"} and bool(a["violations"]) == bool(a["quality_class"])
