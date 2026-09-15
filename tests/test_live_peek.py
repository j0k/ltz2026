# -*- coding: utf-8 -*-
"""Результат снимка во время прогона: пайплайн пишет строки по мере анализа, API отдаёт их порциями,
карточка открывается до manifest.json, панель прогресса содержит список и просмотр."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from dxaqc import pipeline

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "Для теста"
needs_data = pytest.mark.skipif(not TEST_DIR.exists(), reason="нет тестовых данных организатора")


@needs_data
def test_pipeline_writes_rows_while_analyzing(tmp_path):
    out = tmp_path / "out"
    seen = []

    def progress(stage, done=0, total=0, detail="", last=None, tally=None):
        if stage == "analyze" and done:
            lines = (out / pipeline.PARTIAL).read_text(encoding="utf-8").splitlines()
            seen.append(len(lines))
            row = json.loads(lines[-1])
            assert row["key"] == last["key"] and (out / row["overlay_png"]).exists(), "строка и картинка уже на диске"

    man = pipeline.run_batch(str(TEST_DIR), str(out), progress=progress)
    assert seen == [1, 2, 3], "после каждого снимка в файле на строку больше"
    assert not (out / pipeline.PARTIAL).exists(), "после manifest.json промежуточный файл удаляется"
    assert man["summary"]["images"] == 3


def _runs_dir():
    return Path(os.environ["DXAQC_DATA"]) / "runs"


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get(f"/api/runs/{rid}/progress").json()["state"] in ("done", "error", "cancelled"):
            return
        time.sleep(0.3)
    raise AssertionError("прогон не завершился")


@needs_data
def test_live_rows_card_and_panel_before_manifest(client):
    r = client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False)
    rid = r.headers["location"].rsplit("/", 1)[1]
    _wait(client, rid)
    final = client.get(f"/api/runs/{rid}/live-rows").json()
    assert final["final"] is True and final["total"] == 3 and [x["n"] for x in final["rows"]] == [1, 2, 3]

    # превращаем готовый прогон в идущий: строки только в partial.jsonl, manifest.json ещё нет, статус running
    run = _runs_dir() / rid
    man = json.loads((run / "out" / "manifest.json").read_text(encoding="utf-8"))
    ok_rows = [x for x in man["rows"] if x["processing_status"] == "Success"]
    shutil.move(run / "out" / "manifest.json", run / "out" / "manifest.json.bak")
    with open(run / "out" / pipeline.PARTIAL, "w", encoding="utf-8") as f:
        for x in ok_rows[:2]:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
        f.write(json.dumps(ok_rows[2], ensure_ascii=False)[:40])   # недописанная строка
    status_path = run / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status_path.write_text(json.dumps(dict(status, state="running", stage="analyze",
                                           progress={"done": 2, "total": 3}), ensure_ascii=False), encoding="utf-8")
    try:
        live = client.get(f"/api/runs/{rid}/live-rows").json()
        assert live["final"] is False and live["total"] == 2 and live["state"] == "running"
        assert [x["n"] for x in live["rows"]] == [1, 2] and "regions" not in live["rows"][0]
        assert client.get(f"/api/runs/{rid}/live-rows", params={"after": 1}).json()["rows"][0]["n"] == 2
        assert client.get(f"/api/runs/{rid}/live-rows", params={"after": 5}).json()["rows"] == []

        card = client.get(f"/runs/{rid}/images/{ok_rows[0]['key']}")
        assert card.status_code == 200 and 'id="preliminary"' in card.text and "Прогон ещё идёт" in card.text
        assert 'id="atlasOv"' in card.text and "/override" not in card.text, "правки вердикта — после завершения"
        assert client.get(f"/runs/{rid}/images/{ok_rows[2]['key']}").status_code == 404, "недописанная строка не читается"

        page = client.get(f"/runs/{rid}").text
        for marker in ('id="peek"', 'id="peek-follow"', 'data-f="bad"', 'id="live-feed"', 'id="live-done"', 'id="live-viol"'):
            assert marker in page, marker
    finally:
        status_path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
        shutil.move(run / "out" / "manifest.json.bak", run / "out" / "manifest.json")
        (run / "out" / pipeline.PARTIAL).unlink(missing_ok=True)

    done_card = client.get(f"/runs/{rid}/images/{ok_rows[0]['key']}").text
    assert 'id="preliminary"' not in done_card
    assert client.get("/api/runs/nope/live-rows").status_code == 404
