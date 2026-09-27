# -*- coding: utf-8 -*-
"""Запуск настольного приложения DXA QC (#138).

    dxaqc                      окно приложения
    dxaqc файл.dcm папка/ …    сразу проверить файлы («Открыть с помощью»)
    dxaqc --selftest           проверка установки: анализ фантома, сервер, MCP — отчёт и код возврата
    dxaqc --mcp-stdio          MCP-сервер для Claude Desktop по stdio
    dxaqc --browser            окно в браузере вместо встроенного

Окно — pywebview (WebView2 в Windows, WebKitGTK в Linux); если его нет — Edge или Chrome в режиме приложения,
в крайнем случае обычный браузер. Сервер слушает только 127.0.0.1.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from dxaqc.desktop import APP_NAME, DEFAULT_PORT, paths


def configure_env(port: int | None = None):
    """Окружение до импорта сервиса: режим приложения, данные пользователя, шрифты, модели."""
    data = paths.data_dir()
    models = paths.models_dir()
    os.environ.setdefault("DXAQC_MODE", "desktop")
    os.environ["DXAQC_DATA"] = data
    os.environ.setdefault("DXAQC_DATASETS", os.path.join(data, "datasets"))
    os.environ.setdefault("DXAQC_FONT", os.path.join(paths.ASSETS, "DejaVuSans.ttf"))
    os.environ.setdefault("DXAQC_FONT_BOLD", os.path.join(paths.ASSETS, "DejaVuSans-Bold.ttf"))
    os.environ.setdefault("DXAQC_TTS_MODEL", os.path.join(models, "piper", "ru_RU-irina-medium.onnx"))
    os.environ.setdefault("DXAQC_STT_MODEL", os.path.join(models, "whisper-small"))
    os.environ.setdefault("DXAQC_COOKIE_SECURE", "0")
    os.environ.setdefault("DXAQC_TRAC_URL", "")
    os.makedirs(os.environ["DXAQC_DATASETS"], exist_ok=True)
    port = port or int(os.environ.get("DXAQC_PORT") or DEFAULT_PORT)
    os.environ["DXAQC_PORT"] = str(port)
    os.environ["DXAQC_PUBLIC_URL"] = f"http://127.0.0.1:{port}"


def _log_to_file():
    """pythonw в Windows без консоли: всё, что печатает сервис, — в журнал в папке данных."""
    if sys.stdout is None or sys.stderr is None or os.environ.get("DXAQC_LOG_TO_FILE"):
        f = open(paths.log_path(), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] запуск {APP_NAME}", flush=True)


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("нет свободного порта")


def _get(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def _post(url: str, data: dict, timeout: float = 30.0) -> dict | None:
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def _instance_file() -> str:
    return os.path.join(paths.data_dir(), "instance.json")


def running_instance() -> int | None:
    """Порт уже открытой копии приложения или None."""
    try:
        with open(_instance_file(), encoding="utf-8") as f:
            port = int(json.load(f)["port"])
    except (OSError, ValueError, KeyError):
        return None
    h = _get(f"http://127.0.0.1:{port}/api/health", 1.5)
    return port if h and h.get("status") == "ok" else None


# ------------------------------------------------------------------ окно

class Api:
    """Системные диалоги для страницы: window.pywebview.api.* (#140, #141)."""

    def __init__(self, runs_dir: str):
        self.runs_dir = runs_dir
        self.window = None

    def _dialog(self, kind: str, **kw):
        import webview
        fd = getattr(webview, "FileDialog", None)
        const = {"open": fd.OPEN if fd else webview.OPEN_DIALOG, "folder": fd.FOLDER if fd else webview.FOLDER_DIALOG,
                 "save": fd.SAVE if fd else webview.SAVE_DIALOG}[kind]
        res = self.window.create_file_dialog(const, **kw)
        if res is None:
            return []
        return [res] if isinstance(res, str) else list(res)

    def pick_files(self):
        return self._dialog("open", allow_multiple=True,
                            file_types=("DICOM и архивы (*.dcm;*.DCM;*.zip;*.dicom)", "Все файлы (*.*)"))

    def pick_folder(self):
        return self._dialog("folder")

    def save_file(self, run_id: str, name: str):
        src = os.path.join(self.runs_dir, os.path.basename(run_id), "out", os.path.basename(name))
        if not os.path.isfile(src):
            return {"error": "файл результата не найден — дождитесь окончания проверки"}
        dest = self._dialog("save", save_filename=f"dxaqc_{os.path.basename(run_id)}_{os.path.basename(name)}")
        if not dest:
            return {"cancelled": True}
        shutil.copyfile(src, dest[0])
        return {"saved": dest[0]}

    def open_run_folder(self, run_id: str):
        from dxaqc.web.desktop import open_path
        folder = os.path.join(self.runs_dir, os.path.basename(run_id), "out")
        open_path(folder if os.path.isdir(folder) else self.runs_dir)
        return True


def _browser_app(url: str) -> subprocess.Popen | None:
    """Edge или Chrome в режиме приложения: отдельное окно без адресной строки."""
    cands = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    else:
        cands += [shutil.which(n) or "" for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]
    exe = next((c for c in cands if c and os.path.isfile(c)), None)
    if not exe:
        return None
    profile = os.path.join(paths.data_dir(), "browser-profile")
    return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--window-size=1320,900"])


def open_window(url: str, api: Api, prefer_browser: bool = False) -> str:
    """Открыть окно и дождаться, пока его закроют. → какой способ сработал."""
    if not prefer_browser and not os.environ.get("DXAQC_NO_WEBVIEW"):
        try:
            import webview
            win = webview.create_window(APP_NAME, url, width=1320, height=900, min_size=(900, 640), js_api=api,
                                        text_select=True)
            api.window = win
            from dxaqc.web import desktop as webdesk
            webdesk.ctx["navigate"] = win.load_url
            print(f"[window] открываю встроенное окно pywebview: {url}", flush=True)
            webview.start(private_mode=False, storage_path=os.path.join(paths.data_dir(), "webview"))
            return "pywebview"
        except Exception as exc:  # noqa: BLE001 — нет WebView2 / WebKitGTK: браузер в режиме приложения
            print(f"[window] встроенное окно недоступно: {type(exc).__name__}: {exc}", flush=True)
    proc = _browser_app(url)
    if proc:
        print(f"[window] окно браузера в режиме приложения: {url}", flush=True)
        proc.wait()
        return "browser-app"
    import webbrowser
    webbrowser.open(url)
    _wait_heartbeat()
    return "browser"


def _wait_heartbeat():
    """Обычный браузер: работаем, пока открытая страница присылает сигналы; тишина 90 с после первого — выход."""
    from dxaqc.web import desktop as webdesk
    t0 = time.time()
    while True:
        time.sleep(5)
        last = webdesk.ctx.get("last_ping")
        if last is None and time.time() - t0 > 600:
            return
        if last is not None and time.time() - last > 90:
            return


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dxaqc", description=f"{APP_NAME} — контроль качества денситометрии DXA")
    ap.add_argument("files", nargs="*", help="файлы или папки для проверки")
    ap.add_argument("--selftest", action="store_true", help="проверить установку и выйти")
    ap.add_argument("--mcp-stdio", action="store_true", help="MCP-сервер по stdio для ИИ-ассистентов")
    ap.add_argument("--browser", action="store_true", help="открыть в браузере вместо встроенного окна")
    ap.add_argument("--no-window", action="store_true", help="только сервер, без окна (для отладки)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(argv)
    if a.version:
        from dxaqc import __version__
        from dxaqc.desktop import APP_VERSION
        print(f"{APP_NAME} {APP_VERSION} (анализ {__version__})")
        return 0
    if a.mcp_stdio:
        configure_env(a.port or None)
        from dxaqc.desktop import mcp_stdio
        return mcp_stdio.serve()
    if a.selftest:
        from dxaqc.desktop import selftest
        return selftest.run()

    configure_env(a.port or None)
    _log_to_file()
    files = [os.path.abspath(f) for f in a.files]
    other = running_instance()
    if other:                                            # вторая копия: передать файлы первой и выйти
        if files:
            _post(f"http://127.0.0.1:{other}/desktop/run-local", {"paths": files, "navigate": True})
        return 0
    port = _free_port(a.port or DEFAULT_PORT)
    configure_env(port)
    import uvicorn
    from dxaqc.web import app as webapp
    server = uvicorn.Server(uvicorn.Config(webapp.app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    th = threading.Thread(target=server.run, daemon=True, name="server")
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(300):
        if _get(base + "/api/health", 1.0):
            break
        time.sleep(0.1)
    else:
        print("[server] не запустился за 30 секунд", flush=True)
        return 2
    with open(_instance_file(), "w", encoding="utf-8") as f:
        json.dump({"port": port, "pid": os.getpid()}, f)
    url = base + "/"
    if files:
        r = _post(base + "/desktop/run-local", {"paths": files})
        if r and r.get("url"):
            url = base + r["url"]
    try:
        if a.no_window:
            print(f"[server] {url}", flush=True)
            th.join()
        else:
            how = open_window(url, Api(webapp.RUNS), prefer_browser=a.browser)
            print(f"[window] закрыто ({how})", flush=True)
    finally:
        server.should_exit = True
        try:
            os.remove(_instance_file())
        except OSError:
            pass
        th.join(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
