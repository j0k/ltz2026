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


def test_full_version_carries_build_stamp(monkeypatch):
    """30.09 Юрий: версия для человека — 1.0-Beta-<дата-время сборки>; из исходников — без метки."""
    import importlib
    import types
    import dxaqc.desktop as D
    assert D.APP_VERSION_FULL == (f"{D.APP_VERSION}-{D.BUILD}" if D.BUILD else D.APP_VERSION)
    monkeypatch.setitem(sys.modules, "dxaqc.desktop._build", types.SimpleNamespace(BUILD="20260930-0015"))
    try:
        assert importlib.reload(D).APP_VERSION_FULL == "1.0-Beta-20260930-0015" and D.APP_VERSION == "1.0-Beta"
    finally:
        monkeypatch.undo()
        importlib.reload(D)


def test_hosts_listing_and_urls(monkeypatch):
    """30.09 Юрий: --host — где слушает сервер, --show-all-hosts — все варианты."""
    import ipaddress
    from dxaqc.desktop import hosts as H
    monkeypatch.delenv("DXAQC_HOST", raising=False)
    assert H.bind_host() == "127.0.0.1" and H.url(8765) == "http://127.0.0.1:8765"
    assert H.url(8765, "0.0.0.0") == "http://127.0.0.1:8765" and H.url(8765, "::") == "http://[::1]:8765"
    assert H.url(8765, "192.0.2.10") == "http://192.0.2.10:8765"
    assert H.is_loopback("127.0.0.1") and H.is_loopback("::1") and not H.is_loopback("0.0.0.0")
    assert H.check("127.0.0.1") is None and H.check("0.0.0.0") is None
    assert "не IP-адрес" in H.check("kostik.local") and "слушать нельзя" in H.check("203.0.113.7")
    for ip, _ in H.interfaces():                         # настоящие интерфейсы этой машины: только пригодные адреса
        a = ipaddress.ip_address(ip)
        assert not (a.is_loopback or a.is_link_local or a.is_unspecified), ip
    monkeypatch.setattr(H, "interfaces", lambda: [("192.0.2.10", "Ethernet"), ("2001:db8::1", "VPN")])
    text = H.listing("192.0.2.10").splitlines()
    assert "  ✓ 192.0.2.10 — Ethernet" in text
    assert "    127.0.0.1 — только этот компьютер (по умолчанию)" in text
    assert "    2001:db8::1 — VPN" in text
    assert "    :: — все интерфейсы, IPv6" in text


def test_cli_host_options(tmp_path):
    run = lambda *a: subprocess.run([sys.executable, "-X", "utf8", "-W", "ignore", "-m", "dxaqc.desktop", *a],  # noqa: E731
                                    env=_env(tmp_path), capture_output=True, text=True, encoding="utf-8", timeout=60)
    r = run("--show-all-hosts")
    assert r.returncode == 0 and "✓ 127.0.0.1" in r.stdout and "0.0.0.0 — все интерфейсы" in r.stdout, r.stdout + r.stderr
    assert "✓ 0.0.0.0" in run("--show-all-hosts", "--host", "0.0.0.0").stdout
    r = run("--host", "203.0.113.7", "--no-window")
    assert r.returncode == 2 and "--show-all-hosts" in r.stderr, r.stderr
    r = run("--help")
    assert r.returncode == 0 and "--host АДРЕС" in r.stdout and "--show-all-hosts" in r.stdout


def test_server_listens_on_chosen_host(tmp_path):
    """Сервер на 0.0.0.0: сама программа ходит к нему через 127.0.0.1, адрес записан в instance.json."""
    code = """
import json, os, sys
os.environ["DXAQC_HOST"] = "0.0.0.0"
from dxaqc.desktop import __main__ as M
M.configure_env(0)
port = M._free_port(0); M.configure_env(port)
e = M.Engine(port); e.start(); assert e.wait_ready(120), "движок не запустился"
M._write_instance(port)
import socket
s = socket.create_connection((socket.gethostbyname(socket.gethostname()), port), 5); s.close()
print(json.dumps(dict(base=e.base, public=os.environ["DXAQC_PUBLIC_URL"], running=M.running_instance(),
                      inst=json.load(open(M._instance_file())))))
e.stop()
"""
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", code], env=_env(tmp_path), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr[-2000:]
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["base"].startswith("http://127.0.0.1:") and res["public"] == res["base"] == res["running"], res
    assert res["inst"]["host"] == "127.0.0.1", res


