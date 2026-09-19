# -*- coding: utf-8 -*-
"""Галерея: индекс всех снимков без идентификаторов, картинки, наш анализ по кнопке и страница."""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
needs_data = pytest.mark.skipif(not (ROOT / "data" / "train" / "Исследования").exists(), reason="нет данных организатора")


def G():
    return importlib.import_module("dxaqc.web.gallery")


def test_expert_mapping_by_region():
    row = dict(sp_bad="1.0", sp_pos="0.0", sp_axis="1.0", sp_art="1.0", rh_bad="0.0", rh_pos="0.0", rh_roi="0.0",
               lh_bad="", comment="сколиоз")
    spine = G().expert_for(row, "lumbar_spine")
    assert spine["labeled"] and spine["bad"] and spine["types"] == ["axis_tilt", "artifact"] and spine["comment"] == "сколиоз"
    assert G().expert_for(row, "hip_right") == dict(labeled=True, bad=False, types=[], types_ru=[], comment="сколиоз")
    assert G().expert_for(row, "hip_left")["labeled"] is False, "нет разметки левого бедра"


def test_agreement_texts():
    A = G().agreement
    exp = dict(labeled=True, bad=True, types=["axis_tilt"])
    assert A(exp, dict(quality_class=1, violation_codes=["axis_tilt"]))["kind"] == "match"
    part = A(exp, dict(quality_class=1, violation_codes=["axis_tilt", "artifact"]))
    assert part["kind"] == "partial" and "лишнее: посторонние предметы" in part["text"]
    assert A(exp, dict(quality_class=0, violation_codes=[]))["kind"] == "mismatch"
    assert A(dict(labeled=True, bad=True, types=["hip_positioning"]), dict(quality_class=None, violation_codes=["hip_not_evaluated_v0"]))["kind"] == "na"
    assert A(dict(labeled=False), dict(quality_class=0, violation_codes=[]))["kind"] == "none"


@needs_data
def test_gallery_end_to_end(client):
    items = G().public_items()
    assert len(items) == 255 and sum(i["ds"] == "test" for i in items) == 3
    html = client.get("/gallery").text
    assert "Галерея снимков" in html and 'href="/gallery"' in html
    data = json.loads(re.search(r'<script type="application/json" id="glData">(.*?)</script>', html, re.S).group(1))
    assert len(data) == 255
    assert not re.search(r"1\.2\.840\.113619\.\d", html) and "/datasets/" not in html, "ни UID, ни путей на странице"
    spine = next(i for i in data if i["region"] == "lumbar_spine" and i["expert"].get("bad"))
    key = spine["key"]
    for url, kind in ((f"/gallery/img/{key}.png", "image/png"), (f"/gallery/thumb/{key}.jpg", "image/jpeg")):
        r = client.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == kind, url
    assert client.get("/gallery/img/zzzzzzzzzzzz.png").status_code == 404
    assert client.get("/gallery/img/000000000000.png").status_code == 404
    other = next(i["key"] for i in data if i["key"] != key)
    assert client.get(f"/gallery/atlas/{other}.png").status_code == 404, "атлас появляется только после анализа"
    r = client.post(f"/api/gallery/{key}/analyze")
    assert r.status_code == 200
    res = r.json()
    assert res["region"] == "lumbar_spine" and res["quality_class"] in (0, 1) and res["agreement"]["kind"] in ("match", "partial", "mismatch")
    assert client.get(res["atlas"].split("?")[0]).status_code == 200
    assert client.post(f"/api/gallery/{key}/analyze").json()["cached"] is True
    assert client.get("/og/gallery.jpg").status_code == 200
