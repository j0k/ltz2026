# -*- coding: utf-8 -*-
"""Настольное приложение (#164): самопроверка, MCP по stdio, менеджер моделей, фантом."""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(tmp_path, **kw):
    env = dict(os.environ, DXAQC_HOME=str(tmp_path / "home"), PYTHONPATH=ROOT, DXAQC_NO_WEBVIEW="1", **kw)
    env.pop("DXAQC_MODE", None); env.pop("DXAQC_DATA", None)
    return env


def test_selftest_passes(tmp_path):
    r = subprocess.run([sys.executable, "-W", "ignore", "-m", "dxaqc.desktop", "--selftest"], env=_env(tmp_path),
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr[-2000:]
    assert "ВСЁ В ПОРЯДКЕ" in r.stdout and "MCP-сервер" in r.stdout and "Kostik 1.0-Beta" in r.stdout


def test_mcp_stdio_roundtrip(tmp_path):
    from dxaqc.desktop import synth
    synth.study(str(tmp_path / "in"), "artifact")
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "analyze_paths", "arguments": {"paths": [str(tmp_path / "in")], "wait": True}}}]
    r = subprocess.run([sys.executable, "-W", "ignore", "-m", "dxaqc.desktop", "--mcp-stdio"], env=_env(tmp_path),
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, timeout=240)
    out = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    assert [o["id"] for o in out] == [1, 2, 3], r.stderr[-2000:]
    names = {t["name"] for t in out[1]["result"]["tools"]}
    assert "analyze_paths" in names and "analyze_dataset" not in names, "в приложении нет наборов организатора"
    res = out[2]["result"]["structuredContent"]
    assert res["state"] == "done" and res["summary"]["bad"] == 1 and res["summary"]["images"] == 3


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    (root / "models").mkdir(parents=True)
    blob = os.urandom(300_000)
    (root / "models" / "voice.onnx").write_bytes(blob)
    manifest = {"models": [{"key": "voice", "title": "Голос", "purpose": "озвучка", "version": "1", "dir": "piper",
                            "files": [{"name": "voice.onnx", "size": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
                                       "url": "URL/models/voice.onnx"}]}]}
    handler = lambda *a, **k: _Handler(*a, directory=str(root), **k)  # noqa: E731
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    manifest["models"][0]["files"][0]["url"] = url + "/models/voice.onnx"
    (root / "manifest.json").write_text(json.dumps(manifest))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield url, blob
    srv.shutdown()


def test_model_manager_download_resume_checksum_import(tmp_path, site, monkeypatch):
    url, blob = site
    monkeypatch.setenv("DXAQC_HOME", str(tmp_path / "home"))
    import importlib
    from dxaqc.desktop import models as M
    M = importlib.reload(M)
    monkeypatch.setattr(M, "MANIFEST_URL", url + "/manifest.json")
    m = M.fetch_manifest(force=True)["models"][0]
    part = M.target(m, m["files"][0]) + ".part"
    os.makedirs(os.path.dirname(part), exist_ok=True)
    open(part, "wb").write(blob[:1000])                  # обрыв — докачка с того же места
    M.start("voice")
    for _ in range(200):
        if M.listing()["models"][0]["state"] != "downloading":
            break
        threading.Event().wait(0.05)
    item = M.listing()["models"][0]
    assert item["installed"] and item["state"] == "done", item
    M.delete("voice")
    assert not M.listing()["models"][0]["installed"]
    bad = tmp_path / "voice.onnx"; bad.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="контрольная сумма"):
        M.import_file("voice", "voice.onnx", str(bad))
    good = tmp_path / "ok" / "voice.onnx"; good.parent.mkdir(); good.write_bytes(blob)
    M.import_file("voice", "voice.onnx", str(good))
    assert M.listing()["models"][0]["installed"]
    monkeypatch.setattr(M, "MANIFEST_URL", "http://127.0.0.1:9/none.json")
    off = M.fetch_manifest(force=True)
    assert off["offline"] and off["models"] and "недоступен" in off["error"], "без сети — сохранённый каталог"


def test_phantom_regions():
    from dxaqc import analyze as AN
    from dxaqc.desktop import synth
    assert AN.analyze(synth.spine())["region"] == "lumbar_spine" and AN.analyze(synth.spine())["quality_class"] == 0
    assert AN.analyze(synth.spine(artifact=True))["violations"] == ["artifact"]
    assert AN.analyze(synth.hip("left"))["region"] == "hip_left" and AN.analyze(synth.hip("right"))["region"] == "hip_right"


