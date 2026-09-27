"""Итоговая фитнес-функция (#135): формула, жёсткие условия, бутстреп."""
import pytest

from dxaqc import fitness as FT


def row(study, region, y, score, pred, **types):
    return dict(study=study, region=region, y_bad=y, score=score, pred=pred, status="Success", seconds="1", **types)


def test_perfect_model_scores_one_and_gates_zero_it():
    rows = [row(f"s{i}", "lumbar_spine", i % 2, i % 2, i % 2, y_artifact=i % 2, pred_artifact=i % 2) for i in range(10)]
    rows += [row(f"h{i}", "hip_left", i % 2, i % 2, i % 2, y_hip_roi=i % 2, pred_hip_roi=i % 2) for i in range(10)]
    res = FT.evaluate(rows, boots=50)
    assert res["fitness"] == pytest.approx(1.0) and res["gates"] == [] and res["fitness_ci"][0] == pytest.approx(1.0)
    rows[-1]["pred"] = ""                                  # пустой quality_class у бедра — жёсткое условие
    res = FT.evaluate(rows, boots=0)
    assert res["fitness"] == 0 and res["fitness_raw"] > 0.9 and "пустой quality_class" in res["gates"][0]


def test_weights_and_region_mean():
    rows = [row("a", "lumbar_spine", 1, 0.9, 1), row("b", "lumbar_spine", 0, 0.1, 0),
            row("c", "hip_right", 1, 0.2, 0), row("d", "hip_right", 0, 0.8, 1)]
    res = FT.evaluate(rows, boots=0)
    assert res["f1_regions"] == pytest.approx(0.5) and res["auc_regions"] == pytest.approx(0.5)
    assert res["fitness"] == pytest.approx(0.35 * 0.5 + 0.35 * 0.5 + 0.30 * 0.0), "типов без примеров нет — macro-F1 0"
