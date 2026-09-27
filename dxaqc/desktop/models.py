# -*- coding: utf-8 -*-
"""Менеджер моделей: то, что не входит в установщик, скачивается с сайта по запросу пользователя (#146).

Каталог — manifest.json на сайте: для модели — название, зачем нужна, версия и файлы с размером и SHA-256.
Загрузка в фоне с докачкой (Range), файл принимается только при совпадении суммы. Без интернета модель можно
импортировать из файла — например, скачанного на другом компьютере и перенесённого на флешке.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request

from dxaqc.desktop import SITE, paths

MANIFEST_URL = os.environ.get("DXAQC_MODELS_URL", SITE + "/downloads/models/manifest.json")
TIMEOUT = 20
CHUNK = 1 << 16

_lock = threading.Lock()
_state: dict[str, dict] = {}          # key -> status, done, total, error, file
_manifest: dict = {}


def fetch_manifest(force: bool = False) -> dict:
    """Каталог моделей с сайта; при ошибке сети — последняя сохранённая копия и текст ошибки."""
    global _manifest
    cache = os.path.join(paths.models_dir(), "manifest.json")
    if _manifest and not force:
        return _manifest
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        data["offline"] = False
    except (OSError, ValueError, urllib.error.URLError) as exc:
        try:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {"models": []}
        data["offline"] = True
        data["error"] = f"каталог моделей {MANIFEST_URL} недоступен ({type(exc).__name__}) — показан сохранённый каталог; модель можно импортировать из файла"
    _manifest = data
    return data


def _model(key: str) -> dict | None:
    return next((m for m in fetch_manifest().get("models", []) if m.get("key") == key), None)


def target(m: dict, f: dict) -> str:
    return os.path.join(paths.models_dir(), m.get("dir") or m["key"], f["name"])


def installed(m: dict) -> bool:
    return all(os.path.isfile(target(m, f)) for f in m.get("files", []))


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def listing() -> dict:
    man = fetch_manifest()
    items = []
    for m in man.get("models", []):
        size = sum(int(f.get("size") or 0) for f in m.get("files", []))
        st = dict(_state.get(m["key"], {}))
        items.append(dict(key=m["key"], title=m.get("title", m["key"]), purpose=m.get("purpose", ""), version=m.get("version", ""),
                          size=size, installed=installed(m), state=st.get("status", "idle"), done=st.get("done", 0),
                          total=st.get("total", size), error=st.get("error", ""),
                          files=[f["name"] for f in m.get("files", [])]))
    return dict(models=items, offline=man.get("offline", False), error=man.get("error", ""), source=MANIFEST_URL)


def _download_file(key: str, url: str, dest: str, size: int, digest: str, done_before: int):
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    have = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if have and r.status != 206:          # сервер не умеет докачку — начинаем заново
            have = 0
        with open(part, "ab" if have else "wb") as out:
            while True:
                if _state[key].get("cancel"):
                    raise InterruptedError("загрузка остановлена — можно продолжить с того же места")
                block = r.read(CHUNK)
                if not block:
                    break
                out.write(block)
                have += len(block)
                _state[key]["done"] = done_before + have
    if size and os.path.getsize(part) != size:
        raise IOError(f"{os.path.basename(dest)}: получено {os.path.getsize(part)} байт из {size} — повторите загрузку, она продолжится")
    if digest and sha256(part) != digest.lower():
        os.remove(part)
        raise IOError(f"{os.path.basename(dest)}: контрольная сумма не совпала — файл повреждён и удалён, повторите загрузку")
    os.replace(part, dest)


def _worker(key: str):
    m = _model(key)
    try:
        if not m:
            raise LookupError("модели нет в каталоге")
        done = 0
        for f in m.get("files", []):
            dest = target(m, f)
            if os.path.isfile(dest) and (not f.get("sha256") or sha256(dest) == f["sha256"].lower()):
                done += int(f.get("size") or 0)
                continue
            _state[key]["file"] = f["name"]
            _download_file(key, f["url"], dest, int(f.get("size") or 0), f.get("sha256", ""), done)
            done += int(f.get("size") or 0)
        _state[key].update(status="done", done=done, error="")
    except InterruptedError as exc:
        _state[key].update(status="paused", error=str(exc))
    except (OSError, urllib.error.URLError, LookupError) as exc:
        msg = str(exc) if isinstance(exc, (IOError, LookupError)) and not isinstance(exc, urllib.error.URLError) else \
            f"нет связи с сайтом {SITE} ({type(exc).__name__}) — проверьте интернет или импортируйте файл модели"
        _state[key].update(status="error", error=msg)


def start(key: str) -> dict:
    m = _model(key)
    if not m:
        raise LookupError("модели нет в каталоге")
    with _lock:
        st = _state.get(key)
        if st and st.get("status") == "downloading":
            return st
        _state[key] = dict(status="downloading", done=0, total=sum(int(f.get("size") or 0) for f in m.get("files", [])), error="")
    threading.Thread(target=_worker, args=(key,), daemon=True, name=f"model-{key}").start()
    return _state[key]


def pause(key: str):
    if key in _state:
        _state[key]["cancel"] = True


def delete(key: str):
    m = _model(key)
    if not m:
        raise LookupError("модели нет в каталоге")
    for f in m.get("files", []):
        for p in (target(m, f), target(m, f) + ".part"):
            if os.path.exists(p):
                os.remove(p)
    _state.pop(key, None)


def import_file(key: str, name: str, src_path: str) -> str:
    """Импорт файла модели без интернета: имя должно быть из каталога, сумма — совпадать."""
    m = _model(key)
    if not m:
        raise LookupError("модели нет в каталоге — откройте страницу моделей, когда будет интернет, или обновите приложение")
    f = next((x for x in m.get("files", []) if x["name"] == os.path.basename(name)), None)
    if not f:
        raise ValueError(f"файл {os.path.basename(name)} не из этой модели; нужны: " + ", ".join(x["name"] for x in m["files"]))
    if f.get("sha256") and sha256(src_path) != f["sha256"].lower():
        raise ValueError(f"{f['name']}: контрольная сумма не совпала — файл повреждён или от другой версии")
    dest = target(m, f)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src_path, dest + ".part")
    os.replace(dest + ".part", dest)
    return dest