def test_app_version_is_beta_and_orders_before_release():
    from dxaqc.desktop import APP_VERSION, DEB_VERSION, WIN_VERSION
    from dxaqc.web import desktop as W
    assert APP_VERSION == "1.0-Beta" and WIN_VERSION == "1.0.0" and DEB_VERSION == "1.0~beta"
    assert W._ver("0.5.4") < W._ver("1.0-Beta") < W._ver("1.0") < W._ver("1.0.1")


def test_engine_process_status_bar_and_cancel(tmp_path):
    """#138, 29.09 Юрий: окно отдельно от движка, проверка в своём процессе, строка состояния всегда отвечает."""
    import time
    import urllib.request
    from dxaqc.desktop import synth
    code = f"""
import json, os, sys, time, urllib.request
from dxaqc.desktop import __main__ as M
M.configure_env(0)
port = M._free_port(0); M.configure_env(port)
e = M.Engine(port); e.start(); assert e.wait_ready(120), "движок не запустился"
for i in range(8): __import__("dxaqc.desktop.synth", fromlist=["x"]).study(r"{tmp_path}/in/s%d" % i, "ok")
html = urllib.request.urlopen(e.base + "/").read().decode()
r = M._post(e.base + "/desktop/run-local", {{"paths": [r"{tmp_path}/in"]}})
lat, running = [], False
t0 = time.time()
while time.time() - t0 < 120:
    a = time.time(); s = M._get(e.base + "/api/desktop/status", 3); lat.append(time.time() - a)
    running = running or any(x["state"] == "running" for x in s["runs"])
    if running and not s["runs"]: break
    time.sleep(0.1)
st = json.load(open(os.path.join(os.environ["DXAQC_DATA"], "runs", r["run_id"], "status.json")))
r2 = M._post(e.base + "/desktop/run-local", {{"paths": [r"{tmp_path}/in"]}})
time.sleep(1.5)
bad = urllib.request.Request(e.base + "/api/desktop/cancel/" + r2["run_id"], method="POST")
try: urllib.request.urlopen(bad); forbidden = False
except Exception: forbidden = True
ok = urllib.request.Request(e.base + "/api/desktop/cancel/" + r2["run_id"], method="POST", headers={{"X-Kostik": "1"}})
urllib.request.urlopen(ok)
for _ in range(100):
    s2 = json.load(open(os.path.join(os.environ["DXAQC_DATA"], "runs", r2["run_id"], "status.json")))
    if s2["state"] not in ("queued", "running"): break
    time.sleep(0.2)
print(json.dumps(dict(bar="deskStatus" in html, state=st["state"], running=running, max_ms=round(max(lat) * 1000),
                      forbidden=forbidden, cancelled=s2["state"], engine=e.proc.pid)))
sys.stdout.flush(); os._exit(0)          # окно «упало»: движок должен завершиться сам
"""
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", code], env=_env(tmp_path), capture_output=True, text=True, timeout=300)
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["bar"] and res["state"] == "done" and res["running"], res
    assert res["max_ms"] < 1500, f"строка состояния тормозит во время анализа: {res['max_ms']} мс"
    assert res["forbidden"] and res["cancelled"] == "cancelled", res
    for _ in range(30):
        try:
            os.kill(res["engine"], 0)
        except OSError:
            break
        time.sleep(0.5)
    else:
        pytest.fail("движок остался жить после закрытия окна")


def test_open_external_whitelist_and_header(monkeypatch):
    """29.09, Юрий: имя Юрия ведёт на страницу проекта; в приложении внешние ссылки открываются в системном браузере."""
    import webbrowser
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dxaqc.web import desktop as WD
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u))
    app = FastAPI(); app.include_router(WD.router)
    c = TestClient(app)
    url = "https://juri-konoplev.pro/ltz2026/"
    assert c.post("/api/desktop/open-external", json={"url": url}).status_code == 403, "без заголовка страницы нельзя"
    h = {"X-Kostik": "1"}
    assert c.post("/api/desktop/open-external", json={"url": url}, headers=h).status_code == 200 and opened == [url]
    for bad in ("https://evil.example/", "file:///etc/passwd", "javascript:alert(1)", "https://ltz2026.ru.evil.example/"):
        assert c.post("/api/desktop/open-external", json={"url": bad}, headers=h).status_code == 400, bad
    assert opened == [url]
    from dxaqc import desktop as D
    assert next(a for a in D.AUTHORS if a["name"] == "Юрий Коноплёв")["url"] == url
    foot = open(os.path.join(ROOT, "dxaqc", "web", "templates", "_team_footer.html"), encoding="utf-8").read()
    assert f'href="{url}"' in foot and ">Юрий Коноплёв</a>" in foot
