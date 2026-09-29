# -*- coding: utf-8 -*-
"""Проверка установки (#144): зависимости, папка данных, анализ фантома, сервер, страницы, MCP — отчёт и код возврата.

Запускается командой dxaqc --selftest или ярлыком «Kostik — проверка установки». Работает во временной папке
данных, чтобы не трогать проверки пользователя; сеть не нужна.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import threading
import time
import traceback
import urllib.request


def run() -> int:
    results: list[tuple[str, bool, str]] = []

    def step(name, fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.time() - t0:.1f} с)".strip()))
        except Exception as exc:  # noqa: BLE001
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            traceback.print_exc(file=sys.stderr)

    tmp = tempfile.mkdtemp(prefix="dxaqc-selftest-")
    os.environ["DXAQC_HOME"] = tmp
    from dxaqc.desktop import __main__ as launcher, paths
    port = launcher._free_port(0)
    launcher.configure_env(port)
    from dxaqc import __version__

    def deps():
        import numpy, pydicom, PIL, openpyxl, fastapi, uvicorn, jinja2, markdown_it  # noqa: F401
        import pylibjpeg, libjpeg, openjpeg  # noqa: F401 — декодеры сжатых DICOM
        return f"Python {platform.python_version()} · {platform.system()} {platform.release()} · numpy {numpy.__version__}"
    step("Библиотеки", deps)

    def window():
        try:
            import webview  # noqa: F401
            return f"pywebview {getattr(webview, '__version__', '')} — встроенное окно доступно"
        except Exception as exc:  # noqa: BLE001
            return f"pywebview недоступен ({type(exc).__name__}) — окно откроется в браузере"
    step("Окно", window)

    def storage():
        p = os.path.join(paths.data_dir(), "write-test")
        with open(p, "w") as f:
            f.write("ok")
        os.remove(p)
        return paths.data_dir()
    step("Папка данных", storage)

    def analysis():
        from dxaqc import pipeline
        from dxaqc.desktop import synth
        src, out = os.path.join(tmp, "phantom"), os.path.join(tmp, "out")
        synth.study(src, "artifact")
        m = pipeline.run_batch(src, out)
        rows = {r["anatomical_region"]: r for r in m["rows"]}
        assert set(rows) == {"lumbar_spine", "hip_left", "hip_right"}, f"области: {sorted(rows)}"
        assert rows["lumbar_spine"]["quality_class"] == 1 and "artifact" in rows["lumbar_spine"]["violation_list"], "предмет не найден"
        for f in ("results.csv", "results.xlsx", "overlays.zip"):
            assert os.path.getsize(os.path.join(out, f)) > 0, f
        return f"3 снимка фантома, найден посторонний предмет, {m['summary']['mean_time']:.2f} с на снимок"
    step("Анализ снимков", analysis)

    state = {}

    def server():
        import uvicorn
        from dxaqc.web import app as webapp
        srv = uvicorn.Server(uvicorn.Config(webapp.app, host="127.0.0.1", port=port, log_level="error", access_log=False))
        state["srv"] = srv
        threading.Thread(target=srv.run, daemon=True).start()
        base = f"http://127.0.0.1:{port}"
        for _ in range(200):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=1) as r:
                    if json.loads(r.read())["status"] == "ok":
                        break
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        else:
            raise RuntimeError("сервер не ответил за 20 секунд")
        for path in ("/", "/help", "/about", "/models", "/assistant", "/settings", "/history"):
            with urllib.request.urlopen(base + path, timeout=10) as r:
                assert r.status == 200, path
        return f"127.0.0.1:{port}, страницы открываются"
    step("Сервер и страницы", server)

    def mcp():
        from dxaqc.web import desktop
        token = desktop.mcp_token()
        base = f"http://127.0.0.1:{port}/mcp"

        def call(payload):
            req = urllib.request.Request(base, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        init = call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        tools = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "analyze_paths" in names and "get_results" in names, names
        return f"{init['result']['serverInfo']['name']} · {len(tools)} инструментов"
    step("MCP-сервер", mcp)

    if state.get("srv"):
        state["srv"].should_exit = True
    ok = all(r[1] for r in results)
    from dxaqc.desktop import APP_VERSION_FULL
    lines = [f"Kostik {APP_VERSION_FULL} (анализ {__version__}) — проверка установки: {'ВСЁ В ПОРЯДКЕ' if ok else 'ЕСТЬ ПРОБЛЕМЫ'}"]
    lines += [f"  {'✓' if r[1] else '✕'} {r[0]}: {r[2]}" for r in results]
    report = "\n".join(lines)
    try:
        print(report)
    except UnicodeEncodeError:                     # консоль Windows без UTF-8
        print(report.encode("ascii", "replace").decode())
    real_home = os.environ.pop("DXAQC_HOME", None)
    try:
        with open(os.path.join(paths.data_dir(), "selftest.txt"), "w", encoding="utf-8") as f:
            f.write(report + "\n")
    except OSError:
        pass
    del real_home
    return 0 if ok else 1
