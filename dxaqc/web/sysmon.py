# -*- coding: utf-8 -*-
"""Мониторинг сервера для админов: память машины, диск с данными стенда, память контейнера и нагрузка.

Контейнер видит память всей машины через /proc/meminfo, а свой лимит — через cgroup v2. Диск берётся у тома /data:
том лежит на корневом разделе машины, поэтому это то самое место, которое кончается у всех сервисов сразу.
Размеры папок стенда кэшируются на минуту: админку держат открытой и обновляют каждые 15 секунд.
Статус каждой метрики — значок и подпись, цвет только дублирует их.
"""
from __future__ import annotations

import os
import shutil
import threading
import time

PROC = os.environ.get("DXAQC_PROC", "/proc")
CGROUP = os.environ.get("DXAQC_CGROUP", "/sys/fs/cgroup")
DATA = os.environ.get("DXAQC_DATA", "/data")
SIZES_TTL = 60
STATUS = {"good": ("в норме", "✓"), "warning": ("внимание", "!"), "serious": ("высоко", "▲"), "critical": ("критично", "✕")}
# подписи статусов по смыслу метрики: «мало места» уместно у диска, но не у нагрузки процессора
LABELS = {
    "disk": {"serious": "мало места"},
    "ram": {"serious": "мало памяти"},
    "container": {"serious": "близко к лимиту"},
    "load": {"warning": "повышенная", "serious": "высокая", "critical": "перегрузка"},
}
ORDER = ["good", "warning", "serious", "critical"]
# доля занятого, с которой начинается каждый статус
DISK_STEPS = (0.80, 0.90, 0.95)
RAM_STEPS = (0.75, 0.85, 0.92)
CONTAINER_STEPS = (0.70, 0.85, 0.95)
LOAD_STEPS = (0.80, 1.00, 1.50)          # 5-минутная нагрузка на одно ядро
_lock = threading.Lock()
_sizes: dict = {}


def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "—"
    for unit, size in (("ГБ", 1e9), ("МБ", 1e6), ("КБ", 1e3)):
        if abs(n) >= size:
            v = n / size
            text = f"{v:.1f}" if v < 100 else f"{v:.0f}"
            return text.replace(".", ",") + " " + unit
    return f"{int(n)} Б"


def grade(share: float | None, steps: tuple) -> str:
    if share is None:
        return "good"
    level = sum(1 for s in steps if share >= s)
    return ORDER[level]


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def meminfo() -> dict | None:
    text = _read(os.path.join(PROC, "meminfo"))
    if not text:
        return None
    kb = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if rest.strip():
            kb[key] = int(rest.split()[0]) * 1024
    total, avail = kb.get("MemTotal"), kb.get("MemAvailable")
    if not total or avail is None:
        return None
    used = total - avail
    return dict(total=total, available=avail, used=used, share=used / total,
                swap_total=kb.get("SwapTotal", 0), swap_free=kb.get("SwapFree", 0))


def cgroup_memory() -> dict | None:
    """Память контейнера: рабочий набор (без неактивного файлового кэша, который ядро отдаст первым) против лимита."""
    current, limit = _read(os.path.join(CGROUP, "memory.current")), _read(os.path.join(CGROUP, "memory.max"))
    if not current:
        return None
    current = int(current.strip())
    inactive = 0
    for line in (_read(os.path.join(CGROUP, "memory.stat")) or "").splitlines():
        if line.startswith("inactive_file "):
            inactive = int(line.split()[1])
    working = max(0, current - inactive)
    limit = None if not limit or limit.strip() == "max" else int(limit.strip())
    return dict(current=current, working=working, limit=limit, share=working / limit if limit else None)


def disk(path: str = DATA) -> dict | None:
    try:
        du = shutil.disk_usage(path)
    except OSError:
        return None
    return dict(total=du.total, used=du.used, free=du.free, share=du.used / du.total if du.total else None)


def load() -> dict | None:
    text = _read(os.path.join(PROC, "loadavg"))
    if not text:
        return None
    one, five, fifteen = (float(x) for x in text.split()[:3])
    cpus = os.cpu_count() or 1
    return dict(one=one, five=five, fifteen=fifteen, cpus=cpus, share=five / cpus)


