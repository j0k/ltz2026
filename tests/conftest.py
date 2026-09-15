# -*- coding: utf-8 -*-
"""Общая фикстура тестов: стенд в процессе на временном каталоге и поддельный брокер вопросов к Claude."""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "Для теста"
TRAIN_DIR = ROOT / "data" / "train" / "Исследования"
LABELS = ROOT / "data" / "labels_clean.csv"
BROKER_TOKEN = "test-broker-token"


class FakeBroker:
    """Отвечает мгновенно: «Ответ (режим) на: текст». Текст с FAIL завершается ошибкой."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.calls: list[dict] = []
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _ok(self):
                if self.headers.get("Authorization") != f"Bearer {BROKER_TOKEN}":
                    self._json(401, {"error": "unauthorized"})
                    return False
                return True

            def do_GET(self):
                if not self._ok():
                    return
                if self.path == "/v1/health":
                    return self._json(200, {"status": "ok"})
                m = re.fullmatch(r"/v1/questions/(.+)", self.path)
                job = broker.jobs.get(m.group(1)) if m else None
                return self._json(200, job) if job else self._json(404, {"error": "not found"})

            def do_POST(self):
                if not self._ok():
                    return
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                broker.calls.append(data)
                if "FAIL" in data["text"]:
                    job = dict(id=data["id"], status="error", answer="", error="сломалось в брокере")
                else:
                    job = dict(id=data["id"], status="done", error="", answer=f"Ответ ({data['mode']}) на: {data['text']}")
                broker.jobs[data["id"]] = job
                self._json(202, {"id": data["id"], "status": "queued"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture(scope="session")
def broker():
    b = FakeBroker()
    yield b
    b.server.shutdown()


@pytest.fixture(scope="session")
def client(tmp_path_factory, broker):
    base = tmp_path_factory.mktemp("stand")
    ds = base / "datasets"
    ds.mkdir()
    if TEST_DIR.exists() and TRAIN_DIR.exists() and LABELS.exists():
        (ds / "test").symlink_to(TEST_DIR)
        (ds / "train").symlink_to(TRAIN_DIR)
        (ds / "train_labels.csv").symlink_to(LABELS)
    token = base / "broker_token"
    token.write_text(BROKER_TOKEN + "\n")
    os.environ.update(DXAQC_DATA=str(base / "data"), DXAQC_DATASETS=str(ds), DXAQC_SEED="",
                      DXAQC_ASK_URL=broker.url, DXAQC_ASK_TOKEN_FILE=str(token), DXAQC_ASK_POLL="0.05",
                      DXAQC_COOKIE_SECURE="0")
    sys.path.insert(0, str(ROOT))
    for name in [m for m in sys.modules if m == "dxaqc" or m.startswith("dxaqc.")]:
        del sys.modules[name]  # пути данных и настройки читаются при импорте
    app_module = importlib.import_module("dxaqc.web.app")
    from fastapi.testclient import TestClient
    with TestClient(app_module.app) as c:
        yield c
