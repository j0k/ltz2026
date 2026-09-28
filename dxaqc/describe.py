# -*- coding: utf-8 -*-
"""Что на отклонённой картинке: описание вместо тупика «это не DICOM» (не вердикт качества).

Признаки простые и проверяемые: цветность (рентген — оттенки серого), тёмный фон, зеркальная симметрия,
яркий столб по центру (позвоночник), кости у нижних краёв (диафизы бёдер). По ним — догадка об области
и объяснение, чем картинка отличается от снимка денситометрии и что с ней можно сделать.

28.09 (Юрий): вид сбоку — по зеркальности окна вокруг столба позвонков (в прямой проекции левая и правая половины
позвонка похожи: на 99 снимках организатора ≥ 0,45; на сагиттальном срезе КТ — 0,10; порог 0,3); КТ/МРТ — по служебным
надписям программы просмотра; всё, что есть на картинке кроме самого снимка (заголовки, водяные знаки, надписи
аппарата, цветные метки, чёрные поля), перечисляется отдельным списком elements с прочитанным текстом (dxaqc.ocr).
"""
from __future__ import annotations

import re

import numpy as np


def _mirror(a: np.ndarray) -> float:
    x, y = a - a.mean(), a[:, ::-1] - a.mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d else 0.0


def _column_mirror(a: np.ndarray) -> float:
    """Зеркальность окна вокруг столба позвонков: высокая в прямой проекции, низкая сбоку. Центр столба — середина
    самой широкой яркой вертикальной полосы (тела позвонков), а не самая яркая точка: та прыгает на отростки."""
    hh, ww = a.shape
    band = a[int(hh * .15):int(hh * .85)]
    prof = np.convolve(band.mean(0), np.ones(9) / 9, mode="same")
    inner = slice(ww // 8, ww - ww // 8)
    thr = (np.median(prof) + prof[inner].max()) / 2
    hot = prof > thr
    hot[:ww // 8] = hot[ww - ww // 8:] = False
    runs, start = [], None
    for x, v in enumerate(list(hot) + [False]):
        if v and start is None:
            start = x
        elif not v and start is not None:
            runs.append((x - start, start, x)); start = None
    c = (max(runs)[1] + max(runs)[2]) // 2 if runs else int(np.argmax(prof[inner])) + ww // 8
    best = -1.0
    for dc in range(-6, 7, 2):
        cc = c + dc
        r = min(cc, ww - cc, int(ww * 0.22))
        if r < 10:
            continue
        best = max(best, _mirror(band[:, cc - r:cc + r]))
    return best


def _full_height_column(a: np.ndarray) -> bool:
    """Яркий столб по центру и в верхней, и в нижней трети — позвоночник; у бедра диафиз только внизу."""
    hh, ww = a.shape
    t = ww // 3
    for part in (a[: hh // 3], a[2 * hh // 3:]):
        c, sd = part[:, t:2 * t].mean(), (part[:, :t].mean() + part[:, 2 * t:].mean()) / 2
        if c < 1.25 * max(sd, 1):
            return False
    return True


def _where(box) -> str:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    v = "вверху" if cy < 0.2 else "внизу" if cy > 0.8 else ""
    h = "слева" if cx < 0.3 else "справа" if cx > 0.7 else ""
    if v and h:
        return f"{'в левом' if h == 'слева' else 'в правом'} {'верхнем' if v == 'вверху' else 'нижнем'} углу"
    return v or h or "в середине"


_URL = re.compile(r"(www\.|https?://|\b[\w-]+\.(ru|com|org|net|su|рф|info|io|pro|me|dev|app|ai|moscow|tech|online|site)\b)", re.I)
_VIEWER = re.compile(r"\b(spin|tilt|zoom|ww|wl|w:|l:|hu|mpr|slice|thk|sl:|se:|im:|fov|kv|kvp|mas|ma|mm|sag|cor|ax|"
                     r"tr|te|t1|t2|flair|stir)\b", re.I)
_CT = re.compile(r"\b(spin|tilt|hu|mpr|kvp|mas)\b|\bкт\b|компьютерн", re.I)
_MR = re.compile(r"\b(t1|t2|flair|stir|tr|te)\b|\bмрт\b|магнитно", re.I)


def _n(k: int, one: str, few: str, many: str) -> str:
    w = one if k % 10 == 1 and k % 100 != 11 else few if 2 <= k % 10 <= 4 and not 12 <= k % 100 <= 14 else many
    return f"{k} {w}"


MAX_TEXTS = 8                                       # сколько надписей перечислять; остальные — числом


def _elements(path: str, rgb: np.ndarray, a: np.ndarray) -> tuple[list[str], dict]:
    """Всё, что на картинке кроме самого снимка: надписи (с текстом), водяные знаки, цветные метки, чёрные поля."""
    from dxaqc import ocr
    items, hints = [], dict(ct=False, mr=False, texts=[])
    lines = ocr.read(path)
    top = " ".join(ln["text"] for ln in lines if ln["box"][3] < 0.08)
    if re.search(r"\b\d{1,2}:\d{2}\s?(am|pm)?\b", top, re.I) and re.search(r"lte|5g|4g|3g|vpn|%|wi-?fi", top, re.I):
        items.append("строка состояния телефона вверху (время, связь, заряд) — это скриншот экрана телефона")
        lines = [ln for ln in lines if ln["box"][3] >= 0.08]
    if len(lines) > 12:
        items.append(f"много текста — {_n(len(lines), 'строка', 'строки', 'строк')}: похоже на скриншот страницы, переписки или документа")
    shown = 0
    for ln in lines:
        t, box = ln["text"], ln["box"]
        hints["texts"].append(t)
        hints["ct"] |= bool(_CT.search(t))
        hints["mr"] |= bool(_MR.search(t))
        if shown >= MAX_TEXTS:
            continue
        shown += 1
        where = _where(box)
        if _URL.search(t):
            items.append(f"водяной знак или логотип сайта {where}: «{t}»")
        elif "dicom" in t.lower() or re.search(r"x-?ray|/ct|mri|/pet", t, re.I):
            items.append(f"надпись в эмблеме {where}: «{t}»")
        elif _VIEWER.search(t):
            items.append(f"служебная надпись программы просмотра или аппарата {where}: «{t}»")
        elif box[1] < 0.12 and box[2] - box[0] > 0.3:
            items.append(f"заголовок {where}: «{t}»")
        else:
            items.append(f"надпись {where}: «{t}»")
    if len(lines) > MAX_TEXTS:
        items.append(f"и ещё {_n(len(lines) - MAX_TEXTS, 'надпись', 'надписи', 'надписей')}")
    sat = np.abs(rgb[..., 0] - rgb[..., 1]) + np.abs(rgb[..., 1] - rgb[..., 2])
    marks = float((sat > 60).mean())
    if 0.0005 < marks < 0.15:
        items.append(f"цветные метки поверх снимка — стрелки, линии или подписи ({marks:.1%} площади)".replace(".", ","))
    ww = a.shape[1]
    cols = a.mean(0)
    left = int(np.argmax(cols > 8)) if (cols > 8).any() else 0
    right = int(np.argmax(cols[::-1] > 8)) if (cols > 8).any() else 0
    if left > 0.08 * ww or right > 0.08 * ww:
        items.append("чёрные поля по бокам — снимок вписан в рамку, как на скриншоте программы просмотра")
    return items, hints


def describe_picture(path: str, preview: str | None = None) -> dict | None:
    from PIL import Image, ImageOps
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            rgb = np.asarray(im.convert("RGB").resize((96, max(1, round(96 * h / w)))), np.float32)
            gray = im.convert("L")
            if preview:
                g = gray.copy(); g.thumbnail((360, 360)); g.save(preview)
            a = np.asarray(gray.resize((200, max(1, round(200 * h / w)))), np.float32)
    except Exception:  # noqa: BLE001 — битая картинка: описания нет
        return None
    colorful = float(np.mean(np.abs(rgb[..., 0] - rgb[..., 1]) + np.abs(rgb[..., 1] - rgb[..., 2])))
    dark, bright = float((a < 50).mean()), float((a > 170).mean())
    mirror = _mirror(a)
    hh, ww = a.shape
    third = ww // 3
    center, sides = float(a[:, third:2 * third].mean()), float((a[:, :third].mean() + a[:, 2 * third:].mean()) / 2)
    low = a[int(hh * 0.7):]
    low_l, low_c, low_r = float(low[:, : ww // 4].mean()), float(low[:, 3 * ww // 8: 5 * ww // 8].mean()), float(low[:, 3 * ww // 4:].mean())
    prof = np.convolve(low.mean(0), np.ones(9) / 9, mode="same")          # профиль нижней трети: диафиз — одна яркая полоса
    shaft_ratio = float(prof.max() / max(prof.mean(), 1))
    xray = colorful < 10 and dark > 0.08
    elements, hints = _elements(path, rgb, a)
    modality = "КТ" if hints["ct"] else "МРТ" if hints["mr"] else ""
    facts = [f"картинка {w}×{h} px" + (", оттенки серого" if colorful < 10 else ", цветная")]
    if not xray:
        kind, title = "photo", "цветная фотография или рисунок, не рентгеновский снимок"
        facts.append("нет тёмного фона и серой шкалы, характерных для рентгена")
    elif mirror > 0.7 and 0.75 < ww / hh < 1.4 and min(low_l, low_r) > low_c * 0.9:
        kind, title = "pelvis", "обычный рентгеновский снимок таза в прямой проекции"
        facts += [f"изображение симметрично слева направо (сходство половин {mirror:.2f})".replace(".", ","),
                  "видны обе половины таза и верхние части обоих бёдер — оба тазобедренных сустава в кадре"]
    elif (center > 1.35 * max(sides, 1) and hh >= ww * 0.9 and mirror > 0.5 and _full_height_column(a)
          and (col_mirror := _column_mirror(a)) < 0.3):
        kind = "spine_lateral"
        title = (f"{modality} позвоночника, вид сбоку (сагиттальная реконструкция)" if modality else
                 "снимок позвоночника сбоку — боковая проекция или срез КТ/МРТ")
        facts.append("по центру яркий вертикальный столб — тела позвонков")
        facts.append(f"вокруг столба нет зеркальной симметрии (сходство половин {col_mirror:.2f}): спереди тела позвонков, "
                     "сзади отростки — так позвоночник выглядит сбоку".replace(".", ",", 1))
        if modality:
            facts.append(f"служебные надписи программы просмотра указывают на {modality}")
    elif center > 1.35 * max(sides, 1) and hh >= ww * 0.9 and mirror > 0.5:
        kind = "spine"
        title = (f"{modality} позвоночника во фронтальной плоскости" if modality else
                 "рентгеновский снимок позвоночника в прямой проекции")
        facts.append("по центру яркий вертикальный столб — тела позвонков")
    elif mirror < 0.6 and shaft_ratio > 1.8:
        kind, title = "hip", "рентгеновский снимок одного бедра"
        facts.append("внизу одна яркая вертикальная полоса — диафиз бедра, изображение несимметрично")
    else:
        kind, title = "xray", "рентгеновский снимок, область уверенно не определена"
        facts.append(f"тёмный фон {dark:.0%}, яркие костные участки {bright:.0%}".replace("%", " %"))
    dxa = ["Денситометрия (DXA) — это отдельное исследование на денситометре: снимок в DICOM около 300 px, "
           "поясничный отдел L1–L4 или одно бедро, с данными аппарата о протоколе и области.",
           "Обычный рентген и картинки (JPG, PNG) не содержат этих данных, поэтому критерии качества DXA к ним "
           "напрямую не применимы и вердикт не выносится."]
    if kind == "spine_lateral":
        dxa.append("DXA поясничного отдела снимают в прямой проекции, спереди назад; вид сбоку и срезы КТ/МРТ "
                   "по критериям качества DXA не оцениваются.")
    if modality:
        dxa.append(f"{modality} — другое исследование со своими правилами укладки; критерии качества DXA из ТЗ к нему "
                   "не применимы.")
    if kind == "pelvis":
        dxa.append("На обзорном снимке таза видны оба сустава сразу; для DXA бедро снимают отдельно — "
                   "левое и правое, каждое своим снимком.")
    todo = ["Выгрузите исследование с денситометра в DICOM (GE Lunar, Hologic и др.) — поясничный отдел или бедро.",
            "Посмотрите, как выглядит проверка, на готовом примере: главная → «или выберите готовый пример».",
            "Если нужно проверить именно эту картинку — запросите принудительный анализ: сервис приведёт её к масштабу "
            "DXA и разберёт с пометкой «результат не гарантирован»."]
    return dict(kind=kind, title=title, facts=facts, elements=elements, texts=hints["texts"], modality=modality,
                dxa=dxa, todo=todo,
                metrics=dict(colorful=round(colorful, 1), dark=round(dark, 3), mirror=round(mirror, 3), center=round(center, 1),
                             sides=round(sides, 1), shaft=round(shaft_ratio, 2)))
