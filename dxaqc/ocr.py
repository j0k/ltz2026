# -*- coding: utf-8 -*-
"""Чтение надписей на загруженной картинке (28.09, Юрий: «пиши все такие элементы дополнительным текстом»).

RapidOCR на onnxruntime: детектор строк PP-OCRv4 из пакета и кириллическая модель распознавания PaddlePaddle
cyrillic_PP-OCRv5_mobile_rec (Apache 2.0, ~8 МБ). Модель кладётся при сборке образа в /models/ocr, путь —
DXAQC_OCR_MODEL. Работает без сети. Нет пакета или модели — надписи просто не читаются, описание картинки строится
по изображению. Вызывается только для отклонённых картинок, проверку DICOM не замедляет.
"""
from __future__ import annotations

import os
import threading

KEYS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "ocr_cyrillic_keys.txt")
_DEFAULTS = ("/models/ocr/cyrillic_PP-OCRv5_mobile_rec.onnx",
             os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "models", "ocr", "cyrillic_PP-OCRv5_mobile_rec.onnx"))
MIN_SCORE = 0.8
_engine, _tried, _lock = None, False, threading.Lock()


def model_path() -> str | None:
    for p in (os.environ.get("DXAQC_OCR_MODEL"),) + _DEFAULTS:
        if p and os.path.isfile(p):
            return p
    return None


def _get():
    global _engine, _tried
    with _lock:
        if not _tried:
            _tried = True
            path = model_path()
            if path:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    _engine = RapidOCR(rec_model_path=path, rec_keys_path=KEYS, rec_img_shape=[3, 48, 320],
                                       print_verbose=False)
                except Exception:  # noqa: BLE001 — нет пакета или повреждена модель: работаем без надписей
                    _engine = None
        return _engine


def available() -> bool:
    return _get() is not None


def read(path: str) -> list[dict]:
    """Строки текста: text, score и рамка в долях кадра (x0, y0, x1, y1). Неуверенные строки отбрасываются."""
    eng = _get()
    if eng is None:
        return []
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        res, _ = eng(path)
    except Exception:  # noqa: BLE001 — надписи — дополнение, их сбой не мешает описанию
        return []
    out = []
    for box, text, score in res or []:
        text = " ".join(str(text).split())
        if float(score) < MIN_SCORE or len(text) < 2:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append(dict(text=text, score=round(float(score), 2),
                        box=(min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h)))
    out.sort(key=lambda r: (round(r["box"][1], 2), r["box"][0]))
    return out
