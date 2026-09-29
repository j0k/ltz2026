# -*- coding: utf-8 -*-
"""Где приложение хранит данные: проверки, модели, настройки, журнал — только в папке пользователя."""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")


def data_dir() -> str:
    if os.environ.get("DXAQC_HOME"):
        d = os.environ["DXAQC_HOME"]
    elif sys.platform.startswith("win"):
        d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local"), "DXA QC")
    elif sys.platform == "darwin":
        d = os.path.expanduser("~/Library/Application Support/DXA QC")
    else:
        d = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "dxaqc")
    os.makedirs(d, exist_ok=True)
    return d


def models_dir() -> str:
    d = os.path.join(data_dir(), "models")
    os.makedirs(d, exist_ok=True)
    return d


def settings_path() -> str:
    return os.path.join(data_dir(), "settings.json")


def log_path() -> str:
    return os.path.join(data_dir(), "dxaqc.log")


def open_path(path: str):
    """Открыть папку в проводнике или файловом менеджере."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def runs_dir() -> str:
    return os.path.join(data_dir(), "runs")


APP_USER_MODEL_ID = "ru.ltz2026.kostik"


def set_app_identity():
    """Windows: своя группа в панели задач и иконка Kostik вместо иконки pythonw.exe. Вызывать до создания окна."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:  # noqa: BLE001 — иконка не критична
        pass


def set_window_icon(retries: int = 40, delay: float = 0.25) -> bool:
    """Windows: поставить иконку Kostik всем окнам этого процесса (заголовок, Alt+Tab, панель задач).
    pywebview на Windows не умеет icon=, поэтому шлём WM_SETICON сами; окно появляется не сразу — ждём."""
    if not sys.platform.startswith("win"):
        return False
    import ctypes
    import time
    from ctypes import wintypes
    ico = os.path.join(ASSETS, "icon.ico")
    if not os.path.isfile(ico):
        return False
    u = ctypes.windll.user32
    u.LoadImageW.restype = wintypes.HANDLE
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    big = u.LoadImageW(None, ico, 1, u.GetSystemMetrics(11), u.GetSystemMetrics(12), 0x10)      # IMAGE_ICON, LR_LOADFROMFILE
    small = u.LoadImageW(None, ico, 1, u.GetSystemMetrics(49), u.GetSystemMetrics(50), 0x10)
    if not big and not small:
        return False
    pid, found = os.getpid(), []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4):     # верхний уровень без владельца
            found.append(hwnd)
        return True

    for _ in range(retries):
        found.clear()
        u.EnumWindows(each, 0)
        if found:
            for hwnd in found:
                if small:
                    u.SendMessageW(hwnd, 0x80, 0, small)      # WM_SETICON, ICON_SMALL
                if big:
                    u.SendMessageW(hwnd, 0x80, 1, big)        # ICON_BIG
            return True
        time.sleep(delay)
    return False
