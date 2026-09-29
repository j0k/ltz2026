# -*- coding: utf-8 -*-
"""Параметры анализа позвоночника: значения по умолчанию, границы и подписи для пульта.

Значения по умолчанию — те, с которыми откалибрована версия 0.1. Пульт позволяет запустить анализ с другими
порогами; параметры прогона сохраняются в его manifest.json.
"""
from __future__ import annotations

SPEC = [
    dict(name="axis_limit_deg", label="Допуск наклона оси", unit="°", default=5.0, min=1.0, max=15.0, step=0.5, kind=float,
         recompute=True, metric="axis_tilt",
         help="Угол между центрами столба в верхней и нижней трети больше допуска — нарушение «наклон оси». По ТЗ 5°."),
    dict(name="iliac_min_brightness", label="Яркость подвздошных костей в нижних углах", unit="", default=4.0, min=0.0, max=60.0,
         step=0.5, kind=float, recompute=True, metric="coverage",
         help="Средняя яркость нижнего угла кадра ниже порога — подвздошная кость не попала в кадр, нарушение охвата."),
    dict(name="artifact_contrast", label="Контраст постороннего предмета", unit="", default=55, min=20, max=150, step=1, kind=int,
         recompute=True, metric="artifact",
         help="Насколько пятно вне столба ярче своего окружения (из 255). Выше порога — нарушение «посторонний предмет». "
              "Порог подобран честной кросс-валидацией на обучающем наборе, 26.09."),
    dict(name="spine_band_half", label="Полуширина полосы столба", unit="px", default=45, min=20, max=100, step=1, kind=int,
         recompute=False, metric="artifact",
         help="Всё ближе к оси считается самим позвоночником, посторонние предметы ищутся дальше. Эффект виден только после перезапуска анализа."),
]
BY_NAME = {s["name"]: s for s in SPEC}
DEFAULTS = {s["name"]: s["default"] for s in SPEC}
SHORT = {"axis_limit_deg": "ось", "iliac_min_brightness": "подвздошные", "artifact_contrast": "контраст предмета",
         "spine_band_half": "полоса столба"}


class ParamError(ValueError):
    """Неверное значение параметра; текст можно показать пользователю."""


_LEARNED = {"mtime": None, "values": {}}


def learned() -> dict:
    """Пороги, установленные плагином дообучения spine_thresholds (dxaqc/learning), с кешем по времени файла."""
    import json
    import os
    home = os.path.join(os.environ.get("DXAQC_DATA", "/data"), "learning", "spine_thresholds", "active.json")
    try:
        mt = os.path.getmtime(home)
    except OSError:
        _LEARNED.update(mtime=None, values={})
        return {}
    if mt != _LEARNED["mtime"]:
        try:
            with open(home, encoding="utf-8") as f:
                info = json.load(f)
            with open(info["path"], encoding="utf-8") as f:
                vals = {k: v for k, v in json.load(f).items() if k in BY_NAME}
        except (OSError, ValueError, KeyError):
            vals = {}
        _LEARNED.update(mtime=mt, values=vals)
    return dict(_LEARNED["values"])


def normalize(values: dict | None) -> dict:
    """Полный набор параметров: значения по умолчанию (с порогами дообучения, если установлены), поверх — переданные,
    с проверкой типа и диапазона."""
    out = dict(DEFAULTS) | learned()
    for s in SPEC:
        raw = (values or {}).get(s["name"])
        if raw is None or raw == "":
            continue
        try:
            v = float(str(raw).replace(",", "."))
        except (TypeError, ValueError):
            raise ParamError(f"{s['label']}: нужно число") from None
        if s["kind"] is int:
            if v != int(v):
                raise ParamError(f"{s['label']}: нужно целое число")
            v = int(v)
        if not s["min"] <= v <= s["max"]:
            raise ParamError(f"{s['label']}: от {s['min']:g} до {s['max']:g}")
        out[s["name"]] = v
    return out


def changed(p: dict | None) -> dict:
    p = normalize(p)
    return {k: v for k, v in p.items() if v != DEFAULTS[k]}


def describe(p: dict | None) -> str:
    """Короткая подпись для списков: «ось 4°, подвздошные 6» или «по умолчанию»."""
    ch = changed(p)
    if not ch:
        return "по умолчанию"
    return ", ".join(f"{SHORT[k]} {v:g}{BY_NAME[k]['unit'] if BY_NAME[k]['unit'] in ('°', 'px') else ''}" for k, v in ch.items())
