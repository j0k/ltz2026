# -*- coding: utf-8 -*-
"""Проверка из командной строки: описание по каждому снимку — в консоль, без окна и без браузера (30.09, Юрий).

    kostik --check ПУТЬ [ПУТЬ…]     проверить файлы, папки, zip-архивы и напечатать описание
    kostik --results [ПРОВЕРКА]     описание уже сделанной проверки; без номера — последней
    kostik --runs                   последние проверки
    … --json                        то же в JSON — для сценариев и ИИ-агентов
    … --out ПАПКА                   сложить в папку таблицы и картинки разметки
    … --open                        показать проверку в открытом окне программы

Эта программа — тонкий клиент движка. Окно открыто — проверку выполняет его движок: она видна в строке состояния и в истории.
Окна нет — на время команды поднимается свой движок без окна и гасится после ответа. Описание строит сам сервис
(dxaqc.web.desktop.describe_run), поэтому в консоли, в окне и у ИИ-ассистента оно одно и то же.

Код возврата: 0 — нарушений нет; 1 — есть снимки с нарушением; 2 — неверные параметры или нет файлов;
3 — проверка не удалась или часть снимков не обработана.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OK, BAD, USAGE, FAILED = 0, 1, 2, 3
NOTE = "Kostik проверяет качество снимков и не ставит диагноз; вердикт по бедру — подсказка модели."


def _say(text: str):
    print(text, file=sys.stderr, flush=True)


def _call(url: str, data: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    """Запрос к движку → (код HTTP, ответ); 0 — движок не ответил."""
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "X-Kostik": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except ValueError:
            return e.code, {}
    except (OSError, ValueError):
        return 0, {}


@contextlib.contextmanager
def engine(M):
    """Адрес движка: открытого окна или своего, поднятого на время команды. → (адрес, окно открыто)."""
    base = M.running_instance()
    if base:
        yield base, True
        return
    os.environ.pop("DXAQC_HOST", None)               # свой движок на время команды — только для этого компьютера
    port = M._free_port(0)
    M.configure_env(port)
    e = M.Engine(port)
    e.start(output=subprocess.DEVNULL)               # печать движка не должна попасть в наш вывод
    try:
        if not e.wait_ready(120):
            raise RuntimeError("движок не запустился; подробности: kostik --verbose")
        yield e.base, False
    finally:
        e.stop()


def _verdict(im: dict) -> str:
    return {"good": "ГОДЕН", "bad": "БРАК", "not_evaluated": "НЕ ОЦЕНЁН", "failed": "НЕ ОБРАБОТАН"}[im["status"]]


def render(d: dict) -> str:
    """Описание проверки текстом."""
    s = d.get("summary") or {}
    out = [f"Kostik {d['app_version']} · анализ {d['analysis_version']}",
           f"Проверка {d['run_id']} · {d.get('title') or ''} · {d.get('created') or ''}".rstrip(" ·"), ""]
    if d["state"] != "done":
        out.append({"error": f"Проверка не удалась: {d.get('error') or 'причина не записана'}", "cancelled": "Проверка отменена."}
                   .get(d["state"], f"Проверка ещё идёт: {d['state']}, готово {d.get('done', 0)} из {d.get('total', 0)}."))
    elif not d.get("final"):
        out.append("Проверка закончена, но итоговая таблица не записана — результат неполный.")
    if s:
        out.append(f"Снимков {s.get('images', 0)}, исследований {s.get('studies', 0)}: годных {s.get('good', 0)}, с нарушением {s.get('bad', 0)}, "
                   f"не оценено {s.get('not_evaluated', 0)}, не обработано {s.get('failures', 0)}")
        if s.get("duplicates"):
            out.append(f"Одинаковых файлов пропущено: {s['duplicates']}")
    for n, im in enumerate(d.get("images") or [], 1):
        out += ["", f"{n}. {im['file']}", f"   область:   {im['region_ru']}", f"   вердикт:   {_verdict(im)}"]
        for v in im["violations"]:
            out.append(f"   нарушение: {v['text']}")
        if im.get("error"):
            out.append(f"   ошибка:    {im['error']}")
        for k, e in enumerate(im["explanations"]):
            out.append(("   пояснение: " if k == 0 else "              ") + e)
        if im["measurements"]:
            out.append("   измерения: " + "; ".join(f"{k} — {v}" for k, v in im["measurements"].items()))
        if im.get("overlay"):
            out.append(f"   разметка:  {im['overlay']}")
    files = d.get("files") or {}
    if files:
        out += ["", "Файлы проверки:"] + [f"   {p}" for p in files.values()]
    out += ["", NOTE]
    return "\n".join(out)


def _copy_out(d: dict, folder: str):
    """Таблицы и картинки разметки — в папку пользователя; пути в описании ведут уже туда."""
    folder = folder.strip('"')
    os.makedirs(folder, exist_ok=True)

    def take(path):
        target = os.path.join(folder, os.path.basename(path))
        shutil.copy2(path, target)
        return os.path.abspath(target)
    d["files"] = {k: take(p) for k, p in (d.get("files") or {}).items() if os.path.isfile(p)}
    for im in d.get("images") or []:
        for k in ("overlay", "original"):
            if im.get(k) and os.path.isfile(im[k]):
                im[k] = take(im[k])
    d["folder"] = os.path.abspath(folder)


def _code(d: dict) -> int:
    s = d.get("summary") or {}
    if d["state"] != "done" or not d.get("final") or s.get("failures"):
        return FAILED
    return BAD if s.get("bad") else OK


def _show(d: dict, a) -> int:
    saved = True
    if a.out and d["state"] == "done":
        try:
            _copy_out(d, a.out)
        except OSError as e:                         # папка — это файл, нет прав, диск полон: описание всё равно отдаём
            _say(f"Не удалось сложить файлы в {a.out}: {e.strerror or e}. Они остались в папке проверки.")
            saved = False
    print(json.dumps(d, ensure_ascii=False, indent=2) if a.json else render(d))
    return _code(d) if saved else FAILED


def _describe(base: str, run_id: str, patience: float = 6.0) -> dict | None:
    """Описание проверки. Движок как раз переписывает файл состояния или только создаёт проверку — отказ не сразу:
    повторяем запрос, пока не истечёт терпение. «Готово», но итогов ещё нет — тоже ждём: их дописывают следом."""
    t0, d = time.time(), None
    while True:
        code, r = _call(f"{base}/api/desktop/describe/{urllib.parse.quote(run_id)}")
        if code == 200 and not (r.get("state") == "done" and not r.get("final")):
            return r
        d = r if code == 200 else d
        if time.time() - t0 > patience:
            return d                                 # итогов так и нет — отдаём что есть; движок молчит — None
        time.sleep(0.3)


def check(a, M) -> int:
    paths = [os.path.abspath(p.strip('"')) for p in a.files if p.strip('"')]      # "D:\папка\" Windows отдаёт с кавычкой на конце
    missing = [p for p in paths if not os.path.exists(p)]
    if not paths or missing:
        _say("Не найдено: " + ", ".join(missing) if missing else "Что проверить? Пример: kostik --check D:\\снимки\\исследование")
        return USAGE
    with engine(M) as (base, window):
        if a.open and not window:
            _say("Окно программы не открыто — --open пропущен; описание ниже.")
        code, r = _call(base + "/desktop/run-local", {"paths": paths, "navigate": bool(a.open and window), "started_by": "консоль"})
        if code != 200 or not r.get("run_id"):
            _say(f"Движок не принял проверку: {r.get('detail') or 'нет ответа'}")
            return FAILED
        run_id, t0, seen = r["run_id"], time.time(), None
        while True:
            d = _describe(base, run_id)
            if d is None:
                _say("Открыто окно Kostik прежней версии — оно не умеет отдавать описание. Закройте окно и повторите команду."
                     if window and _call(base + "/api/health")[0] == 200 else "Движок перестал отвечать; подробности: kostik --verbose")
                return FAILED
            if d["state"] in ("done", "error", "cancelled"):
                return _show(d, a)
            if time.time() - t0 > a.timeout:
                _say(f"За {a.timeout} с проверка не закончилась. Она продолжается в открытом окне; результат: kostik --results {run_id}"
                     if window else f"За {a.timeout} с проверка не закончилась и остановлена вместе с движком.")
                return FAILED
            if not a.json and (d.get("done"), d.get("total")) != seen and d.get("total"):
                seen = (d.get("done"), d.get("total"))
                _say(f"проверено {seen[0]} из {seen[1]}")
            time.sleep(0.4)


def results(a, M) -> int:
    with engine(M) as (base, _):
        d = _describe(base, a.results)
    if d is None:
        _say("Проверок ещё нет." if a.results == "last" else f"Проверка {a.results} не найдена; список: kostik --runs")
        return USAGE
    return _show(d, a)


def runs(a, M) -> int:
    with engine(M) as (base, _):
        code, r = _call(base + "/api/desktop/runs")
    if code != 200:
        _say("Движок не ответил; подробности: kostik --verbose")
        return FAILED
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        for x in r["runs"]:
            s = x.get("summary") or {}
            tally = f"снимков {s.get('images', 0)}: годных {s.get('good', 0)}, с нарушением {s.get('bad', 0)}" if s else x["state"]
            print(f"{x['run_id']}  {x['created']}  {tally}  {x.get('title') or ''}")
        if not r["runs"]:
            print("Проверок ещё нет.")
    return OK


def main(a, M) -> int:
    try:
        return check(a, M) if a.check else results(a, M) if a.results else runs(a, M)
    except RuntimeError as e:
        _say(str(e))
        return FAILED