def test_check_from_console(tmp_path):
    """30.09 Юрий: kostik --check печатает описание проверки в консоль — без окна и без страниц программы."""
    from dxaqc.desktop import synth
    synth.study(str(tmp_path / "in"), "artifact")
    run = lambda *a: subprocess.run([sys.executable, "-X", "utf8", "-W", "ignore", "-m", "dxaqc.desktop", *a],  # noqa: E731
                                    env=_env(tmp_path), capture_output=True, text=True, encoding="utf-8", timeout=300)
    report = str(tmp_path / "report")
    r = run("--check", str(tmp_path / "in"), "--json", "--out", report)
    assert r.returncode == 1, r.stdout + r.stderr[-2000:]                    # есть снимок с нарушением
    d = json.loads(r.stdout)
    assert d["state"] == "done" and d["summary"]["images"] == 3 and d["summary"]["bad"] == 1 and d["started_by"] == "консоль"
    bad = [im for im in d["images"] if im["status"] == "bad"]
    assert len(bad) == 1 and bad[0]["violations"][0]["code"] == "artifact" and bad[0]["explanations"] and bad[0]["region_ru"]
    assert "http" not in r.stdout, "описание самодостаточно: ссылок на окно программы в нём нет"
    assert os.path.isfile(d["files"]["results_xlsx"]) and os.path.dirname(d["files"]["results_csv"]) == os.path.abspath(report)
    marked = [im["overlay"] for im in d["images"] if im["overlay"]]
    assert marked and all(os.path.isfile(p) and os.path.dirname(p) == os.path.abspath(report) for p in marked)
    t = run("--results")
    assert t.returncode == 1 and d["run_id"] in t.stdout and "БРАК" in t.stdout and "ГОДЕН" in t.stdout, t.stdout + t.stderr[-2000:]
    assert "посторонний предмет" in t.stdout and "разметка:" in t.stdout and "http" not in t.stdout
    assert d["run_id"] in run("--runs").stdout
    synth.study(str(tmp_path / "ok"), "ok")
    assert run("--check", str(tmp_path / "ok")).returncode == 0
    r = run("--check", str(tmp_path / "нет такой папки"))
    assert r.returncode == 2 and "Не найдено" in r.stderr
    assert run("--check", str(tmp_path / "ok") + '"').returncode == 0, "кавычка на конце пути — привычка Windows, путь верный"
    blocked = tmp_path / "файл вместо папки"
    blocked.write_text("x")
    r = run("--check", str(tmp_path / "ok"), "--out", str(blocked))
    assert r.returncode == 3 and "ГОДЕН" in r.stdout and "Не удалось сложить" in r.stderr
    r = subprocess.run([sys.executable, "-X", "utf8", "-W", "ignore", "-m", "dxaqc.desktop", "--check", str(tmp_path / "ok"), "--json"],
                       env=_env(tmp_path, DXAQC_HOST="203.0.113.7"), capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 2 and "слушать нельзя" in r.stderr, "адрес из окружения проверяется так же, как из --host"
    assert run("--results", "20990101-000000-abcdef").returncode == 2


def test_network_clients_cannot_change_or_read_paths(monkeypatch):
    """Проверка враждебным взглядом: программа открыта по сети (--host 0.0.0.0) — чужой компьютер смотрит страницы,
    но не запускает проверку по пути на диске, не узнаёт пути к файлам и не меняет настройки."""
    from fastapi import HTTPException
    from dxaqc.desktop import hosts as H
    from dxaqc.web import desktop as W

    def ask(method, path, client):
        req = type("R", (), {"method": method, "url": type("U", (), {"path": path})(), "client": type("C", (), {"host": client})()})()
        try:
            W.own_machine(req)
            return 200
        except HTTPException as e:
            return e.status_code
    monkeypatch.setattr(H, "interfaces", lambda: [("192.0.2.10", "Ethernet")])
    monkeypatch.setitem(H._own, "at", 0.0)
    monkeypatch.setenv("DXAQC_HOST", "0.0.0.0")
    stranger, own = "198.51.100.7", "192.0.2.10"
    for method, path in (("POST", "/desktop/run-local"), ("GET", "/api/desktop/describe/last"), ("GET", "/api/desktop/runs"),
                         ("POST", "/settings"), ("POST", "/api/desktop/open-external"), ("POST", "/history/x/delete")):
        assert ask(method, path, stranger) == 403, (method, path)
        assert ask(method, path, own) == ask(method, path, "127.0.0.1") == ask(method, path, "::ffff:127.0.0.1") == 200, (method, path)
    assert ask("GET", "/help", stranger) == ask("GET", "/api/desktop/status", stranger) == 200
    monkeypatch.setenv("DXAQC_HOST", "127.0.0.1")            # слушаем только петлю: чужих запросов не бывает, проверка не мешает
    assert ask("POST", "/desktop/run-local", "testclient") == 200


def test_mcp_describe_run(tmp_path):
    """ИИ-ассистент получает всю проверку одним ответом, с путями к файлам на диске."""
    from dxaqc.desktop import synth
    synth.study(str(tmp_path / "in"), "artifact")
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "analyze_paths", "arguments": {"paths": [str(tmp_path / "in")], "wait": True}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "describe_run", "arguments": {}}}]
    r = subprocess.run([sys.executable, "-W", "ignore", "-m", "dxaqc.desktop", "--mcp-stdio"], env=_env(tmp_path),
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, timeout=240)
    out = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    assert [o["id"] for o in out] == [1, 2, 3], r.stderr[-2000:]
    first, last = out[1]["result"]["structuredContent"], out[2]["result"]["structuredContent"]
    assert first["description"]["run_id"] == last["run_id"] == first["run_id"]
    assert len(last["images"]) == 3 and os.path.isfile(last["files"]["results_csv"])
    assert [im["status"] for im in last["images"]].count("bad") == 1


