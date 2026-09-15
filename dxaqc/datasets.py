# -*- coding: utf-8 -*-
"""Наборы данных организатора, доступные на стенде без загрузки.

Каталоги монтируются в контейнер только на чтение (DXAQC_DATASETS). Выбранные исследования
подключаются в папку прогона символическими ссылками, файлы не копируются.
"""
from __future__ import annotations

import csv
import os
import random

ROOT = os.environ.get("DXAQC_DATASETS", "/datasets")

REGISTRY = {
    "test": dict(title="Фрагмент «Для теста»",
                 desc="Три снимка из архива для отладки: поясничный отдел, правое и левое бедро. Экспертной разметки нет.",
                 path="test", labels=None, per_study=False),
    "train": dict(title="Обучающий набор организатора",
                  desc="100 исследований с экспертной оценкой качества. Вердикты сервиса сравниваются с разметкой.",
                  path="train", labels="train_labels.csv", per_study=True),
}

LABEL_FIELDS = ("sp_pos", "sp_axis", "sp_art", "rh_pos", "rh_roi", "lh_pos", "lh_roi", "sp_bad", "rh_bad", "lh_bad")


def _dir(ds_id):
    return os.path.join(ROOT, REGISTRY[ds_id]["path"])


def studies(ds_id: str) -> list[str]:
    d = _dir(ds_id)
    if not os.path.isdir(d):
        return []
    if not REGISTRY[ds_id]["per_study"]:
        return ["all"]
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)) and not x.startswith("."))


def available() -> list[dict]:
    out = []
    for ds_id, meta in REGISTRY.items():
        st = studies(ds_id)
        if not st:
            continue
        out.append(dict(id=ds_id, title=meta["title"], desc=meta["desc"], per_study=meta["per_study"],
                        n_studies=len(st) if meta["per_study"] else 1, has_labels=bool(meta["labels"]),
                        studies=st if meta["per_study"] else []))
    return out


def link_selection(ds_id: str, mode: str, dest: str, n: int = 10, study: str = "", seed: int | None = None) -> list[str]:
    """Подключить в dest выбранные исследования. mode: all | sample | study."""
    if ds_id not in REGISTRY:
        raise ValueError("неизвестный набор данных")
    src = _dir(ds_id)
    os.makedirs(dest, exist_ok=True)
    if not REGISTRY[ds_id]["per_study"]:
        for f in sorted(os.listdir(src)):
            os.symlink(os.path.join(src, f), os.path.join(dest, f))
        return ["all"]
    all_st = studies(ds_id)
    if mode == "study":
        if study not in all_st:
            raise ValueError("такого исследования в наборе нет")
        chosen = [study]
    elif mode == "sample":
        n = max(1, min(int(n), len(all_st)))
        chosen = sorted(random.Random(seed).sample(all_st, n))
    else:
        chosen = all_st
    for s in chosen:
        os.symlink(os.path.join(src, s), os.path.join(dest, s))
    return chosen


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def load_labels(ds_id: str) -> dict | None:
    meta = REGISTRY.get(ds_id)
    if not meta or not meta["labels"]:
        return None
    p = os.path.join(ROOT, meta["labels"])
    if not os.path.exists(p):
        return None
    out = {}
    with open(p, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["study"]] = {k: _num(row.get(k)) for k in LABEL_FIELDS} | {"comment": (row.get("comment") or "").strip()}
    return out


def expert_for(labels: dict | None, study_key: str, region: str) -> dict | None:
    """Экспертная оценка для снимка: bad и типы нарушений в кодах сервиса."""
    if not labels or study_key not in labels:
        return None
    L = labels[study_key]
    if region == "lumbar_spine" and L["sp_bad"] is not None:
        types = [c for c, k in (("coverage", "sp_pos"), ("axis_tilt", "sp_axis"), ("artifact", "sp_art")) if L[k] == 1]
        return dict(bad=L["sp_bad"], types=types, comment=L["comment"])
    for side, pre in (("hip_right", "rh"), ("hip_left", "lh")):
        if region == side and L[f"{pre}_bad"] is not None:
            types = [c for c, k in (("hip_positioning", f"{pre}_pos"), ("hip_roi", f"{pre}_roi")) if L[k] == 1]
            return dict(bad=L[f"{pre}_bad"], types=types, comment=L["comment"])
    return None
