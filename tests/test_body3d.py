# -*- coding: utf-8 -*-
"""3D-вид исследования: сцена из результатов проверки, страница, ссылка со страницы результата, three.js локально."""
from __future__ import annotations

import importlib
import json
import os
import sys
import time


def B():
    return importlib.import_module("dxaqc.web.body3d")


SPINE = dict(key="s1", study_key="st1", anatomical_region="lumbar_spine", quality_class=1, processing_status="Success",
             violation_list=["artifact"], metrics=dict(angle_deg=-2.2),
             callouts=dict(image_box=[200, 50, 600, 634], items=[
                 dict(label="L1", anchor=[424, 368]), dict(label="L5", anchor=[424, 662]),
                 dict(label="посторонний предмет", anchor=[728, 62]), dict(label="ось столба", anchor=[506, 272])]))
HIP = dict(key="h1", study_key="st1", anatomical_region="hip_left", quality_class=1, processing_status="Success",
           violation_list=["hip_positioning"], metrics=dict(hip_prob_bad=0.77))


def test_scene_takes_verdicts_angle_and_spots():
    sc = B().scene("r1", [SPINE, HIP])
    sp, hl, hr = (sc["regions"][k] for k in ("lumbar_spine", "hip_left", "hip_right"))
    assert sc["verdict"] == "bad" and sc["bad"] == ["Поясничный отдел", "Левое бедро"]
    assert sp["status"] == "bad" and sp["angle"] == -2.2 and sp["card"] == "/runs/r1/images/s1"
    assert sp["levels"]["L1"] == [0.373, 0.502] and sp["spots"] == [[0.88, 0.019]], "предметы — в долях кадра"
    assert "ось -2,2° (допуск 5°) ✓" in sp["lines"] and "предметы ✕ 1" in sp["lines"]
    assert hl["positioning"] and not hl["roi"] and hl["lines"][0] == "вероятность брака 0,77"
    assert hr["status"] == "absent" and hr["card"] is None and hr["lines"] == ["снимка нет в исследовании"]


def test_worst_image_of_region_wins_and_studies_group():
    ok = dict(HIP, key="h0", quality_class=0, violation_list=[])
    assert B().scene("r", [ok, HIP])["regions"]["hip_left"]["status"] == "bad"
    other = dict(HIP, study_key="st2")
    assert list(B().studies([SPINE, HIP, other, dict(anatomical_region="unknown")])) == ["st1", "st2"]


def fake_run(run_id, rows):
    app = sys.modules["dxaqc.web.app"]
    out = os.path.join(app.RUNS, run_id, "out")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(app.RUNS, run_id, "status.json"), "w") as f:
        json.dump(dict(state="done", title="Проверка", created=time.time(), finished=time.time()), f)
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(dict(summary=dict(images=len(rows), bad=1, good=0, studies=1), rows=rows), f)


def test_page_renders_tags_and_data(client):
    fake_run("20260927-190000-aaaaaa", [SPINE, HIP, dict(HIP, key="h2", study_key="st2", quality_class=0, violation_list=[])])
    html = client.get("/runs/20260927-190000-aaaaaa/3d").text
    assert 'id="b3dData"' in html and "/static/vendor/three/three.module.min.js" in html and "/static/body3d.js" in html
    assert 'b3d-tag tl bad' in html and 'b3d-tag right bad' in html and 'b3d-tag left absent' in html
    assert "Модель схематичная" in html and 'name="study"' in html, "честная подпись и выбор исследования"
    one = client.get("/runs/20260927-190000-aaaaaa/3d?study=st2").text
    assert 'b3d-tag right ok' in one and 'b3d-tag tl absent' in one
    assert client.get("/runs/nope-run/3d").status_code == 404
    check = client.get("/check/20260927-190000-aaaaaa").text
    assert 'href="/runs/20260927-190000-aaaaaa/3d"' in check


def test_three_is_served_locally(client):
    for f in ("three.module.min.js", "three.core.min.js", "OrbitControls.js", "LICENSE"):
        assert client.get(f"/static/vendor/three/{f}").status_code == 200, f
    js = client.get("/static/body3d.js").text
    assert "from 'three'" in js and "http" not in js.split("import")[1].split(";")[0], "без CDN — работает без сети"
