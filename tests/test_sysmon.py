# -*- coding: utf-8 -*-
"""Мониторинг сервера: разбор /proc и cgroup, пороги статусов и доступ только админам."""
from __future__ import annotations

import importlib
import re
import sys

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-1"


def sm():
    return importlib.import_module("dxaqc.web.sysmon")


def fake_system(tmp_path, monkeypatch, *, avail_kb=1_900_000, current=150_000_000, inactive=30_000_000, limit="1572864000"):
    S = sm()
    proc, cg = tmp_path / "proc", tmp_path / "cgroup"
    proc.mkdir(); cg.mkdir()
    (proc / "meminfo").write_text(f"MemTotal: 8132488 kB\nMemFree: 240000 kB\nMemAvailable: {avail_kb} kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
    (proc / "loadavg").write_text("2.50 1.18 0.88 4/1631 7672\n")
    (cg / "memory.current").write_text(f"{current}\n")
    (cg / "memory.max").write_text(f"{limit}\n")
    (cg / "memory.stat").write_text(f"anon 99000000\nfile 42000000\ninactive_file {inactive}\n")
    monkeypatch.setattr(S, "PROC", str(proc))
    monkeypatch.setattr(S, "CGROUP", str(cg))
    return S


def test_grades_and_formatting():
    S = sm()
    load = S._metric("load", "Нагрузка", 1.2, S.LOAD_STEPS, "", "")
    assert load["status"] == "serious" and load["status_label"] == "высокая", "не «мало места» у процессора"
    assert S._metric("disk", "Диск", 0.92, S.DISK_STEPS, "", "")["status_label"] == "мало места"
    assert S.grade(0.5, S.DISK_STEPS) == "good" and S.grade(0.82, S.DISK_STEPS) == "warning"
    assert S.grade(0.92, S.DISK_STEPS) == "serious" and S.grade(0.96, S.DISK_STEPS) == "critical"
    assert S.grade(None, S.DISK_STEPS) == "good"
    assert S.fmt_bytes(3_379_118_080) == "3,4 ГБ" and S.fmt_bytes(145_000_000) == "145 МБ" and S.fmt_bytes(None) == "—"


def test_snapshot_reads_proc_and_cgroup(tmp_path, monkeypatch, client):
    S = fake_system(tmp_path, monkeypatch)
    m = S.meminfo()
    assert m["total"] == 8132488 * 1024 and m["available"] == 1_900_000 * 1024 and m["swap_total"] == 0
    c = S.cgroup_memory()
    assert c["working"] == 120_000_000 and c["limit"] == 1_572_864_000, "рабочий набор без неактивного кэша"
    snap = S.snapshot()
    by = {x["key"]: x for x in snap["metrics"]}
    assert set(by) == {"disk", "ram", "container", "load"}
    assert by["ram"]["status"] == "warning" and "Swap нет" in by["ram"]["hint"], "занято 77% без swap"
    assert by["container"]["status"] == "good" and by["container"]["percent"] == 8 and not by["container"]["hint"], \
        "подсказка только когда есть повод"
    assert by["load"]["status"] == "good", "статус по 5-минутной нагрузке: 1,18 на 2 ядра"
    assert snap["status"] in S.ORDER and snap["status_label"] and snap["sizes"] is not None

    (tmp_path / "cgroup" / "memory.current").write_text("1550000000\n")
    (tmp_path / "cgroup" / "memory.stat").write_text("inactive_file 0\n")
    crit = {x["key"]: x for x in S.snapshot()["metrics"]}["container"]
    assert crit["status"] == "critical" and "лимит" in crit["hint"]
    (tmp_path / "cgroup" / "memory.max").write_text("max\n")
    assert S.cgroup_memory()["limit"] is None and "лимита нет" in {x["key"]: x for x in S.snapshot()["metrics"]}["container"]["detail"]


def test_only_admins_see_server(client):
    A = sys.modules["dxaqc.web.accounts"]
    assert client.get("/admin/api/system").status_code == 403, "гостю — нет"

    A.get_user_by_login("srv-user") or A.create_user("srv-user", PASSWORD)
    user = TestClient(client.app)
    user.post("/login", data={"login": "srv-user", "password": PASSWORD})
    assert user.get("/admin/api/system").status_code == 403 and user.get("/admin").status_code == 403
    user.close()

    A.get_user_by_login("srv-admin") or A.create_user("srv-admin", PASSWORD, role="admin")
    admin = TestClient(client.app)
    admin.post("/login", data={"login": "srv-admin", "password": PASSWORD})
    r = admin.get("/admin/api/system")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    keys = {m["key"] for m in r.json()["metrics"]}
    assert {"disk", "ram"} <= keys
    page = admin.get("/admin").text
    assert 'id="server"' in page and page.count('class="srv-tile"') == len(r.json()["metrics"])
    assert 'href="#server"' in page and "role=\"meter\"" in page
    assert re.search(r'srv-sl">[а-я ]+<', page), "статус подписан словами"
    admin.close()
