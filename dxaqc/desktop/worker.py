# -*- coding: utf-8 -*-
"""Отдельный процесс одной проверки (#138): анализ не делит GIL с сервером и окном — интерфейс не тормозит.

    python -m dxaqc.desktop.worker <run_id>

Ход пишется в status.json прогона, как и раньше; отмена — файл <прогон>/stop, его создаёт сервер.
Приоритет процесса понижен: окно и сервер всегда получают процессор первыми.
"""
from __future__ import annotations

import os
import sys


def lower_priority():
    try:
        if sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL
        else:
            os.nice(10)
    except Exception:  # noqa: BLE001 — не вышло, считаем с обычным приоритетом
        pass


class StopFile:
    """Флаг отмены между процессами: как threading.Event.is_set, но по файлу."""

    def __init__(self, path: str):
        self.path = path

    def is_set(self) -> bool:
        return os.path.exists(self.path)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("использование: python -m dxaqc.desktop.worker <run_id>", file=sys.stderr)
        return 2
    lower_priority()
    if os.environ.get("DXAQC_LOG_TO_FILE") or sys.stdout is None:
        from dxaqc.desktop import paths
        sys.stdout = sys.stderr = open(paths.log_path(), "a", encoding="utf-8", buffering=1)
    from dxaqc.web import app as A
    run_id = os.path.basename(argv[0])
    A._process(run_id, StopFile(os.path.join(A.RUNS, run_id, "stop")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
