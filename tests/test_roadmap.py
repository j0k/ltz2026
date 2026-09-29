# -*- coding: utf-8 -*-
"""Роудмап: целостность данных, форматы оценок и страница с доской."""
from __future__ import annotations

import importlib
import re


def rm():
    return importlib.import_module("dxaqc.web.roadmap")


def test_data_is_consistent():
    R = rm()
    ids = {i["id"] for i in R.ITEMS}
    assert len(ids) == len(R.ITEMS), "id инициатив уникальны"
    dirs, phases = {d["id"] for d in R.DIRECTIONS}, {p["id"] for p in R.PHASES}
    for it in R.ITEMS:
        assert it["dir"] in dirs and it["phase"] in phases and it["size"] in R.SIZES, it["id"]
        assert it["impact"] in R.IMPACT and it["state"] in R.STATE, it["id"]
        assert it["agent"][0] <= it["agent"][1] and it["human"][0] <= it["human"][1], it["id"]
        assert all(dep in ids for dep in it.get("deps", [])), it["id"]
        assert it["what"] and it["effect"], it["id"]
    assert all(p in ids for p in R.PATH) and len(set(R.PATH)) == len(R.PATH)
    order = {p["id"]: n for n, p in enumerate(R.PHASES)}
    by = {i["id"]: i for i in R.ITEMS}
    for it in R.ITEMS:                       # зависимость не может быть в более позднем этапе, чем то, что от неё зависит
        for dep in it.get("deps", []):
            assert order[by[dep]["phase"]] <= order[it["phase"]], (dep, it["id"])


def test_hours_format_and_totals():
    R = rm()
    assert R._fmt_hours(50, 73) == "50–73 ч", "раньше rstrip('0') превращал 50 в 5"
    assert R._fmt_hours(0.5, 1) == "0,5–1 ч" and R._fmt_hours(0.2, 0.5) == "12–30 мин" and R._fmt_hours(0, 0) == "—"
    d = R.build({13: True, 3: False})
    q_cv = next(i for i in d["items"] if i["id"] == "q_cv")
    assert q_cv["tickets"] == [dict(id=13, closed=True)] and q_cv["step"] == 2
    assert "q_hip" in next(i for i in d["items"] if i["id"] == "q_meta")["blocks"]
    assert d["totals"]["path"] == len(R.PATH) and "ч" in d["totals"]["path_agent"]
    assert all(p["days"] is None or p["days"] >= 1 for p in d["phases"])


def test_page_renders_board(client):
    R = rm()
    html = client.get("/tz/roadmap.html").text
    assert "Роудмап развития" in html
    assert html.count('class="rm-card') == len(R.ITEMS)
    for n in range(1, len(R.PATH) + 1):
        assert f'aria-label="шаг {n} пути"' in html
    for ph in R.PHASES:
        assert ph["until"] in html
    assert 'id="rmData"' in html and "Откуда оценки" in html
    assert client.get("/tz/roadmap", follow_redirects=False).headers["location"] == "/tz/roadmap.html"
    assert client.get("/og/roadmap.jpg").status_code == 200
    assert "/tz/roadmap.html" in client.get("/tz/").text
    assert re.search(r'og:image" content="[^"]+/og/roadmap\.jpg(\?v=\d+)?"', html)
