# -*- coding: utf-8 -*-
"""Шпаргалка scikit-learn: целостность схемы, оценки у каждого алгоритма, страница и ссылка из документов."""
from __future__ import annotations

import json
import re

from dxaqc.web import ml_map as ML


def test_cheatsheet_data_is_complete_and_consistent():
    nodes = ML.node_map()
    assert len(nodes) == len(ML.NODES), "идентификаторы узлов уникальны"
    for a, b, kind in ML.EDGES:
        assert a in nodes and b in nodes and kind in ML.EDGE_KINDS, (a, b)
    for n in ML.NODES:
        assert 0 < n["x"] < 1280 and 0 < n["y"] < 703, n["id"]
        if n["kind"] == "estimator":
            assert n["region"] in {r["id"] for r in ML.REGIONS}
            assert n["sklearn"] and n["used"] and n["why"] and n["perspective"] in ML.PERSPECTIVE, n["id"]
        if n["kind"] == "decision":
            assert n["ours"], n["id"]
    edges = {(a, b) for a, b, _ in ML.EDGES}
    assert all((a, b) in edges for a, b in zip(ML.TASK_PATH, ML.TASK_PATH[1:])), "путь задачи 04 идёт по стрелкам схемы"
    est = ML.estimators()
    assert len(est) == 18 and est[0]["perspective"] == "high"
    assert nodes["svc_ensemble"]["perspective"] == "high" and nodes["sgd_cls"]["perspective"] == "none"
    assert all(n["used"].startswith("Нет") for n in est), "scikit-learn на стенде пока не используется"


def test_mlmap_page(client):
    r = client.get("/tz/ml-map.html")
    assert r.status_code == 200
    page = r.text
    data = json.loads(re.search(r'<script type="application/json" id="ml-data">(.*?)</script>', page, re.S).group(1))
    assert len(data["nodes"]) == len(ML.NODES) and len(data["edges"]) == len(ML.EDGES) and data["path"] == ML.TASK_PATH
    assert page.count('<tr id="row-') == 18 and "HistGradientBoostingClassifier" in page
    assert "/static/ml-map.js" in page and 'id="mlPath"' in page
    assert client.get("/tz/ml-map", follow_redirects=False).headers["location"] == "/tz/ml-map.html"
    assert 'href="/tz/ml-map.html"' in client.get("/tz/").text
    assert client.get("/static/ml-map.js").status_code == 200 and client.get("/static/ml-map.css").status_code == 200
