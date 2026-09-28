# -*- coding: utf-8 -*-
"""Тесты живого прогресса: этапы и времена в статусе, распаковка в фоне, поток событий, панель на странице, очередь."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED_ZIP = ROOT / "Для теста.zip"
needs_data = pytest.mark.skipif(not (SEED_ZIP.exists() and (ROOT / "data" / "train" / "Исследования").exists()),
                                reason="нет данных организатора")


def run_id_from(resp) -> str:
    assert resp.status_code == 303, resp.text[:300]
    return resp.headers["location"].rsplit("/", 1)[1]


def wait_state(client, rid, states=("done", "error", "cancelled"), timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/runs/{rid}/progress").json()
        if st["state"] in states:
            return st
        time.sleep(0.2)
    pytest.fail(f"прогон {rid} не дошёл до {states}")


def test_progress_of_missing_run_is_404(client):
    assert client.get("/api/runs/nope/progress").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404


@needs_data
def test_upload_is_unpacked_in_background_with_milestones(client):
    with open(SEED_ZIP, "rb") as f:
        rid = run_id_from(client.post("/runs", files={"files": ("Для теста.zip", f, "application/zip")}, follow_redirects=False))
    first = client.get(f"/api/runs/{rid}/progress").json()
    assert first["stages"]["received"]["start"]
    assert [s["key"] for s in first["stage_list"]] == ["received", "unpack", "read", "analyze", "tables", "done"]

    p = wait_state(client, rid)
    assert p["state"] == "done", p.get("error")
    for key in ("received", "unpack", "read", "analyze", "tables", "done"):
        st = p["stages"][key]
        assert st["start"] <= st["end"], key
    order = [p["stages"][k]["start"] for k in ("unpack", "read", "analyze", "tables", "done")]
    assert order == sorted(order), "этапы идут по порядку"
    assert p["progress"] == {"done": 3, "total": 3} and p["stage"] == "done"
    tally = p["tally"]
    summary = client.get(f"/api/runs/{rid}").json()["summary"]
    assert tally["good"] == summary["good"] and tally["bad"] == summary["bad"] and sum(tally.values()) == 3
    assert len(p["recent"]) == 3 and all(r["name"].lower().endswith(".dcm") for r in p["recent"])


@needs_data
def test_broken_archive_is_reported_as_failure_row(client):
    """28.09: битый архив не срывает проверку — она завершается, по архиву строка отказа с причиной."""
    rid = run_id_from(client.post("/runs", files={"files": ("bad.zip", b"not a zip at all", "application/zip")}, follow_redirects=False))
    p = wait_state(client, rid)
    assert p["state"] == "done", p
    m = client.get(f"/runs/{rid}/files/manifest.json").json()
    assert m["summary"]["failures"] == 1 and "архив zip не распакован" in m["rows"][0]["explanations"][0]


@needs_data
def test_events_stream_reaches_done(client):
    rid = run_id_from(client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False))
    states, stages_seen = [], set()
    with client.stream("GET", f"/api/runs/{rid}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers.get("x-accel-buffering") == "no"
        for line in r.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                states.append(payload["state"])
                stages_seen.update(payload["stages"])
    assert states and states[-1] == "done"
    assert {"received", "read", "analyze", "tables", "done"} <= stages_seen


@needs_data
def test_run_page_shows_live_panel_then_results_and_queue_position(client):
    long_run = run_id_from(client.post("/runs/dataset", data={"dataset": "train", "mode": "sample", "n": "10"}, follow_redirects=False))
    queued = run_id_from(client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False))
    p = client.get(f"/api/runs/{queued}/progress").json()
    if p["state"] == "queued":
        assert p["queue_position"] >= 1
    page = client.get(f"/runs/{long_run}").text
    if client.get(f"/api/runs/{long_run}/progress").json()["state"] in ("queued", "running"):
        assert 'id="live"' in page and 'id="live-data"' in page
        assert 'http-equiv="refresh"' not in page.replace('<noscript><meta http-equiv="refresh" content="3"></noscript>', "")
        live = json.loads(page.split('id="live-data">')[1].split("</script>")[0])
        assert "evaluate" in [s["key"] for s in live["stage_list"]], "у обучающего набора есть этап сравнения с экспертами"
    assert wait_state(client, long_run)["state"] == "done"
    assert wait_state(client, queued)["state"] == "done"
    done_page = client.get(f"/runs/{long_run}").text
    assert 'id="live"' not in done_page and 'data-tile="bad"' in done_page
    assert "evaluate" in client.get(f"/api/runs/{long_run}/progress").json()["stages"]


@needs_data
def test_home_design_switch(client):
    classic = client.get("/", params={"design": "classic"}).text
    bio = client.get("/v1").text   # с 16.09 biotech — главная v1 по умолчанию, с 21.09 она на /v1
    assert 'class="hero"' in client.get("/", params={"design": "bio"}).text
    assert 'class="hero"' not in classic and 'id="upload"' in classic
    assert 'class="hero"' in bio and 'id="upload"' in bio
    assert "up-progress" in classic and "up-progress" in bio, "прогресс отправки есть в обоих вариантах главной"
