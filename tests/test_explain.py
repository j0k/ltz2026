"""Пояснение графом (#137): узлы проверок с измерением и порогом, вердикт, переключатель граф ⇄ текст."""
from dxaqc.web import explain


def test_spine_graph_marks_failed_check():
    row = dict(anatomical_region="lumbar_spine", processing_status="Success", quality_class=1, violation_list=["artifact"],
               metrics=dict(angle_deg=-2.2, iliac_left=55.1, iliac_right=36.3, artifact_contrast=127),
               explanations=["Область: ширина кадра 300 px, протокол позвоночника GE Lunar."])
    g = explain.graph(row, {"artifact_contrast": 55}, None)
    st = {c["title"]: (c["state"], c["value"], c["rule"]) for c in g["checks"]}
    assert st["Предметы"] == ("bad", "контраст 127", "< 55") and st["Ось"][0] == "ok" and st["Охват"][0] == "ok"
    assert g["verdict"] == dict(state="bad", text="брак") and g["basis"].startswith("ширина кадра 300 px")


def test_hip_graph_uses_model_thresholds_and_skips_failures():
    row = dict(anatomical_region="hip_left", processing_status="Success", quality_class=0, violation_list=[],
               metrics=dict(hip_prob_bad=0.19, hip_prob_positioning=0.2, hip_prob_roi=0.05), explanations=[])
    g = explain.graph(row, None, {"bad": 0.385, "hip_positioning": 0.355, "hip_roi": 0.338})
    assert [c["title"] for c in g["checks"]] == ["Брак", "Укладка", "Поля ROI"] and g["checks"][0]["rule"] == "< 0,39"
    assert all(c["state"] == "ok" for c in g["checks"]) and g["verdict"]["text"] == "годен"
    assert explain.graph(dict(row, processing_status="Failure"), None, None) is None


def test_dashboard_renders_graph_and_text(client):
    html = client.get("/check/example").text
    if '<article class="d-img' in html:
        assert 'class="xg"' in html and 'class="xg-text"' in html and 'data-v="text"' in html
