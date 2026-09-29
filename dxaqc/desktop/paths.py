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
