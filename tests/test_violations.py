# -*- coding: utf-8 -*-
"""Каталог нарушений: полнота списка, разбивка примеров и страница с прогоном и без."""
from __future__ import annotations

import importlib
import json
import os
import sys
import time


def V():
    return importlib.import_module("dxaqc.web.violations")


def test_catalog_covers_every_known_code(client):
    app = sys.modules["dxaqc.web.app"]
    codes = {e["code"] for e in V().ENTRIES}
    assert set(app.VIOLATION_RU) <= codes, set(app.VIOLATION_RU) - codes
    for e in V().ENTRIES:
        assert e["tz"] and e["method"] and e["status"] in V().STATUS, e["code"]
    assert {r["code"] for r in V().REJECTS} == {"not_dicom", "not_dxa", "unreadable"}


def fake_run(run_id):
    app = sys.modules["dxaqc.web.app"]
    out = os.path.join(app.RUNS, run_id, "out")
    os.makedirs(out, exist_ok=True)
    now = time.time()
    with open(os.path.join(app.RUNS, run_id, "status.json"), "w") as f:
        json.dump(dict(state="done", title="Весь обучающий набор", created=now, finished=now, dataset="train"), f)
    ex = lambda **k: dict(dict(bad=0, types=[], comment=""), **k)
    rows = [
        dict(key="k1", thumb_png="k1.png", anatomical_region="lumbar_spine", violation_list=["artifact"], quality_class=1,
             expert=ex(bad=1, types=["artifact"])),
        dict(key="k2", thumb_png="k2.png", anatomical_region="lumbar_spine", violation_list=[], quality_class=0,
             expert=ex(bad=1, types=["artifact"], comment="Требует внимание")),
        dict(key="k3", thumb_png="k3.png", anatomical_region="lumbar_spine", violation_list=["axis_tilt"], quality_class=1,
             expert=ex(comment="сколиоз")),
        dict(key="k4", thumb_png="k4.png", anatomical_region="hip_left", violation_list=["hip_not_evaluated_v0"], quality_class=None,
             expert=ex(bad=1, types=["hip_positioning"])),
        dict(key="k5", thumb_png="k5.png", anatomical_region="lumbar_spine", violation_list=[], quality_class=0, expert=ex()),
    ]
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(dict(summary=dict(images=5, studies=100), rows=rows,
                       evaluation=dict(spine_artifact=dict(f1=0.5, tp=1, fp=0, fn=1, tn=3, n=5))), f)


def test_page_with_examples(client):
    fake_run("20260919-120000-aaaaaa")
    html = client.get("/tz/violations.html").text
    assert "Каталог нарушений" in html
    for code in ("coverage", "axis_tilt", "artifact", "hip_positioning", "hip_roi", "not_dicom"):
        assert f"{code}<" in html or f'id="v-{code}"' in html, code
    art = html[html.index('id="v-artifact"'):html.index('id="v-hip_positioning"')]
    assert "Сервис нашёл <span class=\"n\">· 1" in art and "Сервис пропустил <span class=\"n\">· 1" in art
    assert "/images/k1" in art and "/images/k2" in art and "F1 0,50" in art and "точность <b>средняя</b>" in art
    axis = html[html.index('id="v-axis_tilt"'):html.index('id="v-artifact"')]
    assert "Ложная тревога <span class=\"n\">· 1" in axis and "/images/k3" in axis
    hip = html[html.index('id="v-hip_positioning"'):html.index('id="v-hip_roi"')]
    assert "Отмечено экспертами" in hip and "пропустил" not in hip, "бедро не проверяется — «пропустил» нечестно"
    att = html[html.index('id="attention"'):html.index('id="normal"')]
    assert "«требует внимание»" in att and "«сколиоз»" in att
    assert "/images/k5" in html[html.index('id="normal"'):], "норма для сравнения"
    assert client.get("/tz/violations", follow_redirects=False).headers["location"] == "/tz/violations.html"
    assert client.get("/og/violations.jpg").status_code == 200
    assert "/tz/violations.html" in client.get("/tz/").text


def test_toc_is_numbered_and_every_item_links_to_its_card(client):
    import re
    fake_run("20260919-120000-aaaaaa")
    html = client.get("/tz/violations.html").text
    toc = html[html.index('id="toc"'):html.index("</nav>", html.index('id="toc"'))]
    nums = [int(n) for n in re.findall(r'class="no">(\d+)\.<', toc)]
    assert nums == list(range(1, len(nums) + 1)) and len(nums) >= 11, "сквозная нумерация без пропусков"
    anchors = re.findall(r'href="#([\w-]+)"', toc)
    assert len(anchors) == len(nums)
    for a in anchors:
        assert f'id="{a}"' in html, f"пункт оглавления #{a} ведёт в никуда"
    assert "эксперты 2 · нашёл 1 · ложных 0" in toc, "количество по данным у нарушения"
    assert "«сколиоз»" in toc and "Не DICOM" in toc
    body = html[html.index('id="v-coverage"'):]
    assert '<span class="vc-num">1.</span>Неполный охват' in body and 'href="#toc"' in body, "номер в заголовке и путь назад"


def test_study_comment_is_shown_once_per_study_not_per_image(client):
    """«Перелом» написан на исследование: три его снимка — одна группа, а не три «перелома»."""
    rows = [dict(key=f"s{i}", thumb_png=f"s{i}.png", anatomical_region=reg, study_key="study-A", violation_list=[],
                 quality_class=None, expert=dict(bad=1, types=[], comment="перелом"))
            for i, reg in enumerate(("hip_left", "hip_right", "lumbar_spine"))]
    rows.append(dict(key="z", thumb_png="z.png", anatomical_region="lumbar_spine", study_key="study-B", violation_list=[],
                     quality_class=0, expert=dict(bad=0, types=[], comment="перелом L2")))
    c = V().build(dict(rows=rows), "run-x")
    frac = next(a for a in c["attention"] if a["theme"] == "перелом")
    assert len(frac["studies"]) == 2 and [len(s["images"]) for s in frac["studies"]] == [3, 1]
    item = next(i for sec in c["toc"] for i in sec["items"] if i["title"] == "«перелом»")
    assert item["facts"] == "исследований 2 · снимков 4"