def _tree_size(path: str) -> int:
    if os.path.isfile(path):
        return os.lstat(path).st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def data_sizes(force: bool = False) -> list[dict]:
    """Что занимает место в данных стенда, по убыванию; кэш на минуту."""
    with _lock:
        if not force and _sizes and time.time() - _sizes.get("at", 0) < SIZES_TTL:
            return _sizes["rows"]
        labels = {"runs": "прогоны и результаты", "og": "картинки превью", "showcase": "кадры витрины",
                  "tts": "озвучка пояснений", "attachments": "вложения запросов", "app.db": "база учёток"}
        rows = []
        try:
            names = sorted(os.listdir(DATA))
        except OSError:
            names = []
        db = 0
        for name in names:
            path = os.path.join(DATA, name)
            if name.startswith("app.db"):
                db += _tree_size(path)
                continue
            rows.append(dict(name=name, label=labels.get(name, name), bytes=_tree_size(path)))
        if db:
            rows.append(dict(name="app.db", label=labels["app.db"], bytes=db))
        rows.sort(key=lambda r: -r["bytes"])
        for r in rows:
            r["text"] = fmt_bytes(r["bytes"])
        _sizes.update(rows=rows, at=time.time())
        return rows


def _metric(key: str, title: str, share: float | None, steps: tuple, value: str, detail: str, hint: str = "") -> dict:
    status = grade(share, steps)
    label, icon = STATUS[status]
    label = LABELS.get(key, {}).get(status, label)
    return dict(key=key, title=title, share=share, percent=round(share * 100) if share is not None else None,
                value=value, detail=detail, status=status, status_label=label, status_icon=icon, hint=hint)


def snapshot() -> dict:
    metrics = []
    d = disk()
    if d:
        hint = ""
        if grade(d["share"], DISK_STEPS) in ("serious", "critical"):
            hint = ("Диск общий для всех сервисов машины: когда он заполнится, перестанут сохраняться прогоны "
                    "и записываться база учёток.")
        metrics.append(_metric("disk", "Диск", d["share"], DISK_STEPS, f"{fmt_bytes(d['free'])} свободно",
                               f"занято {fmt_bytes(d['used'])} из {fmt_bytes(d['total'])}", hint))
    m = meminfo()
    if m:
        hint = ("Swap нет: при нехватке памяти ядро завершает процессы."
                if not m["swap_total"] and grade(m["share"], RAM_STEPS) != "good" else "")
        metrics.append(_metric("ram", "Память машины", m["share"], RAM_STEPS, f"{fmt_bytes(m['available'])} доступно",
                               f"занято {fmt_bytes(m['used'])} из {fmt_bytes(m['total'])}", hint))
    c = cgroup_memory()
    if c:
        detail = (f"рабочий набор {fmt_bytes(c['working'])} из лимита {fmt_bytes(c['limit'])}" if c["limit"]
                  else f"рабочий набор {fmt_bytes(c['working'])}, лимита нет")
        metrics.append(_metric("container", "Контейнер стенда", c["share"], CONTAINER_STEPS,
                               f"{fmt_bytes((c['limit'] or 0) - c['working'])} до лимита" if c["limit"] else fmt_bytes(c["working"]),
                               detail, "При упоре в лимит контейнер перезапускается, идущий прогон начнётся заново."
                               if grade(c["share"], CONTAINER_STEPS) != "good" else ""))
    ld = load()
    if ld:
        metrics.append(_metric("load", "Нагрузка процессора", ld["share"], LOAD_STEPS,
                               f"{ld['five']:.2f}".replace(".", ",") + f" на {ld['cpus']} ядра",
                               "за 1, 5 и 15 минут: " + " · ".join(f"{x:.2f}".replace(".", ",") for x in (ld["one"], ld["five"], ld["fifteen"]))))
    worst = max((ORDER.index(x["status"]) for x in metrics), default=0)
    sizes = data_sizes()
    return dict(metrics=metrics, status=ORDER[worst], status_label=STATUS[ORDER[worst]][0], status_icon=STATUS[ORDER[worst]][1],
                sizes=sizes,
                data_total=fmt_bytes(sum(r["bytes"] for r in sizes)), at=time.time())
