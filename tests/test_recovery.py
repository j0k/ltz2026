# -*- coding: utf-8 -*-
"""Прогон, оборванный перезапуском сервиса, при старте снова ставится в очередь и доходит до конца."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
needs_data = pytest.mark.skipif(not (ROOT / "data" / "Для теста").exists(), reason="нет тестовых данных организатора")


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/runs/{rid}/progress").json()
        if st["state"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.3)
    raise AssertionError("прогон не завершился")


@needs_data
def test_interrupted_run_is_requeued_on_startup(client):
    app = sys.modules["dxaqc.web.app"]
    rid = client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    assert _wait(client, rid)["state"] == "done"

    status_path = Path(os.environ["DXAQC_DATA"]) / "runs" / rid / "status.json"
    st = json.loads(status_path.read_text(encoding="utf-8"))
    received = st["stages"]["received"]
    # так выглядит прогон после перезапуска контейнера посреди анализа
    os.remove(Path(os.environ["DXAQC_DATA"]) / "runs" / rid / "out" / "manifest.json")
    status_path.write_text(json.dumps(dict(st, state="running", stage="analyze", progress={"done": 2, "total": 3}, finished=None),
                                      ensure_ascii=False), encoding="utf-8")

    app._recover_interrupted()
    after = _wait(client, rid)
    assert after["state"] == "done"
    saved = json.loads(status_path.read_text(encoding="utf-8"))
    assert saved["restarts"] == 1 and saved["stages"]["received"] == received
    assert client.get(f"/api/runs/{rid}").json()["summary"]["images"] == 3

    # прогон, который всё время обрывается, не перезапускается бесконечно
    status_path.write_text(json.dumps(dict(saved, state="running", restarts=app.MAX_RESTARTS), ensure_ascii=False), encoding="utf-8")
    app._recover_interrupted()
    final = json.loads(status_path.read_text(encoding="utf-8"))
    assert final["state"] == "error" and "перезапуском" in final["error"]
