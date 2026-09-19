# -*- coding: utf-8 -*-
"""Страница данных: статистика по реальным файлам организатора и её вывод — только агрегаты."""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
needs_data = pytest.mark.skipif(not (ROOT / "data" / "train" / "Исследования").exists(), reason="нет данных организатора")


def ds():
    return importlib.import_module("dxaqc.web.datastats")


@needs_data
def test_stats_match_known_facts(client):
    d = ds().get(force=True)
    assert d["ok"]
    t = d["train"]
    assert (t["studies"], t["files"], t["unique"], t["extra"]) == (100, 499, 252, 247)
    assert {r["key"]: r["n"] for r in t["regions"]} == {"lumbar_spine": 99, "hip_left": 79, "hip_right": 74}
    assert dict(t["per_study"]) == {1: 22, 2: 4, 3: 74} and sum(k * n for k, n in t["copies"]) == 499
    assert t["tech"]["no_scale"] == 499 and t["tech"]["no_part"] == 499, "в DICOM нет масштаба и области"
    assert {w["width"] for w in t["tech"]["widths"]} == {280, 300, 248}
    assert sorted(i["region"] for i in d["test"]["images"]) == ["hip_left", "hip_right", "lumbar_spine"]
    crit = {c["key"]: c for c in d["labels"]["criteria"]}
    assert (crit["sp_bad"]["bad"], crit["sp_art"]["bad"], crit["rh_pos"]["na"]) == (32, 17, 28)
    assert dict(d["labels"]["spine_combos"])["посторонние предметы"] == 15
    assert ds().get()["signature"] == d["signature"], "второй вызов — из кеша"


@needs_data
def test_page_shows_charts_without_identifiers(client):
    html = client.get("/tz/data.html").text
    assert "Данные задачи 04" in html and "252" in html and "499" in html
    assert html.count('class="dv-crow"') == 10, "десять критериев разметки"
    assert "Нет масштаба" in html and "Нет области в тегах" in html
    assert html.count("<summary>Таблица</summary>") >= 6, "у каждого графика табличный вид"
    assert "data-tip=" in html
    assert not re.search(r"1\.2\.840\.113619\.\d", html), "идентификаторы исследований на странице не показываются"
    assert client.get("/tz/data", follow_redirects=False).headers["location"] == "/tz/data.html"
    assert client.get("/og/data.jpg").status_code == 200
    assert "/tz/data.html" in client.get("/tz/").text


def test_page_explains_missing_data(client, monkeypatch):
    S = ds()
    monkeypatch.setattr(S, "get", lambda force=False: dict(ok=False, error="обучающий набор не подключён"))
    html = client.get("/tz/data.html").text
    assert "не подключён" in html and 'class="dv-crow"' not in html
