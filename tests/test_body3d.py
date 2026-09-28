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
             original_png="s1_original.png", overlay_png="s1_overlay.png",
             violation_list=["artifact"], metrics=dict(angle_deg=-2.2),
             callouts=dict(image_box=[200, 50, 600, 634], items=[
                 dict(label="L1", anchor=[424, 368]), dict(label="L5", anchor=[424, 662]),
                 dict(label="посторонний предмет", anchor=[728, 62]), dict(label="ось столба", anchor=[506, 272])]))
HIP = dict(key="h1", study_key="st1", anatomical_region="hip_left", quality_class=1, processing_status="Success",
           violation_list=["hip_positioning"], metrics=dict(hip_prob_bad=0.77), original_png="h1_original.png",
           callouts=dict(image_box=[230, 50, 560, 582], items=[dict(label="шейка и головка бедра", anchor=[370, 206]),
                                                                 dict(label="большой вертел", anchor=[686, 290])]))


def test_scene_takes_verdicts_angle_and_spots():
    sc = B().scene("r1", [SPINE, HIP])
    sp, hl, hr = (sc["regions"][k] for k in ("lumbar_spine", "hip_left", "hip_right"))
    assert sc["verdict"] == "bad" and sc["bad"] == ["Поясничный отдел", "Левое бедро"]
    assert sp["status"] == "bad" and sp["angle"] == -2.2 and sp["card"] == "/runs/r1/images/s1"
    assert sp["levels"]["L1"] == [0.373, 0.502] and sp["spots"] == [[0.88, 0.019]], "предметы — в долях кадра"
    assert "ось -2,2° (допуск 5°) ✓" in sp["lines"] and "предметы ✕ 1" in sp["lines"]
    assert hl["positioning"] and not hl["roi"] and hl["lines"][0] == "вероятность брака 0,77"
    assert hr["status"] == "absent" and hr["card"] is None and hr["lines"] == ["снимка нет в исследовании"]
    # рентген-вид: снимок и опоры для совмещения с моделью
    assert sp["image"] == "/runs/r1/files/s1_original.png" and hr["image"] is None
    assert hl["anchors"] == {"head": [0.25, 0.268], "gt": [0.814, 0.412]} and hl["aspect"] == 0.9622


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


def test_results_only_on_images(client):
    """28.09, Алексей: результаты — только на снимках; 3D-вид исследования и выбор на нём убраны."""
    fake_run("20260927-190000-aaaaaa", [SPINE, HIP, dict(HIP, key="h2", study_key="st2", quality_class=0, violation_list=[])])
    r = client.get("/runs/20260927-190000-aaaaaa/3d?study=st2", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/check/20260927-190000-aaaaaa", "старые ссылки — на результат"
    assert client.get("/runs/nope-run/3d", follow_redirects=False).status_code == 404
    check = client.get("/check/20260927-190000-aaaaaa").text
    assert "/3d" not in check and 'id="b3dData"' not in check and "body3d" not in check, "на дашборде нет 3D"
    assert "Снимки исследования" in check and check.count('class="d-thumb') == 3, "галерея снимков"
    assert f'href="#{SPINE["key"]}"' in check and f'id="{SPINE["key"]}"' in check, "снимок в галерее ведёт к своей карточке"
    assert 'class="d-thumb bad"' in check and 'class="d-thumb ok"' in check


def test_three_is_served_locally(client):
    for f in ("three.module.min.js", "three.core.min.js", "OrbitControls.js", "LICENSE"):
        assert client.get(f"/static/vendor/three/{f}").status_code == 200, f
    js = client.get("/static/body3d.js").text
    assert "from 'three'" in js and "http" not in js.split("import")[1].split(";")[0], "без CDN — работает без сети"


def test_card_switches_to_plain_xray(client):
    """28.09, Юрий: на карточке можно увидеть чистый рентгеновский снимок без разметки."""
    fake_run("20260927-190000-aaaaaa", [SPINE, HIP])
    check = client.get("/check/20260927-190000-aaaaaa").text
    assert 'data-raw="/runs/20260927-190000-aaaaaa/files/s1_original.png"' in check
    assert 'data-atlas="/runs/20260927-190000-aaaaaa/files/s1_overlay.png"' in check
    assert check.count('class="pic-sw"') == 2 and 'class="pic-sw all"' in check and "чистый снимок" in check
    assert "dxaqc_pic_view" in check, "общий выбор запоминается"
