# -*- coding: utf-8 -*-
"""Mind map ТЗ: дерево разделов, страницы PDF, честные статусы, страница карты и список для печати."""
from __future__ import annotations

import html
import json
import re

from dxaqc.web import tz_mindmap as MM


def test_tree_structure_pages_and_statuses():
    nodes = MM.nodes()
    assert len(MM.TREE["children"]) == 8, "8 веток — по числу цветов палитры"
    assert len(nodes) > 80
    for n in nodes:
        assert n["title"] and (n["page"] is None or 1 <= n["page"] <= 12), n["title"]
        assert n["status"] in (None, *MM.STATUS), n["title"]
        for l in n["links"]:
            assert l["url"].startswith("/"), l
    titles = {n["title"] for n in nodes}
    for must in ("Охват сверху: половина Th12", "Описание нарушений в DICOM SR", "ROC AUC / PR AUC", "time_of_processing",
                 "Не более 3 минут на исследование", "Обученная модель и скрипт инференса"):
        assert must in titles, must
    by = {n["title"]: n for n in nodes}
    assert by["Охват сверху: половина Th12"]["status"] == "todo" and by["Ось позвоночника: наклон до 5°"]["status"] == "done"
    c = MM.counts()
    assert c["total"] == c["done"] + c["partial"] + c["todo"] and c["done"] and c["partial"] and c["todo"]


def test_mindmap_page(client):
    r = client.get("/tz/mindmap.html")
    assert r.status_code == 200
    page = r.text
    data = json.loads(re.search(r'<script type="application/json" id="mm-data">(.*?)</script>', page, re.S).group(1))
    assert data["title"] == MM.TREE["title"] and len(data["children"]) == 8
    c = MM.counts()
    assert f"<b>{c['done']}</b> сделано" in page and f"<b>{c['todo']}</b> не сделано" in page
    assert "/static/tz-mindmap.js" in page and 'id="mmOutline"' in page
    assert html.escape("Посторонние предметы и артефакты", quote=False) in page, "список для печати и без JS"
    meta = dict(re.findall(r'<meta property="(og:[a-z:]+)" content="([^"]*)"', page))
    assert meta["og:title"].startswith("Mind map ТЗ")
    assert client.get("/tz/mindmap", follow_redirects=False).headers["location"] == "/tz/mindmap.html"
    assert 'href="/tz/mindmap.html"' in client.get("/tz/").text
    js, css = client.get("/static/tz-mindmap.js"), client.get("/static/tz-mindmap.css")
    assert js.status_code == 200 and "layout" in js.text and css.status_code == 200
