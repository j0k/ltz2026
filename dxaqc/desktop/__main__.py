# -*- coding: utf-8 -*-
"""Запуск настольного приложения Kostik (#138).

    kostik                     окно приложения (в Linux; прежняя команда dxaqc тоже работает)
    kostik файл.dcm папка/ …   сразу проверить файлы («Открыть с помощью»)
    kostik --selftest          проверка установки: анализ фантома, сервер, MCP — отчёт и код возврата
    kostik --mcp-stdio         MCP-сервер для Claude Desktop по stdio
    kostik --browser           окно в браузере вместо встроенного
    kostik --host 0.0.0.0      на каком адресе слушает сервер; по умолчанию 127.0.0.1
    kostik --show-all-hosts    все адреса для --host: этот компьютер, все интерфейсы, каждый интерфейс по имени
    kostik --check папка/      проверить и напечатать описание по каждому снимку в консоль; --json, --out, --open
    kostik --results           описание последней или названной проверки; kostik --runs — список проверок

Окно — pywebview (WebView2 в Windows, WebKitGTK в Linux); если его нет — Edge или Chrome в режиме приложения,
в крайнем случае обычный браузер. Сервер слушает только 127.0.0.1, пока не задан другой адрес: --host.

Три процесса, чтобы окно никогда не подвисало:
  окно      — этот процесс: лёгкий, без numpy и FastAPI; открывается сразу, с заставкой и ходом запуска;
  движок    — `kostik --engine`: сервер FastAPI со страницами и API; упал — окно перезапускает его само;
  проверка  — `python -m dxaqc.desktop.worker`: каждая проверка отдельно и с пониженным приоритетом.
Внизу окна всегда строка состояния: что идёт, сколько осталось, отвечает ли движок.
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

from dxaqc.desktop import APP_NAME, DEFAULT_PORT, hosts, paths


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
    os.environ["DXAQC_PUBLIC_URL"] = hosts.url(port)


def _log_to_file():
    """pythonw в Windows без консоли: всё, что печатает сервис, — в журнал в папке данных."""
    if sys.stdout is None or sys.stderr is None or os.environ.get("DXAQC_LOG_TO_FILE"):
        f = open(paths.log_path(), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] запуск {APP_NAME}", flush=True)


def _log_to_file_quiet():
    """pythonw без консоли и команды с выводом в файл: печатать некуда — в журнал, без отметки о запуске."""
    if sys.stdout is None or sys.stderr is None:
        sys.stdout = sys.stderr = open(paths.log_path(), "a", encoding="utf-8", buffering=1)


def _free_port(preferred: int) -> int:
    host = hosts.bind_host()
    for port in (preferred, 0):
        with socket.socket(hosts.family(host)) as s:
            try:
                s.bind((host, port))
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


def _write_instance(port: int):
    with open(_instance_file(), "w", encoding="utf-8") as f:
        json.dump({"port": port, "pid": os.getpid(), "host": hosts.local()}, f)


def running_instance() -> str | None:
    """Адрес уже открытой копии приложения (http://127.0.0.1:8765) или None."""
    try:
        with open(_instance_file(), encoding="utf-8") as f:
            inst = json.load(f)
        base = hosts.url(int(inst["port"]), inst.get("host") or hosts.DEFAULT)
    except (OSError, ValueError, KeyError):
        return None
    h = _get(base + "/api/health", 1.5)
    return base if h and h.get("status") == "ok" else None


# ------------------------------------------------------------------ окно

class Api:
    """Системные диалоги для страницы: window.pywebview.api.* (#140, #141)."""

    def __init__(self, runs_dir: str):
        self._runs_dir = runs_dir
        self._window = None

    def _dialog(self, kind: str, **kw):
        import webview
        fd = getattr(webview, "FileDialog", None)
        const = {"open": fd.OPEN if fd else webview.OPEN_DIALOG, "folder": fd.FOLDER if fd else webview.FOLDER_DIALOG,
                 "save": fd.SAVE if fd else webview.SAVE_DIALOG}[kind]
        res = self._window.create_file_dialog(const, **kw)
        if res is None:
            return []
        return [res] if isinstance(res, str) else list(res)

    def pick_files(self):
        return self._dialog("open", allow_multiple=True,
                            file_types=("DICOM и архивы (*.dcm;*.DCM;*.zip;*.dicom)", "Все файлы (*.*)"))

    def pick_folder(self):
        return self._dialog("folder")

    def save_file(self, run_id: str, name: str):
        src = os.path.join(self._runs_dir, os.path.basename(run_id), "out", os.path.basename(name))
        if not os.path.isfile(src):
            return {"error": "файл результата не найден — дождитесь окончания проверки"}
        dest = self._dialog("save", save_filename=f"dxaqc_{os.path.basename(run_id)}_{os.path.basename(name)}")
        if not dest:
            return {"cancelled": True}
        shutil.copyfile(src, dest[0])
        return {"saved": dest[0]}

    def open_run_folder(self, run_id: str):
        folder = os.path.join(self._runs_dir, os.path.basename(run_id), "out")
        paths.open_path(folder if os.path.isdir(folder) else self._runs_dir)
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


SPLASH = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#12151a;color:#e8edf3;font:15px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
.w{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}
h1{margin:0;font-size:42px;font-weight:800;color:#5aa7ff;letter-spacing:-.02em}
.sub{color:#8b96a3}.bar{width:320px;height:6px;border-radius:3px;background:#262b33;overflow:hidden}
.bar i{display:block;height:100%;width:30%;background:#5aa7ff;border-radius:3px;animation:m 1.1s ease-in-out infinite alternate}
@keyframes m{from{margin-left:0}to{margin-left:70%}}
.st{position:fixed;left:0;right:0;bottom:0;height:30px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#16191f;
 border-top:1px solid #2a2f38;font-size:13px}.d{width:9px;height:9px;border-radius:50%;background:#5aa7ff}
.bad .d{background:#e5534b}.bad .bar i{background:#e5534b;animation:none;width:100%}
pre{max-width:80%;max-height:30vh;overflow:auto;color:#c9a0a0;font-size:12px;white-space:pre-wrap}
button{font:inherit;padding:8px 18px;border-radius:10px;border:0;background:#5aa7ff;color:#fff;cursor:pointer}
</style></head><body><div class="w" id="w"><h1>Kostik</h1><div class="sub">контроль качества денситометрии</div>
<div class="bar"><i></i></div><pre id="log" hidden></pre><button id="rb" hidden onclick="pywebview.api.restart_engine()">Перезапустить движок</button></div>
<div class="st"><span class="d"></span><span id="msg">Запускаю движок анализа…</span></div>
<script>function kostikStatus(t,bad,log){document.getElementById('msg').textContent=t;document.body.className=bad?'bad':'';
const l=document.getElementById('log');l.hidden=!log;l.textContent=log||'';document.getElementById('rb').hidden=!bad}</script>
</body></html>"""


class Engine:
    """Процесс движка: запуск, ожидание готовности, перезапуск после падения."""

    def __init__(self, port: int):
        self.port, self.proc, self.restarts = port, None, 0
        self.base = hosts.url(port)

    def start(self, output=None):
        kw = {} if output is None else {"stdout": output, "stderr": output}
        verbose = os.environ.get("DXAQC_VERBOSE") == "1"
        if sys.platform.startswith("win") and not verbose:
            kw["creationflags"] = 0x08000000                     # CREATE_NO_WINDOW; в подробном режиме движок печатает в ту же консоль
        env = dict(os.environ, PYTHONIOENCODING="utf-8", DXAQC_PROC="движок")
        if not verbose:
            env["DXAQC_LOG_TO_FILE"] = "1"
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "dxaqc.desktop", "--engine", "--port", str(self.port),
                                      "--parent", str(os.getpid())], env=env, stdin=subprocess.DEVNULL, **kw)
        return self.proc

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait_ready(self, timeout: float = 90.0, on_wait=None) -> bool:
        from dxaqc.desktop import verbose
        t0, last = time.time(), 0.0
        while time.time() - t0 < timeout:
            if not self.alive():
                if verbose.enabled():
                    verbose.fail(f"движок завершился до готовности, код {self.proc.returncode if self.proc else '?'}")
                return False
            if _get(self.base + "/api/health", 1.0):
                if verbose.enabled():
                    verbose.ok(f"движок отвечает на /api/health через {time.time() - t0:.1f} с")
                return True
            if on_wait:
                on_wait(time.time() - t0)
            if verbose.enabled() and time.time() - t0 - last >= 2.0:
                last = time.time() - t0
                verbose.log(f"жду движок: {last:.0f} с, процесс {'жив' if self.alive() else 'ЗАВЕРШИЛСЯ'}, порт {self.port}")
            time.sleep(0.15)
        if verbose.enabled():
            verbose.fail(f"движок не ответил за {timeout:.0f} с")
        return False

    def stop(self):
        if self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _log_tail(n: int = 12) -> str:
    try:
        with open(paths.log_path(), encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:]).strip()
    except OSError:
        return ""


class Ui(Api):
    """Окно: заставка сразу, страница — когда движок готов; следит за движком и перезапускает его."""

    def __init__(self, engine: Engine, start_path: str, files: list[str]):
        super().__init__(paths.runs_dir())
        self._engine, self._start_path, self._files, self._closing = engine, start_path, files, False

    def _status(self, text: str, bad: bool = False, log: str = ""):
        from dxaqc.desktop import verbose
        if verbose.enabled():
            (verbose.fail if bad else verbose.log)(f"окно: {text}")
        if self._window is not None:
            try:
                self._window.evaluate_js(f"window.kostikStatus && kostikStatus({json.dumps(text)}, {json.dumps(bad)}, {json.dumps(log)})")
            except Exception:  # noqa: BLE001 — окно ещё не готово или уже закрыто
                pass

    def _boot(self):
        if not self._engine.alive():
            self._engine.start()
        hints = ((0, "Запускаю движок анализа…"), (3, "Загружаю модели анализа…"), (10, "Готовлю интерфейс… первый запуск дольше"))
        ok = self._engine.wait_ready(on_wait=lambda t: self._status(next(h for s, h in reversed(hints) if t >= s)))
        if not ok:
            self._status("Движок анализа не запустился", True, _log_tail())
            return False
        url = self._engine.base + self._start_path
        if self._files:
            r = _post(self._engine.base + "/desktop/run-local", {"paths": self._files})
            self._files = []
            if r and r.get("url"):
                url = self._engine.base + r["url"]
        self._status("Открываю…")
        print(f"[ui] движок готов, открываю {url}", flush=True)
        self._window.load_url(url)
        return True

    def restart_engine(self):
        self._engine.stop()
        threading.Thread(target=self._boot, daemon=True).start()
        return True

    def _watch(self):
        """Поток окна: первый запуск движка, дальше — перезапуск, если он упал (до 3 раз подряд)."""
        self._boot()
        while not self._closing:
            time.sleep(1.0)
            if self._closing or self._engine.alive():
                continue
            if self._engine.restarts >= 3:
                self._window.load_html(SPLASH)
                time.sleep(0.5)
                self._status("Движок анализа падает при запуске — подробности в журнале", True, _log_tail())
                return
            self._engine.restarts += 1
            print(f"[ui] движок завершился (код {self._engine.proc.returncode}), перезапуск {self._engine.restarts}", flush=True)
            self._start_path = "/"
            self._boot()


def open_window(engine: Engine, start_path: str, files: list[str], prefer_browser: bool = False) -> str:
    """Открыть окно и дождаться, пока его закроют. → какой способ сработал."""
    if not prefer_browser and not os.environ.get("DXAQC_NO_WEBVIEW"):
        try:
            import webview
            ui = Ui(engine, start_path, files)
            win = webview.create_window(APP_NAME, html=SPLASH, width=1320, height=900, min_size=(900, 640), js_api=ui,
                                        text_select=True, background_color="#12151a")
            ui._window = win
            try:
                win.events.closing += lambda: setattr(ui, "_closing", True)
            except AttributeError:                       # старый pywebview без событий
                pass
            print("[window] окно pywebview, движок в отдельном процессе", flush=True)
            paths.set_app_identity()
            threading.Thread(target=paths.set_window_icon, daemon=True, name="window-icon").start()
            kw = {}
            # GTK и Qt: иконка окна Linux. В Windows нельзя: pywebview 6 отдаёт файл в System.Drawing.Icon, PNG роняет окно;
            # там иконку ставит set_window_icon
            if not sys.platform.startswith("win") and os.path.isfile(os.path.join(paths.ASSETS, "icon.png")):
                kw["icon"] = os.path.join(paths.ASSETS, "icon.png")
            try:
                webview.start(ui._watch, private_mode=False, storage_path=os.path.join(paths.data_dir(), "webview"), **kw)
            except TypeError:                                                # pywebview без параметра icon
                webview.start(ui._watch, private_mode=False, storage_path=os.path.join(paths.data_dir(), "webview"))
            ui._closing = True
            return "pywebview"
        except Exception as exc:  # noqa: BLE001 — нет WebView2 / WebKitGTK: браузер в режиме приложения
            print(f"[window] встроенное окно недоступно: {type(exc).__name__}: {exc}", flush=True)
    if not engine.alive():
        engine.start()
    if not engine.wait_ready():
        print("[server] движок не запустился", flush=True)
        return "failed"
    url = engine.base + start_path
    if files:
        r = _post(engine.base + "/desktop/run-local", {"paths": files})
        if r and r.get("url"):
            url = engine.base + r["url"]
    proc = _browser_app(url)
    if proc:
        print(f"[window] окно браузера в режиме приложения: {url}", flush=True)
        proc.wait()
        return "browser-app"
    import webbrowser
    webbrowser.open(url)
    _wait_heartbeat(engine)
    return "browser"


def _wait_heartbeat(engine: Engine):
    """Обычный браузер: работаем, пока открытая страница опрашивает строку состояния; тишина 90 с — выход."""
    t0 = time.time()
    while engine.alive():
        time.sleep(5)
        s = _get(engine.base + "/desktop/ping-age", 2.0) or {}
        age = s.get("age")
        if age is None and time.time() - t0 > 600:
            return
        if age is not None and age > 90:
            return


def _parent_watch(pid: int, server):
    """Движок: окно закрылось или упало — завершаемся, не оставляя процесс-сироту."""
    while True:
        time.sleep(2)
        try:
            if sys.platform.startswith("win"):
                import ctypes
                h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)       # PROCESS_QUERY_LIMITED_INFORMATION
                code = ctypes.c_ulong()
                alive = bool(h) and ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
            else:
                os.kill(pid, 0)
                alive = os.getppid() == pid
        except OSError:
            alive = False
        if not alive:
            print("[engine] окно закрыто — завершаюсь", flush=True)
            server.should_exit = True
            return


def serve(port: int, parent: int | None = None):
    """Движок: сервер FastAPI в этом процессе."""
    from dxaqc.desktop import verbose
    vb = verbose.enabled()
    if vb:
        import faulthandler
        faulthandler.dump_traceback_later(40, repeat=False)              # запуск завис — увидим, где именно
        verbose.log("импорт uvicorn")
    import uvicorn
    if vb:
        verbose.log("импорт сервиса dxaqc.web.app (модели, шаблоны, маршруты)")
    t = time.time()
    from dxaqc.web import app as webapp
    if vb:
        verbose.ok(f"сервис импортирован за {time.time() - t:.2f} с, режим {'приложение' if webapp.DESKTOP else 'сервер'}, данные {webapp.DATA}")
    server = uvicorn.Server(uvicorn.Config(webapp.app, host=hosts.bind_host(), port=port, log_level="debug" if vb else "warning",
                                           access_log=vb))
    if parent:
        threading.Thread(target=_parent_watch, args=(parent, server), daemon=True, name="parent-watch").start()
    print(f"[engine] {hosts.url(port)}/ · слушает {hosts.bind_host()}", flush=True)
    if vb:
        def _startup_done():                                            # сервер поднялся — стек зависания больше не нужен
            for _ in range(600):
                if getattr(server, "started", False):
                    faulthandler.cancel_dump_traceback_later()
                    verbose.ok("сервер принимает соединения")
                    return
                time.sleep(0.1)
        threading.Thread(target=_startup_done, daemon=True, name="startup-watch").start()
    server.run()
    if vb:
        verbose.log("движок остановлен")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dxaqc", add_help=False)
    ap.add_argument("files", nargs="*", help="файлы или папки для проверки")
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("--version", "-V", action="store_true")
    ap.add_argument("--author", action="store_true")
    ap.add_argument("--mcp", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mcp-stdio", action="store_true")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--engine", action="store_true", help=argparse.SUPPRESS)       # процесс движка, запускает окно
    ap.add_argument("--parent", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--host", default="")
    ap.add_argument("--show-all-hosts", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--results", nargs="?", const="last", default="")
    ap.add_argument("--runs", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    a, unknown = ap.parse_known_args(argv)
    from dxaqc.desktop import cli
    if unknown:                                          # неизвестный параметр — не молча, а с подсказкой
        print(f"Неизвестный параметр: {' '.join(unknown)}\nСправка: {cli.prog()} --help", file=sys.stderr)
        return 2
    if a.help:
        print(cli.help_text())
        return 0
    if a.version:
        print(cli.version_text())
        return 0
    if a.author:
        print(cli.author_text())
        return 0
    if a.show_all_hosts:
        print(hosts.listing(a.host or None))
        return 0
    host = a.host or ("" if a.engine else os.environ.get("DXAQC_HOST", ""))     # движок получает адрес через окружение
    if host:
        err = hosts.check(host)
        if err:
            print(f"{err}\nСправка: {cli.prog()} --help", file=sys.stderr)
            return 2
        os.environ["DXAQC_HOST"] = host
    if a.mcp:
        configure_env(a.port or None)
        print(cli.mcp_text())
        return 0
    if a.mcp_stdio:
        configure_env(a.port or None)
        from dxaqc.desktop import mcp_stdio
        return mcp_stdio.serve()
    if a.check or a.results or a.runs:                   # консоль: описание проверки без окна и без браузера
        configure_env(a.port or None)
        _log_to_file_quiet()
        from dxaqc.desktop import check
        return check.main(a, sys.modules[__name__])
    from dxaqc.desktop import verbose
    if a.verbose:
        configure_env(a.port or None)
        verbose.enable()
        print(f"Подробный журнал запуска {APP_NAME}. Файл журнала: {verbose.log_path()}", flush=True)
    elif verbose.enabled() and (a.engine or os.environ.get("DXAQC_PROC")):
        verbose.enable(fresh=False)                      # дочерний процесс: дописываем в тот же файл
    if a.selftest:
        rc = 0
        if a.verbose:
            rc = 1 if verbose.report(service=False) else 0
        from dxaqc.desktop import selftest
        return selftest.run() or rc

    configure_env(a.port or None)
    if not a.verbose:
        _log_to_file()
    if a.engine:
        return serve(a.port, a.parent or None)
    if a.verbose:
        verbose.report()
        verbose.header("Запуск программы")
    files = [os.path.abspath(f) for f in a.files]
    other = running_instance()
    if verbose.enabled():
        verbose.log(f"Уже запущенная копия: {other or 'нет'}")
    if other:                                            # вторая копия: передать файлы первой и выйти
        if files:
            _post(other + "/desktop/run-local", {"paths": files, "navigate": True})
        return 0
    port = _free_port(a.port or DEFAULT_PORT)
    configure_env(port)
    if verbose.enabled():
        verbose.log(f"Сервер: слушает {hosts.bind_host()}, порт {port}; файлов на проверку: {len(files)}")
    if not hosts.is_loopback(hosts.bind_host()):
        print(f"[внимание] программа открыта по сети: слушает {hosts.bind_host()}, порт {port}. Входа по паролю в ней нет — "
              "снимки и результаты видны всем, кто достанет до этого адреса.", flush=True)
    if a.no_window:
        _write_instance(port)
        try:
            print(f"[server] {hosts.url(port)}/", flush=True)
            return serve(port)
        finally:
            _remove_instance()
    engine = Engine(port)
    proc = engine.start()                                # движок стартует параллельно с окном
    if verbose.enabled():
        verbose.log(f"Процесс движка запущен: pid {proc.pid}, порт {port}")
    _write_instance(port)
    try:
        how = open_window(engine, "/", files, prefer_browser=a.browser)
        print(f"[window] закрыто ({how})", flush=True)
    finally:
        engine.stop()
        _remove_instance()
    return 0


def _remove_instance():
    try:
        os.remove(_instance_file())
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
