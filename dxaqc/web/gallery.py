# -*- coding: utf-8 -*-
"""Галерея снимков наборов организатора: индекс, картинки и наш анализ по запросу.

Снимки собираются тем же io.collect, что в пайплайне, поэтому ключ кадра совпадает с ключом карточки в прогонах
и дубли схлопнуты так же. В индекс для страницы не попадают пути и идентификаторы исследований: исследования
пронумерованы 1…N. Заключение экспертов берётся из разметки обучающего набора по области снимка; комментарий
эксперта относится ко всему исследованию. Анализ по кнопке — текущей версией кода, результат и атлас кешируются
по версии; одновременно идёт не больше одного анализа, чтобы галерея не отнимала процессор у прогонов.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time

from dxaqc import __version__, analyze, datasets, pipeline, render
from dxaqc import io as dio

INDEX_VERSION = 1
DS_TITLES = {"test": "Фрагмент «Для теста»", "train": "Обучающий набор"}
REGION_RU = {"lumbar_spine": "поясничный отдел", "hip_right": "правое бедро", "hip_left": "левое бедро", "unknown": "не определена"}
VIOL_RU = {"coverage": "неполный охват", "axis_tilt": "наклон оси", "artifact": "посторонние предметы",
           "hip_positioning": "укладка и ротация бедра", "hip_roi": "поля вокруг зоны интереса",
           "hip_not_evaluated_v0": "бедро в этой версии не оценивается"}
LABELS = {"lumbar_spine": ("sp_bad", {"sp_pos": "coverage", "sp_axis": "axis_tilt", "sp_art": "artifact"}),
          "hip_right": ("rh_bad", {"rh_pos": "hip_positioning", "rh_roi": "hip_roi"}),
          "hip_left": ("lh_bad", {"lh_pos": "hip_positioning", "lh_roi": "hip_roi"})}
REGION_ORDER = {"lumbar_spine": 0, "hip_right": 1, "hip_left": 2}
_lock = threading.Lock()
_run_lock = threading.Semaphore(1)
_index: dict = {}


def _data_dir(*parts) -> str:
    path = os.path.join(os.environ.get("DXAQC_DATA", "/data"), "gallery", *parts)
    os.makedirs(os.path.dirname(path) if os.path.splitext(path)[1] else path, exist_ok=True)
    return path


def _folder(ds: str) -> str:
    return os.path.join(datasets.ROOT, datasets.REGISTRY[ds]["path"])


def _flag(v):
    v = (v or "").strip()
    return None if not v else v.startswith("1")


def _labels() -> dict:
    try:
        with open(os.path.join(datasets.ROOT, datasets.REGISTRY["train"]["labels"]), encoding="utf-8") as fh:
            return {r["study"]: r for r in csv.DictReader(fh)}
    except OSError:
        return {}


def expert_for(row: dict | None, region: str) -> dict:
    """Заключение экспертов для снимка: итог по области, типы нарушений и комментарий к исследованию."""
    comment = ((row or {}).get("comment") or "").strip()
    if not row or region not in LABELS:
        return dict(labeled=False, comment=comment)
    bad_key, parts = LABELS[region]
    bad = _flag(row.get(bad_key))
    if bad is None:
        return dict(labeled=False, comment=comment)
    types = [code for key, code in parts.items() if _flag(row.get(key))]
    return dict(labeled=True, bad=bad, types=types, types_ru=[VIOL_RU[t] for t in types], comment=comment)


def _signature() -> str:
    from dxaqc.web import datastats as DS
    return f"g{INDEX_VERSION}:" + DS._signature(DS._dicoms(_folder("train")) + DS._dicoms(_folder("test")))


def _scan() -> dict:
    labels = _labels()
    items, paths = [], {}
    for ds in ("test", "train"):
        root = _folder(ds)
        if not os.path.isdir(root):
            continue
        images, _failures, _dups = dio.collect(root)
        for img in images:
            key = img.sha[:12]
            if key in paths:
                continue
            region = analyze.detect_region(img.pixels)[0]
            study = img.rel_path.split(os.sep)[0] if ds == "train" and os.sep in img.rel_path else ""
            items.append(dict(key=key, ds=ds, ds_title=DS_TITLES[ds], study=study, region=region,
                              region_ru=REGION_RU.get(region, region), w=int(img.pixels.shape[1]), h=int(img.pixels.shape[0]),
                              expert=expert_for(labels.get(study), region) if ds == "train" else dict(labeled=False, comment="")))
            paths[key] = [ds, img.path]
    numbers = {s: n for n, s in enumerate(sorted({i["study"] for i in items if i["study"]}), 1)}
    for it in items:                      # идентификаторы исследований наружу не отдаём
        it["study_no"] = numbers.get(it.pop("study"))
    items.sort(key=lambda i: (i["ds"] != "test", i["study_no"] or 0, REGION_ORDER.get(i["region"], 9)))
    return dict(items=items, paths=paths)


def index(force: bool = False) -> dict:
    """Все снимки галереи; пересчёт, только если поменялись файлы наборов."""
    with _lock:
        sig = _signature()
        if not force and _index.get("signature") == sig:
            return _index
        path = _data_dir(f"index_v{INDEX_VERSION}.json")
        if not force:
            try:
                with open(path, encoding="utf-8") as fh:
                    cached = json.load(fh)
                if cached.get("signature") == sig:
                    _index.clear(); _index.update(cached)
                    return _index
            except (OSError, ValueError):
                pass
        data = dict(_scan(), signature=sig)
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        _index.clear(); _index.update(data)
        return _index


def warm():
    def run():
        try:
            index()
        except Exception as exc:  # noqa: BLE001 — страница соберёт индекс сама
            print(f"[gallery] прогрев не удался: {type(exc).__name__}: {exc}", flush=True)
    threading.Thread(target=run, name="gallery-warm", daemon=True).start()


def public_items() -> list[dict]:
    return index()["items"]


def item(key: str) -> dict | None:
    return next((i for i in index()["items"] if i["key"] == key), None)


def _pixels(key: str):
    ds, path = index()["paths"][key]
    img = dio.load_image(path, _folder(ds))
    if not hasattr(img, "pixels"):
        raise ValueError("снимок не читается")
    return img.pixels


def image_path(key: str, kind: str) -> str:
    """Исходный снимок (png) или миниатюра (jpg) — рисуются один раз и лежат на диске."""
    path = _data_dir("thumb" if kind == "thumb" else "img", f"{key}.{'jpg' if kind == 'thumb' else 'png'}")
    if not os.path.isfile(path):
        im = render.original(_pixels(key))
        if kind == "thumb":
            im.thumbnail((280, 280))
            im.save(path + ".tmp", "JPEG", quality=85)
        else:
            im.save(path + ".tmp", "PNG", optimize=True)
        os.replace(path + ".tmp", path)
    return path


def atlas_path(key: str) -> str:
    return _data_dir(f"v{__version__}", f"{key}_atlas.png")


def agreement(expert: dict, result: dict) -> dict:
    """Совпадает ли наш вердикт с экспертами — по итогу и по типам нарушений."""
    if not expert.get("labeled"):
        return dict(kind="none", text="У снимка нет экспертной разметки — сравнивать не с чем.")
    if result["quality_class"] is None:
        verdict = "нарушение" if expert["bad"] else "норма"
        return dict(kind="na", text=f"Сервис эту область пока не оценивает. У экспертов — {verdict}.")
    ours = {v for v in result["violation_codes"] if v != "hip_not_evaluated_v0"}
    theirs = set(expert["types"])
    missing = [VIOL_RU[c] for c in sorted(theirs - ours)]
    extra = [VIOL_RU.get(c, c) for c in sorted(ours - theirs)]
    same = (result["quality_class"] == 1) == bool(expert["bad"])
    if same and not missing and not extra:
        return dict(kind="match", text="Совпадает с экспертами.", missing=[], extra=[])
    parts = []
    if missing:
        parts.append("пропущено: " + ", ".join(missing))
    if extra:
        parts.append("лишнее: " + ", ".join(extra))
    head = "Итог совпадает, но есть расхождения" if same else "Расходится с экспертами"
    return dict(kind="partial" if same else "mismatch", text=head + (": " + "; ".join(parts) if parts else "") + ".",
                missing=missing, extra=extra)


def run_analysis(key: str) -> dict:
    """Наш анализ снимка текущей версией; результат и атлас кешируются по версии сервиса."""
    it = item(key)
    if not it:
        raise KeyError(key)
    cache = _data_dir(f"v{__version__}", f"{key}.json")
    if os.path.isfile(cache):
        with open(cache, encoding="utf-8") as fh:
            result = json.load(fh)
        result["cached"] = True
        return result
    with _run_lock:
        pixels = _pixels(key)
        t0 = time.perf_counter()
        res, art = pipeline.analyze_image(pixels)
        seconds = time.perf_counter() - t0
        atlas = art["atlas"] if art else render.overlay(pixels, res)
        atlas.save(atlas_path(key) + ".tmp", "PNG", optimize=True)
        os.replace(atlas_path(key) + ".tmp", atlas_path(key))
    result = dict(region=res["region"], region_ru=REGION_RU.get(res["region"], res["region"]), quality_class=res["quality_class"],
                  violation_codes=list(res["violations"]), violations=[VIOL_RU.get(v, v) for v in res["violations"]],
                  explanations=list(res.get("explanations") or [])[:6], seconds=round(seconds, 2), version=__version__,
                  atlas=f"/gallery/atlas/{key}.png?v={__version__}")
    result["agreement"] = agreement(it["expert"], result)
    with open(cache + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
    os.replace(cache + ".tmp", cache)
    result["cached"] = False
    return result