def test_window_icon_is_not_png_on_windows(monkeypatch, tmp_path):
    """30.09 Юрий: pywebview 6 в Windows читает icon= как .ico — с PNG окно падало сразу после запуска."""
    import types
    from dxaqc.desktop import __main__ as M
    from dxaqc.desktop import paths
    started = {}
    closing = type("Event", (), {"__iadd__": lambda self, f: self})()
    fake = types.SimpleNamespace(create_window=lambda *a, **kw: types.SimpleNamespace(events=types.SimpleNamespace(closing=closing)),
                                 start=lambda func, **kw: started.update(kw))
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.delenv("DXAQC_NO_WEBVIEW", raising=False)
    monkeypatch.setenv("DXAQC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(paths, "set_app_identity", lambda: None)
    monkeypatch.setattr(paths, "set_window_icon", lambda: False)
    for platform, png in (("win32", False), ("linux", True)):
        started.clear()
        monkeypatch.setattr(sys, "platform", platform)
        assert M.open_window(M.Engine(1), "/", []) == "pywebview"
        assert started.get("icon", "").endswith("icon.png") is png, (platform, started)


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
    assert c.post("/api/desktop/open-external", json={"url": "https://i.moscow/lct"}, headers=h).status_code == 200
    opened.clear(); opened.append(url)
    for bad in ("https://evil.example/", "file:///etc/passwd", "javascript:alert(1)", "https://ltz2026.ru.evil.example/"):
        assert c.post("/api/desktop/open-external", json={"url": bad}, headers=h).status_code == 400, bad
    assert opened == [url]
    from dxaqc import desktop as D
    assert next(a for a in D.AUTHORS if a["name"] == "Юрий Коноплёв")["url"] == url
    foot = open(os.path.join(ROOT, "dxaqc", "web", "templates", "_team_footer.html"), encoding="utf-8").read()
    assert f'href="{url}"' in foot and ">Юрий Коноплёв</a>" in foot


def _cli(tmp_path, *args, timeout=240):
    env = _env(tmp_path)
    env["KOSTIK_PROG"] = "Kostik.exe"
    return subprocess.run([sys.executable, "-W", "ignore", "-m", "dxaqc.desktop", *args], env=env, capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8")


def test_cli_help_version_author_mcp(tmp_path):
    """29.09, Юрий: Kostik.exe --help / --version / --author / --mcp печатают в консоль и выходят с кодом 0."""
    h = _cli(tmp_path, "--help")
    assert h.returncode == 0 and "Kostik.exe --verbose" in h.stdout and "--author" in h.stdout and "--mcp" in h.stdout
    for flag in ("--selftest", "--browser", "--no-window", "--port", "--mcp-stdio"):
        assert flag in h.stdout, flag
    assert _cli(tmp_path, "-h").stdout == h.stdout
    v = _cli(tmp_path, "--version")
    assert v.returncode == 0 and v.stdout.startswith("Kostik 1.0-Beta (анализ ") and "Python" in v.stdout and "Каталог установки" in v.stdout
    a = _cli(tmp_path, "--author")
    assert "https://i.moscow/lct" in a.stdout
    assert a.returncode == 0 and "Юрий Коноплёв" in a.stdout and "https://juri-konoplev.pro/ltz2026/" in a.stdout and "Алексей Чуркин" in a.stdout
    m = _cli(tmp_path, "--mcp")
    assert m.returncode == 0 and '"mcpServers"' in m.stdout and "--mcp-stdio" in m.stdout and "analyze_paths" in m.stdout
    bad = _cli(tmp_path, "--foo")
    assert bad.returncode == 2 and "Неизвестный параметр" in bad.stderr and "--help" in bad.stderr


def test_verbose_report_and_file(tmp_path):
    """--verbose --selftest: подробный журнал компонентов в консоль и в файл dxaqc-verbose.log, ошибок нет."""
    r = _cli(tmp_path, "--verbose", "--selftest")
    assert r.returncode == 0, r.stdout[-2500:] + r.stderr[-1500:]
    out = r.stdout
    for part in ("=== Система", "=== Установка", "=== Библиотеки", "=== Окно", "=== Сеть", "=== Анализ и сервис", "import numpy", "import pydicom",
                 "import fastapi", "Анализ фантома", "Итог проверки компонентов", "ошибок: 0", "ВСЁ В ПОРЯДКЕ"):
        assert part in out, part
    log = tmp_path / "home" / "dxaqc-verbose.log"
    assert log.is_file() and "=== Библиотеки" in log.read_text(encoding="utf-8")
