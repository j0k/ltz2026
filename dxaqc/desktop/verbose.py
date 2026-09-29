# -*- coding: utf-8 -*-
"""Подробный журнал запуска (29.09, Юрий: «Kostik.exe --verbose — подробный лог загрузки всех компонентов»).

Пишет по шагам, что происходит: система, установка, папки данных, каждая библиотека с временем и версией, окно и
WebView2, порт, анализ на фантоме, импорт сервиса, старт движка и ожидание его. Всё идёт в консоль и в файл
`dxaqc-verbose.log` в папке данных — его можно прислать разработчикам. Ошибки печатаются с полным traceback.
"""
from __future__ import annotations

import faulthandler
import importlib
import importlib.metadata as md
import os
import platform
import shutil
import socket
import sys
import threading
import time
import traceback

T0 = time.time()
_lock = threading.Lock()
_file = None
counts = {"ok": 0, "warn": 0, "fail": 0}


def enabled() -> bool:
    return os.environ.get("DXAQC_VERBOSE") == "1"


def log_path() -> str:
    from dxaqc.desktop import paths
    return os.path.join(paths.data_dir(), "dxaqc-verbose.log")


def enable(fresh: bool = True):
    """Включить подробный режим в этом процессе; дочерние процессы (движок, проверка) наследуют переменную."""
    global _file
    os.environ["DXAQC_VERBOSE"] = "1"
    os.environ.setdefault("PYWEBVIEW_LOG", "debug")          # pywebview подробно про выбор окна и WebView2
    os.environ.setdefault("PYTHONFAULTHANDLER", "1")
    try:
        _file = open(log_path(), "w" if fresh else "a", encoding="utf-8", buffering=1)
    except OSError:
        _file = None
    try:
        faulthandler.enable(_file or sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def _out(line: str):
    with _lock:
        try:
            print(line, flush=True)
        except Exception:  # noqa: BLE001 — консоли нет (pythonw): остаётся файл
            pass
        if _file:
            try:
                _file.write(line + "\n")
            except Exception:  # noqa: BLE001
                pass


def log(msg: str, tag: str = "INFO"):
    who = os.environ.get("DXAQC_PROC", "окно")
    _out(f"[{time.time() - T0:7.2f} с] [{tag:4}] {who}: {msg}")


def ok(msg: str):
    counts["ok"] += 1
    log(msg, " OK ")


def warn(msg: str):
    counts["warn"] += 1
    log(msg, "WARN")


def fail(msg: str, exc: BaseException | None = None):
    counts["fail"] += 1
    log(msg, "FAIL")
    if exc is not None:
        for line in "".join(traceback.format_exception(exc)).rstrip().splitlines():
            _out("           | " + line)


def header(title: str):
    _out("")
    _out(f"=== {title} " + "=" * max(4, 66 - len(title)))


def step(name: str, fn, optional: bool = False):
    t = time.time()
    try:
        detail = fn()
        ok(f"{name}: {detail or 'готово'} ({time.time() - t:.2f} с)")
        return True
    except Exception as exc:  # noqa: BLE001
        msg = f"{name}: {type(exc).__name__}: {exc} ({time.time() - t:.2f} с)"
        if optional:
            warn(msg + " — необязательный компонент")
        else:
            fail(msg, exc)
        return False


def _ver(mod, dist: str | None = None) -> str:
    v = getattr(mod, "__version__", None)
    if v:
        return str(v)
    try:
        return md.version(dist or mod.__name__)
    except Exception:  # noqa: BLE001
        return "версия неизвестна"


def _is_admin() -> str:
    try:
        if sys.platform.startswith("win"):
            import ctypes
            return "да" if ctypes.windll.shell32.IsUserAnAdmin() else "нет"
        return "да" if os.geteuid() == 0 else "нет"
    except Exception:  # noqa: BLE001
        return "неизвестно"


def report(service: bool = True):
    """Проверка всех компонентов с подробным выводом. Не останавливается на ошибках — печатает всё."""
    from dxaqc import __version__
    from dxaqc.desktop import APP_NAME, APP_VERSION, paths

    header("Система")
    log(f"{APP_NAME} {APP_VERSION} (анализ {__version__})")
    log(f"ОС: {platform.platform()} · {platform.machine()} · процессор: {platform.processor() or '—'} · ядер: {os.cpu_count()}")
    log(f"Python {platform.python_version()} ({platform.python_implementation()}) · {sys.executable}")
    from dxaqc.desktop import cli
    log(f"Каталог установки: {cli.install_dir()}")
    log(f"Рабочая папка: {os.getcwd()} · команда: {' '.join(sys.argv)} · запускатель: {os.environ.get('KOSTIK_PROG', '—')}")
    log(f"Пользователь: {os.environ.get('USERNAME') or os.environ.get('USER') or '—'} · права администратора: {_is_admin()}")
    log(f"Кодировки: stdout={getattr(sys.stdout, 'encoding', None)} · файловая система={sys.getfilesystemencoding()}")
    ram = _ram()
    if ram:
        log(f"Память: {ram}")
    for k in sorted(os.environ):
        if k.startswith(("DXAQC_", "PYWEBVIEW", "KOSTIK")):
            log(f"  {k}={os.environ[k]}")
    for p in sys.path:
        log(f"  sys.path: {p}")

    header("Установка")
    root = os.path.abspath(os.path.join(paths.HERE, "..", ".."))
    for rel in ("dxaqc/desktop/assets/icon.ico", "dxaqc/desktop/assets/icon.png", "dxaqc/desktop/assets/DejaVuSans.ttf",
                "dxaqc/desktop/assets/DejaVuSans-Bold.ttf", "dxaqc/models/hip_trees.npz", "dxaqc/fonts/Inter.ttf"):
        p = os.path.join(root, *rel.split("/"))
        (ok if os.path.isfile(p) else warn)(f"{rel}: {'есть, ' + str(os.path.getsize(p)) + ' байт' if os.path.isfile(p) else 'НЕТ ФАЙЛА'}")
    for name in ("help", "assets"):
        d = os.path.join(paths.HERE, name)
        (ok if os.path.isdir(d) else fail)(f"desktop/{name}: {len(os.listdir(d)) if os.path.isdir(d) else 0} файлов")
    pth = os.path.join(os.path.dirname(sys.executable), "python312._pth")
    if os.path.isfile(pth):
        log("python312._pth: " + " | ".join(open(pth, encoding="utf-8").read().split()))
    exe_dir = os.path.dirname(sys.executable)
    for name in ("Kostik.exe", "Kostik-cli.exe"):
        p = os.path.join(exe_dir, "..", name)
        if os.path.isfile(p):
            ok(f"{name}: {os.path.getsize(p)} байт")

    header("Данные пользователя")
    d = paths.data_dir()
    log(f"Папка данных: {d}")

    def writable():
        p = os.path.join(d, "write-test")
        with open(p, "w") as f:
            f.write("ok")
        os.remove(p)
        u = shutil.disk_usage(d)
        return f"запись работает, свободно {u.free / 1e9:.1f} ГБ из {u.total / 1e9:.1f}"
    step("Запись в папку данных", writable)
    runs = os.path.join(d, "runs")
    log(f"Проверок в истории: {len(os.listdir(runs)) if os.path.isdir(runs) else 0}")
    log(f"Настройки: {'есть' if os.path.isfile(paths.settings_path()) else 'ещё не созданы'} · журнал: {paths.log_path()}")
    md_ = paths.models_dir()
    log(f"Папка моделей: {md_}: {', '.join(os.listdir(md_)) or 'пусто'}")

    header("Библиотеки (импорт с замером времени)")
    libs = [("numpy", None, False), ("PIL", "pillow", False), ("pydicom", None, False), ("pylibjpeg", None, False),
            ("libjpeg", "pylibjpeg-libjpeg", False), ("openjpeg", "pylibjpeg-openjpeg", False), ("openpyxl", None, False),
            ("fastapi", None, False), ("starlette", None, False), ("uvicorn", None, False), ("jinja2", None, False),
            ("multipart", "python-multipart", False), ("markdown_it", "markdown-it-py", False), ("certifi", None, False),
            ("onnxruntime", None, True), ("piper", "piper-tts", True), ("rapidocr_onnxruntime", None, True),
            ("sklearn", "scikit-learn", True), ("webview", "pywebview", True)]
    if sys.platform.startswith("win"):
        libs += [("clr_loader", None, True), ("clr", "pythonnet", True), ("proxy_tools", None, True), ("bottle", None, True)]
    else:
        libs += [("gi", "PyGObject", True)]
    for name, dist, optional in libs:
        if name == "clr":                                   # pythonnet поднимает .NET: при поломке роняет процесс целиком
            step("import clr (pythonnet + .NET), в отдельном процессе", _isolated_clr, optional)
            continue

        def imp(name=name, dist=dist):
            m = importlib.import_module(name)
            where = getattr(m, "__file__", "") or ""
            return f"{_ver(m, dist)} · {os.path.dirname(where) or 'встроенный'}"
        step(f"import {name}", imp, optional)

    header("Окно")
    if sys.platform.startswith("win"):
        wv = _webview2_version()
        (ok if wv else warn)(f"WebView2 Runtime: {wv or 'не найден — встроенное окно недоступно, программа откроется в Edge или Chrome (режим приложения)'}")
        try:
            import webview
            lib = os.path.join(os.path.dirname(webview.__file__), "lib")
            log(f"pywebview lib: {lib}: {', '.join(sorted(os.listdir(lib))[:14]) if os.path.isdir(lib) else 'нет папки'}")
        except Exception as exc:  # noqa: BLE001
            warn(f"pywebview: {type(exc).__name__}: {exc}")
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
                p = os.path.join(base or "", rel)
                if os.path.isfile(p):
                    ok(f"браузер для запасного режима: {p}")
    else:
        def gtk():
            import gi
            found = []
            for ns, vers in (("Gtk", ("3.0",)), ("WebKit2", ("4.1", "4.0"))):
                for v in vers:
                    try:
                        gi.require_version(ns, v)
                        found.append(f"{ns} {v}")
                        break
                    except ValueError:
                        continue
            if len(found) < 2:
                raise RuntimeError("нет Gtk 3 или WebKit2GTK: " + ", ".join(found or ["ничего"]))
            return ", ".join(found)
        step("Gtk и WebKit2GTK", gtk, optional=True)
    log(f"DISPLAY={os.environ.get('DISPLAY', '—')} · WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', '—')}") if not sys.platform.startswith("win") else None

    header("Сеть")
    def port():
        p = int(os.environ.get("DXAQC_PORT") or 8765)
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return f"порт {p} свободен"
            except OSError as e:
                raise RuntimeError(f"порт {p} занят ({e}); приложение возьмёт другой") from e
    step("Порт 127.0.0.1", port, optional=True)

    def loopback():
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        c = socket.create_connection(srv.getsockname(), timeout=2); c.close(); srv.close()
        return "соединение с самим собой работает (брандмауэр не мешает)"
    step("Loopback", loopback)

    header("Анализ и сервис")
    def phantom():
        import tempfile
        from dxaqc import pipeline
        from dxaqc.desktop import synth
        tmp = tempfile.mkdtemp(prefix="dxaqc-verbose-")
        synth.study(os.path.join(tmp, "in"), "artifact")
        t = time.time()
        pipeline.run_batch(os.path.join(tmp, "in"), os.path.join(tmp, "out"))
        import json
        m = json.load(open(os.path.join(tmp, "out", "manifest.json"), encoding="utf-8"))
        for r in m["rows"]:
            log(f"  {r['anatomical_region']}: класс {r['quality_class']} {r.get('violation_list') or ''}")
        shutil.rmtree(tmp, ignore_errors=True)
        return f"{len(m['rows'])} снимка фантома за {time.time() - t:.2f} с, сводка {m['summary']}"
    step("Анализ фантома", phantom)

    def hip():
        from dxaqc import hipmodel
        m = hipmodel.load()
        return f"модель бедра загружена: {sorted(m)[:4] if isinstance(m, dict) else type(m).__name__}"
    step("Модель бедра", hip, optional=True)

    def ocr():
        from dxaqc import ocr as O
        return f"модель распознавания надписей: {O.model_path() if hasattr(O, 'model_path') else 'проверка при первой картинке'}"
    step("OCR", ocr, optional=True)

    def webapp():
        os.environ.setdefault("DXAQC_MODE", "desktop")
        from dxaqc.web import app as A
        return f"сервис импортирован: {len(A.app.routes)} маршрутов, режим {'приложение' if A.DESKTOP else 'сервер'}"
    if service:
        step("Импорт сервиса dxaqc.web.app", webapp)
    else:
        log("Импорт сервиса и MCP проверит самопроверка ниже")

    header("Итог проверки компонентов")
    log(f"успешно: {counts['ok']} · предупреждений: {counts['warn']} · ошибок: {counts['fail']}")
    log(f"Журнал сохранён: {log_path()}")
    return counts["fail"]


def _isolated_clr() -> str:
    import subprocess
    code = "import clr, sys; print('pythonnet', getattr(clr, '__version__', '?'))"
    t = time.time()
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-4:]
        raise RuntimeError(f"импорт упал с кодом {r.returncode}: {' | '.join(tail)[:400]} — нужен .NET Framework 4.8 (есть в Windows 10/11)")
    return f"{r.stdout.strip()} ({time.time() - t:.1f} с)"


def _ram() -> str:
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong), ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong),
                            ("ex", ctypes.c_ulonglong)]
            s = MS(); s.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return f"{s.total / 1e9:.1f} ГБ всего, {s.avail / 1e9:.1f} ГБ свободно"
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
        return f"{pages * size / 1e9:.1f} ГБ всего"
    except Exception:  # noqa: BLE001
        return ""


def _webview2_version() -> str:
    if not sys.platform.startswith("win"):
        return ""
    import winreg
    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
                      (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
                      (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}")):
        try:
            with winreg.OpenKey(root, key) as k:
                return winreg.QueryValueEx(k, "pv")[0]
        except OSError:
            continue
    return ""
