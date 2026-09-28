# -*- coding: utf-8 -*-
"""Что на отклонённой картинке: описание вместо тупика «это не DICOM» (не вердикт качества).

Признаки простые и проверяемые: цветность (рентген — оттенки серого), тёмный фон, зеркальная симметрия,
яркий столб по центру (позвоночник), кости у нижних краёв (диафизы бёдер). По ним — догадка об области
и объяснение, чем картинка отличается от снимка денситометрии и что с ней можно сделать.
"""
from __future__ import annotations

import numpy as np


def _mirror(a: np.ndarray) -> float:
    x, y = a - a.mean(), a[:, ::-1] - a.mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d else 0.0


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
    facts = [f"картинка {w}×{h} px" + (", оттенки серого" if colorful < 10 else ", цветная")]
    if not xray:
        kind, title = "photo", "цветная фотография или рисунок, не рентгеновский снимок"
        facts.append("нет тёмного фона и серой шкалы, характерных для рентгена")
    elif mirror > 0.7 and 0.75 < ww / hh < 1.4 and min(low_l, low_r) > low_c * 0.9:
        kind, title = "pelvis", "обычный рентгеновский снимок таза в прямой проекции"
        facts += [f"изображение симметрично слева направо (сходство половин {mirror:.2f})".replace(".", ","),
                  "видны обе половины таза и верхние части обоих бёдер — оба тазобедренных сустава в кадре"]
    elif center > 1.35 * max(sides, 1) and hh >= ww * 0.9 and mirror > 0.5:
        kind, title = "spine", "рентгеновский снимок позвоночника в прямой проекции"
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
    if kind == "pelvis":
        dxa.append("На обзорном снимке таза видны оба сустава сразу; для DXA бедро снимают отдельно — "
                   "левое и правое, каждое своим снимком.")
    todo = ["Выгрузите исследование с денситометра в DICOM (GE Lunar, Hologic и др.) — поясничный отдел или бедро.",
            "Посмотрите, как выглядит проверка, на готовом примере: главная → «или выберите готовый пример».",
            "Если нужно проверить именно эту картинку — запросите принудительный анализ: сервис приведёт её к масштабу "
            "DXA и разберёт с пометкой «результат не гарантирован»."]
    return dict(kind=kind, title=title, facts=facts, dxa=dxa, todo=todo,
                metrics=dict(colorful=round(colorful, 1), dark=round(dark, 3), mirror=round(mirror, 3), center=round(center, 1),
                             sides=round(sides, 1), shaft=round(shaft_ratio, 2)))
