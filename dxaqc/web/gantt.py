# -*- coding: utf-8 -*-
"""Данные для диаграммы Ганта: задачи и вехи проекта из трекера.

Trac читается изнутри сети контейнеров в машинных форматах: список задач — CSV отчёта, точные даты закрытия —
лента событий в RSS (в CSV есть только «изменено»), сроки вех — выгрузка дорожной карты в iCalendar.
Ответы кешируются на пару минут: страницу могут открыть несколько человек подряд, дёргать трекер на каждый заход незачем.
Трекер недоступен — страница честно говорит об этом, а не рисует пустую диаграмму.
"""
from __future__ import annotations

import csv
import io
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

TRAC = (os.environ.get("DXAQC_TRAC_INTERNAL") or os.environ.get("DXAQC_TG_TRAC", "")).rstrip("/")
PUBLIC_TRAC = os.environ.get("DXAQC_TRAC_URL", "https://ltz2026.juri-konoplev.pro/trac/").rstrip("/") + "/"
TTL = 120
DAY = 86400
QUERY = ("/query?format=csv&col=id&col=summary&col=status&col=milestone&col=component&col=time&col=changetime"
         "&max=0&order=id&status=!none")
TIMELINE = "/timeline?ticket=on&format=rss&daysback=365&max=0"
ROADMAP = "/roadmap?format=ics"
_lock = threading.Lock()
_cache: dict = {}


def _fetch(path: str) -> str | None:
    if not TRAC:
        return None
    try:
        with urllib.request.urlopen(TRAC + path, timeout=15) as r:
            return r.read(8_000_000).decode("utf-8-sig", "replace")
    except Exception as exc:  # noqa: BLE001 — трекер недоступен: страница скажет об этом
        print(f"[gantt] {path.split('?')[0]}: {type(exc).__name__}", flush=True)
        return None


def _ts(text: str) -> float | None:
    """Дата Trac из CSV «09/15/26 10:24:38» — в секундах UTC."""
    try:
        return datetime.strptime(text.strip(), "%m/%d/%y %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except (ValueError, AttributeError):
        return None


def _closed_times(rss: str | None) -> dict[int, float]:
    """Когда каждая задача была закрыта в последний раз — из ленты событий."""
    out: dict[int, float] = {}
    for item in re.findall(r"<item>(.*?)</item>", rss or "", re.S):
        m = re.search(r"<title>[^<]*?#(\d+)[^<]*?\bclosed\b", item)
        date = re.search(r"<pubDate>(.*?)</pubDate>", item)
        if not (m and date):
            continue
        try:
            when = parsedate_to_datetime(date.group(1).strip()).timestamp()
        except (TypeError, ValueError):
            continue
        out[int(m.group(1))] = max(when, out.get(int(m.group(1)), 0))
    return out


def _due_dates(ics: str | None) -> dict[str, float]:
    """Сроки вех из дорожной карты: в iCalendar попадают только вехи с датой."""
    text = re.sub(r"\r?\n[ \t]", "", ics or "")      # длинные строки iCalendar переносятся с отступом
    out: dict[str, float] = {}
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        name = re.search(r"^SUMMARY:\s*(?:Milestone\s+)?(.+)$", block, re.M)
        day = re.search(r"^DTSTART;VALUE=DATE:(\d{4})(\d{2})(\d{2})", block, re.M)
        if name and day:
            y, mo, d = (int(x) for x in day.groups())
            out[name.group(1).strip()] = datetime(y, mo, d, tzinfo=timezone.utc).timestamp()
    return out


def _build() -> dict:
    rows = list(csv.DictReader(io.StringIO(_fetch(QUERY) or "")))
    if not rows:
        return dict(ok=False, epics=[], counts=dict(total=0, closed=0, open=0, epics=0, reached=0),
                    start=time.time() - 7 * DAY, end=time.time() + 7 * DAY, now=time.time(), trac_url=PUBLIC_TRAC)
    closed_at = _closed_times(_fetch(TIMELINE))
    due = _due_dates(_fetch(ROADMAP))
    now = time.time()
    groups: dict[str, list] = {}
    for r in rows:
        try:
            tid = int(r.get("id") or 0)
        except ValueError:
            continue
        start = _ts(r.get("Created") or "") or now
        closed = (r.get("Status") or "").strip() == "closed"
        end = closed_at.get(tid) or _ts(r.get("Modified") or "") or now if closed else now
        groups.setdefault((r.get("Milestone") or "").strip() or "Без эпика", []).append(dict(
            id=tid, summary=(r.get("Summary") or "").strip(), status=(r.get("Status") or "").strip(),
            component=(r.get("Component") or "").strip(), closed=closed,
            start=start, end=max(end, start + 1800)))   # получасовой минимум, иначе полоска схлопывается в точку
    epics = []
    for name, tasks in groups.items():
        tasks.sort(key=lambda t: (t["start"], t["id"]))
        done = sum(1 for t in tasks if t["closed"])
        epics.append(dict(
            name=name, due=due.get(name), tasks=tasks, total=len(tasks), closed=done, open=len(tasks) - done,
            start=min(t["start"] for t in tasks), end=max(t["end"] for t in tasks),
            reached=done == len(tasks), url=PUBLIC_TRAC + "milestone/" + urllib.parse.quote(name) if name in due else ""))
    for e in epics:
        e["overdue"] = bool(e["due"] and not e["reached"] and e["due"] < now)
    epics.sort(key=lambda e: (e["due"] or float("inf"), e["start"]))
    counts = dict(total=sum(e["total"] for e in epics), closed=sum(e["closed"] for e in epics),
                  open=sum(e["open"] for e in epics), epics=len(epics), reached=sum(1 for e in epics if e["reached"]))
    start = min(e["start"] for e in epics)
    end = max([e["end"] for e in epics] + [d for d in due.values()] + [now])
    return dict(ok=True, epics=epics, counts=counts, now=now, trac_url=PUBLIC_TRAC,
                start=start - DAY, end=end + DAY, updated=now)


def _layout(d: dict) -> dict:
    """Проценты вместо дат: полоски позиционируются в дорожке, а масштаб потом меняется шириной дорожки."""
    span = max(d["end"] - d["start"], DAY)
    pct = lambda t: round((t - d["start"]) / span * 100, 3)
    for e in d["epics"]:
        e["left"], e["width"] = pct(e["start"]), max(round((e["end"] - e["start"]) / span * 100, 3), 0.4)
        e["due_left"] = pct(e["due"]) if e["due"] else None
        e["progress"] = round(e["closed"] / e["total"] * 100) if e["total"] else 0
        for t in e["tasks"]:
            t["left"], t["width"] = pct(t["start"]), max(round((t["end"] - t["start"]) / span * 100, 3), 0.35)
    d["now_left"] = pct(d["now"])
    d["days"] = round(span / DAY, 1)
    return d


def data(force: bool = False) -> dict:
    """Задачи по эпикам, сроки вех и счётчики; ok=False — трекер не ответил."""
    with _lock:
        fresh = _cache.get("data")
        if force or not fresh or time.time() - _cache.get("at", 0) > TTL:
            fresh = _build()
            _cache.update(data=_layout(fresh), at=time.time())
        return fresh
