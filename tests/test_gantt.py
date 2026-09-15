# -*- coding: utf-8 -*-
"""Диаграмма Ганта: разбор выгрузок трекера, признак достижения вех и страница с полосками."""
from __future__ import annotations

import importlib
import re
import sys

import pytest

CSV = """id,Summary,Status,Milestone,Component,Created,Modified
1,Загрузчик DICOM,closed,Веха А,Данные,09/10/26 08:00:00,09/11/26 10:00:00
2,Классификатор области,new,Веха А,Модель,09/11/26 09:00:00,09/11/26 09:30:00
3,Карточка снимка,closed,Веха Б,Веб,09/12/26 07:00:00,09/12/26 12:00:00
4,Без эпика задача,new,,Прочее,09/12/26 08:00:00,09/12/26 08:10:00
"""
RSS = """<rss><channel>
<item><title>Ticket #1 (Загрузчик DICOM) closed</title><pubDate>Fri, 11 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Ticket #1 (Загрузчик DICOM) created</title><pubDate>Thu, 10 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>Ticket #3 (Карточка снимка) closed</title><pubDate>Sat, 12 Sep 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""
ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260929
SUMMARY:Milestone Веха А
END:VEVENT
END:VCALENDAR"""


@pytest.fixture()
def gantt(client, monkeypatch):
    G = importlib.import_module("dxaqc.web.gantt")
    monkeypatch.setattr(G, "_fetch", lambda path: CSV if "query" in path else RSS if "timeline" in path else ICS)
    G.data(force=True)
    yield G
    G._cache.clear()


def test_parses_trac_and_marks_reached_milestones(gantt):
    d = gantt.data()
    assert d["ok"] and d["counts"] == dict(total=4, closed=2, open=2, epics=3, reached=1)
    names = [e["name"] for e in d["epics"]]
    assert names[0] == "Веха А", "эпик со сроком идёт первым"
    assert "Без эпика" in names
    a, b = (next(e for e in d["epics"] if e["name"] == n) for n in ("Веха А", "Веха Б"))
    assert a["due"] and a["due_left"] is not None and not a["reached"] and a["progress"] == 50
    assert b["due"] is None and b["reached"] and b["progress"] == 100
    task = next(t for t in a["tasks"] if t["id"] == 1)
    assert task["closed"] and task["end"] - task["start"] == 26 * 3600, "конец задачи — время закрытия из ленты"
    assert 0 <= task["left"] <= 100 and task["width"] > 0
    assert next(t for t in a["tasks"] if t["id"] == 2)["end"] >= d["now"] - 5, "незакрытая тянется до сегодня"


def test_page_shows_bars_milestones_and_links(client, gantt):
    html = client.get("/tz/gantt.html").text
    assert "Диаграмма Ганта" in html and "gt-bar" in html
    assert html.count('class="gt-row task"') == 4 and html.count("gt-row epic") == 3
    assert "gt-mile" in html and "срок" in html
    assert "2 задач закрыто" in html.replace("<b>", "").replace("</b> ", " ")
    assert '/tz/mindmap.html' in html and 'ticket/1' in html
    assert 'data-start=' in html and "gt-today" in html
    assert len(re.findall(r'class="gt-row task"[^>]*hidden>', html)) == 4, "задачи свёрнуты до нажатия"
    css = client.get("/static/gantt.css").text
    assert ".gt-row[hidden]{display:none}" in css, "иначе display:flex перебивает hidden и задачи видны сразу"
    assert client.get("/og/gantt.jpg").status_code == 200

    docs = client.get("/tz/").text
    assert '/tz/gantt.html' in docs, "карточка на странице документов"


def test_trac_unavailable_is_explained(client, monkeypatch):
    G = importlib.import_module("dxaqc.web.gantt")
    monkeypatch.setattr(G, "_fetch", lambda path: None)
    G.data(force=True)
    try:
        html = client.get("/tz/gantt.html").text
        assert "не отвечает" in html and "gt-row epic" not in html
    finally:
        G._cache.clear()
