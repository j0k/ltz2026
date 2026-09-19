# -*- coding: utf-8 -*-
"""Статистика данных задачи для страницы /tz/data.html: состав наборов, разметка экспертов, технические параметры.

Считается по тем же файлам, что видит сервис (/datasets, только чтение), и тем же кодом определения области, что в
пайплайне. Наружу — только агрегаты: персональные теги DICOM в выдачу не попадают, идентификаторы исследований не
показываются. Результат кешируется на диск с подписью набора (число файлов и время их изменения) и пересчитывается,
только когда данные поменялись; при старте сервиса кеш прогревается в фоне.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import threading
import time
from collections import Counter, defaultdict

from dxaqc import datasets

VERSION = 1
_lock = threading.Lock()
_mem: dict = {}

REGION_RU = {"lumbar_spine": "поясничный отдел", "hip_left": "левое бедро", "hip_right": "правое бедро", "unknown": "не определена"}
CRITERIA = [
    ("Позвоночник", "sp_pos", "охват"), ("Позвоночник", "sp_axis", "наклон оси"),
    ("Позвоночник", "sp_art", "посторонние предметы"), ("Позвоночник", "sp_bad", "итог"),
    ("Правое бедро", "rh_pos", "укладка"), ("Правое бедро", "rh_roi", "зона интереса"), ("Правое бедро", "rh_bad", "итог"),
    ("Левое бедро", "lh_pos", "укладка"), ("Левое бедро", "lh_roi", "зона интереса"), ("Левое бедро", "lh_bad", "итог"),
]
SPINE_PARTS = {"sp_pos": "охват", "sp_axis": "ось", "sp_art": "посторонние предметы"}
HIP_PARTS = {"pos": "укладка", "roi": "зона интереса"}


def _dir(ds_id: str) -> str:
    return os.path.join(datasets.ROOT, datasets.REGISTRY[ds_id]["path"])


def _labels_path() -> str:
    return os.path.join(datasets.ROOT, datasets.REGISTRY["train"]["labels"])


def _dicoms(root: str) -> list[str]:
    out = []
    for base, _dirs, files in os.walk(root, followlinks=True):
        out += [os.path.join(base, f) for f in files if f.lower().endswith(".dcm")]
    return sorted(out)


def _signature(files: list[str]) -> str:
    stamp = 0
    for f in files:
        try:
            stamp += int(os.stat(f).st_mtime)
        except OSError:
            pass
    try:
        lab = os.stat(_labels_path())
        stamp += int(lab.st_mtime) + lab.st_size
    except OSError:
        pass
    return f"v{VERSION}:{len(files)}:{stamp}"


def _cache_path() -> str:
    return os.path.join(os.environ.get("DXAQC_DATA", "/data"), "cache", f"datastats_v{VERSION}.json")


def _region(path: str, root: str) -> str:
    """Область тем же кодом, что в пайплайне: загрузка io.load_image и analyze.detect_region."""
    from dxaqc import analyze
    from dxaqc.io import load_image
    img = load_image(path, root)
    if not hasattr(img, "pixels"):
        return "unknown"
    return analyze.detect_region(img.pixels)[0]


def _scan_train(files: list[str], root: str) -> dict:
    import pydicom
    tags = defaultdict(Counter)
    heights = defaultdict(list)
    copies: Counter = Counter()
    first: dict = {}
    study_unique: dict = defaultdict(set)
    no_scale = no_part = 0
    for f in files:
        ds = pydicom.dcmread(f, force=True)
        study = os.path.relpath(f, root).split(os.sep)[0]
        for key, tag in (("modality", "Modality"), ("manufacturer", "Manufacturer"), ("model", "ManufacturerModelName"),
                         ("bits", "BitsStored"), ("photometric", "PhotometricInterpretation"), ("series", "SeriesDescription")):
            tags[key][str(ds.get(tag, "") or "—")] += 1
        width, height = int(ds.get("Columns", 0) or 0), int(ds.get("Rows", 0) or 0)
        tags["width"][width] += 1
        heights[width].append(height)
        no_scale += int(not (ds.get("PixelSpacing") or ds.get("ImagerPixelSpacing")))
        no_part += int(not str(ds.get("BodyPartExamined", "") or "").strip())
        digest = hashlib.sha1(ds.PixelData).hexdigest() if "PixelData" in ds else f
        copies[digest] += 1
        first.setdefault(digest, f)
        study_unique[study].add(digest)
    regions = Counter(_region(path, root) for path in first.values())
    return dict(
        studies=len(study_unique), files=len(files), unique=len(copies), extra=len(files) - len(copies),
        copies=sorted(Counter(copies.values()).items()),
        per_study=sorted(Counter(len(s) for s in study_unique.values()).items()),
        regions=[dict(key=k, ru=REGION_RU.get(k, k), n=n) for k, n in regions.most_common()],
        tech=dict(
            modality=tags["modality"].most_common(), manufacturer=tags["manufacturer"].most_common(),
            model=tags["model"].most_common(), bits=tags["bits"].most_common(),
            photometric=tags["photometric"].most_common(), series=tags["series"].most_common(),
            widths=[dict(width=w, n=n, h_min=min(heights[w]), h_med=round(statistics.median(heights[w])), h_max=max(heights[w]))
                    for w, n in tags["width"].most_common()],
            no_scale=no_scale, no_part=no_part))


def _scan_test(files: list[str], root: str) -> dict:
    import pydicom
    images = []
    for f in files:
        ds = pydicom.dcmread(f, force=True, stop_before_pixels=True)
        region = _region(f, root)
        images.append(dict(name=os.path.basename(f), width=int(ds.get("Columns", 0) or 0), height=int(ds.get("Rows", 0) or 0),
                           region=region, ru=REGION_RU.get(region, region)))
    return dict(files=len(files), images=images)


def _flag(v: str):
    v = (v or "").strip()
    return None if not v else v.startswith("1")


def _scan_labels() -> dict | None:
    try:
        with open(_labels_path(), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None
    criteria = []
    for group, key, title in CRITERIA:
        vals = [_flag(r.get(key, "")) for r in rows]
        bad, ok = vals.count(True), vals.count(False)
        labeled = bad + ok
        criteria.append(dict(group=group, key=key, title=title, bad=bad, ok=ok, na=len(rows) - labeled, labeled=labeled,
                             share=round(bad / labeled * 100) if labeled else 0, total=len(rows)))
    spine = Counter()
    for r in rows:
        if _flag(r.get("sp_bad", "")):
            parts = [name for k, name in SPINE_PARTS.items() if _flag(r.get(k, ""))]
            spine[" + ".join(parts) if parts else "без отметки подкритерия"] += 1
    hips = Counter()
    for side, ru in (("rh", "правое"), ("lh", "левое")):
        for r in rows:
            if _flag(r.get(f"{side}_bad", "")):
                parts = [name for k, name in HIP_PARTS.items() if _flag(r.get(f"{side}_{k}", ""))]
                hips[" + ".join(parts) if parts else "без отметки подкритерия"] += 1
    comments = Counter(c.strip().lower() for c in (r.get("comment", "") for r in rows) if c and c.strip())
    return dict(studies=len(rows), criteria=criteria, spine_combos=spine.most_common(), hip_combos=hips.most_common(),
                comments=comments.most_common(6), commented=sum(comments.values()))


def compute() -> dict:
    t0 = time.time()
    train_root, test_root = _dir("train"), _dir("test")
    train_files, test_files = _dicoms(train_root), _dicoms(test_root)
    if not train_files:
        return dict(ok=False, error="обучающий набор не подключён")
    return dict(ok=True, signature=_signature(train_files + test_files), train=_scan_train(train_files, train_root),
                test=_scan_test(test_files, test_root), labels=_scan_labels(), seconds=round(time.time() - t0, 1))


def get(force: bool = False) -> dict:
    """Статистика из памяти, с диска (если данные не менялись) или посчитанная заново."""
    with _lock:
        files = _dicoms(_dir("train")) + _dicoms(_dir("test"))
        sig = _signature(files)
        if not force and _mem.get("signature") == sig:
            return _mem
        path = _cache_path()
        if not force:
            try:
                with open(path, encoding="utf-8") as fh:
                    cached = json.load(fh)
                if cached.get("signature") == sig:
                    _mem.clear(); _mem.update(cached)
                    return _mem
            except (OSError, ValueError):
                pass
        data = compute()
        if data.get("ok"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(path + ".tmp", path)
        _mem.clear(); _mem.update(data)
        return _mem


def warm():
    """Прогреть кеш в фоне, чтобы первый посетитель страницы не ждал разбора 500 файлов."""
    threading.Thread(target=lambda: _safe_get(), name="datastats-warm", daemon=True).start()


def _safe_get():
    try:
        get()
    except Exception as exc:  # noqa: BLE001 — страница посчитает сама при заходе
        print(f"[datastats] прогрев не удался: {type(exc).__name__}: {exc}", flush=True)
