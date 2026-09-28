# -*- coding: utf-8 -*-
"""Чтение входных данных: архивы и файлы DICOM.

Требования ТЗ, которые закрывает модуль:
- нестандартные UID и прочие отступления от стандарта не роняют обработку;
- нечитаемый файл попадает в отчёт со статусом Failure, а не выбрасывает исключение;
- одинаковые снимки внутри исследования обрабатываются один раз.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import warnings
import zipfile
from dataclasses import dataclass, field

import numpy as np
import pydicom
from pydicom import config as dcm_config

warnings.filterwarnings("ignore", module="pydicom")
try:  # pydicom >= 2.3
    dcm_config.settings.reading_validation_mode = dcm_config.IGNORE
except AttributeError:  # pragma: no cover
    pass

MAX_FILES = 5000
MAX_UNPACKED_BYTES = 2 * 1024 ** 3


@dataclass
class DicomImage:
    path: str
    rel_path: str
    study_uid: str
    image_uid: str
    pixels: np.ndarray            # uint8, 2D
    sha: str
    meta: dict = field(default_factory=dict)


@dataclass
class LoadFailure:
    rel_path: str
    error: str
    code: str = "unreadable"   # not_dicom — картинка, not_dxa — DICOM не денситометрии, unreadable — не прочитан
    forceable: bool = False    # можно проверить принудительно после одобрения админа


# картинки не пропускаем молча: человек загрузил их как снимок и должен узнать, почему они не проверены
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif")
SKIP_EXT = (".xlsx", ".xls", ".csv", ".txt", ".pdf", ".doc", ".docx", ".json", ".md")
FORCE_MAX_SIDE = 320   # принудительный анализ приводит кадр к масштабу DXA, около 300 px
NON_DXA_MODALITY = {"CT": "компьютерная томография", "MR": "МРТ", "US": "УЗИ", "PT": "ПЭТ", "NM": "радионуклидное исследование",
                    "MG": "маммография", "XA": "ангиография", "RF": "рентгеноскопия", "ES": "эндоскопия", "OP": "офтальмология",
                    "IO": "внутриротовой снимок", "PX": "панорамный снимок зубов", "SM": "микроскопия", "ECG": "ЭКГ",
                    "RTDOSE": "дозовое распределение лучевой терапии", "RTPLAN": "план лучевой терапии",
                    "RTSTRUCT": "контуры лучевой терапии", "RTIMAGE": "снимок лучевой терапии", "SR": "структурированный отчёт",
                    "SEG": "сегментация", "PR": "состояние отображения", "KO": "отметка ключевых снимков",
                    "REG": "совмещение изображений", "DOC": "документ", "AU": "аудиозапись", "HD": "гемодинамика"}
DXA_WORDS = ("dxa", "dexa", "densit", "денсит", "bmd", "lunar", "prodigy", "hologic", "horizon", "norland", "stratos",
             "osteosys", "primus", "medix")


def _dxa_named(ds) -> bool:
    """В описании серии, у производителя или модели есть признаки денситометра."""
    text = " ".join(str(ds.get(k, "")) for k in ("SeriesDescription", "StudyDescription", "ProtocolName", "Manufacturer",
                                                 "ManufacturerModelName", "BodyPartExamined", "ImageType")).lower()
    return any(w in text for w in DXA_WORDS)


def _is_colour(ds) -> bool:
    pi = str(ds.get("PhotometricInterpretation", "")).upper()
    return int(ds.get("SamplesPerPixel", 1) or 1) > 1 or pi.startswith(("RGB", "YBR", "PALETTE"))


def dxa_problem(ds, shape) -> str | None:
    """Причина считать DICOM не денситометрией DXA или None. Признаки денситометра в описании снимают подозрения
    (отчёт денситометра разбирается отдельно — см. find_scan_panel)."""
    if _dxa_named(ds):
        return None
    modality = str(ds.get("Modality", "") or "").upper().strip()
    if not modality:
        return ("в файле не указана модальность и нет признаков денситометра — похоже на тестовую или служебную "
                "картинку, а не снимок исследования")
    if modality in NON_DXA_MODALITY:
        return f"модальность {modality} ({NON_DXA_MODALITY[modality]}) — это не денситометрия DXA"
    if int(ds.get("BitsStored", 8) or 8) == 1:
        return "однобитное изображение — это маска или разметка, а не снимок"
    if _is_colour(ds):
        return (f"цветное изображение ({str(ds.get('PhotometricInterpretation', '')) or 'цвет'}) — снимки DXA "
                "в оттенках серого, а признаков денситометра в файле нет")
    if modality == "OT":
        return ("вторичный захват (Modality OT) без признаков денситометра — это скриншот или служебная картинка, "
                "а не снимок DXA")
    h, w = shape[:2]
    if max(h, w) > 1024:
        return (f"кадр {w}×{h} px похож на обычный рентген: снимки DXA около 300×300 px, "
                "а в описании серии и у производителя нет признаков денситометра")
    return None


def find_scan_panel(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """Отчёт денситометра (страница с таблицами и графиком): найти на нём сам снимок — самую крупную тёмную
    прямоугольную панель. Возвращает (y0, y1, x0, x1) в пикселях страницы или None."""
    h, w = gray.shape
    k = max(1, min(h, w) // 300)                       # грубая сетка: ~300 клеток по короткой стороне
    hh, ww = h // k, w // k
    dark = gray[:hh * k, :ww * k].reshape(hh, k, ww, k).mean(axis=(1, 3)) < 45
    seen = np.zeros_like(dark, bool)
    boxes = []                                         # (клеток, y0, y1, x0, x1) каждого тёмного куска
    for sy, sx in zip(*np.nonzero(dark)):
        if seen[sy, sx]:
            continue
        stack, n, y0, y1, x0, x1 = [(sy, sx)], 0, sy, sy, sx, sx
        seen[sy, sx] = True
        while stack:
            y, x = stack.pop()
            n += 1
            y0, y1, x0, x1 = min(y0, y), max(y1, y), min(x0, x), max(x1, x)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < hh and 0 <= nx < ww and dark[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        boxes.append((n, y0, y1 + 1, x0, x1 + 1))
    if not boxes:
        return None
    # панель снимка разрезана светлой костью и линиями разметки на вертикальные куски с общими верхом и низом —
    # собираем их вместе с самым крупным куском
    _, y0, y1, x0, x1 = max(boxes)
    tol = max(2, (y1 - y0) // 20)
    for n, by0, by1, bx0, bx1 in boxes:
        if n >= 10 and abs(by0 - y0) <= tol and abs(by1 - y1) <= tol and min(abs(bx0 - x1), abs(x0 - bx1)) <= (y1 - y0):
            x0, x1 = min(x0, bx0), max(x1, bx1)
    bh, bw = y1 - y0, x1 - x0
    share = bh * bw / (hh * ww)
    if not (0.02 <= share <= 0.6) or not (0.5 <= bw / bh <= 2.0) or min(bh, bw) * k < 64:
        return None                                    # не похоже на панель снимка
    return y0 * k, y1 * k, x0 * k, x1 * k


def _shrink(pixels: np.ndarray) -> np.ndarray:
    h, w = pixels.shape
    if max(h, w) <= FORCE_MAX_SIDE:
        return pixels
    from PIL import Image
    r = FORCE_MAX_SIDE / max(h, w)
    return np.asarray(Image.fromarray(pixels).resize((max(32, round(w * r)), max(32, round(h * r))), Image.LANCZOS))


def _load_picture(path: str, rel: str) -> DicomImage | LoadFailure:
    """Картинка для принудительного анализа: оттенки серого и масштаб DXA."""
    from PIL import Image, ImageOps
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            pixels = np.asarray(im.convert("L"), np.uint8)
    except Exception as exc:  # битая картинка
        return LoadFailure(rel, f"картинку не удалось открыть: {type(exc).__name__}", code="unreadable")
    ext = os.path.splitext(path)[1].lstrip(".").upper()
    study = os.path.basename(os.path.dirname(rel)) or "принудительно"
    from dxaqc.describe import describe_picture
    desc = describe_picture(path) or {}
    if desc.get("kind") == "pelvis" and pixels.shape[1] >= 64:
        # обзорный снимок таза: на DXA каждое бедро снимают отдельно — режем пополам и разбираем как два бедра.
        # Пациент лежит лицом к нам: левая половина кадра — его правое бедро.
        half, out = pixels.shape[1] // 2, []
        for part, side in ((pixels[:, :half], "правое бедро — левая половина кадра"),
                           (pixels[:, half:], "левое бедро — правая половина кадра")):
            px = _shrink(np.ascontiguousarray(part))
            sha = hashlib.sha1(px.tobytes()).hexdigest()
            note = (f"Принудительный анализ: исходный файл — картинка {ext} {w}×{h} px, не DICOM: обычный рентген таза. "
                    f"На денситометрии бедро снимают отдельно, поэтому снимок разрезан пополам; здесь {side}. "
                    f"Масштаб приведён к DXA. Результат не гарантирован.")
            out.append(DicomImage(path, f"{rel} · {side}", study, sha[:16], px, sha,
                                  {"Modality": ext, "forced": "1", "forced_note": note}))
        return out
    pixels = _shrink(pixels)
    if min(pixels.shape) < 32:
        return LoadFailure(rel, f"картинка слишком маленькая: {w}×{h} px", code="unreadable")
    sha = hashlib.sha1(pixels.tobytes()).hexdigest()
    note = (f"Принудительный анализ: исходный файл — картинка {ext} {w}×{h} px, не DICOM; переведена в оттенки серого "
            f"и приведена к масштабу DXA. Результат не гарантирован.")
    return DicomImage(path, rel, study, sha[:16], pixels, sha, {"Modality": ext, "forced": "1", "forced_note": note})


def safe_extract(zip_path: str, dest: str) -> list[str]:
    """Распаковать архив без выхода за пределы dest и с ограничением объёма."""
    dest_real = os.path.realpath(dest)
    out, total = [], 0
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) > MAX_FILES:
            raise ValueError(f"слишком много файлов в архиве: {len(members)}")
        for m in members:
            name = m.filename
            try:  # имена из Windows-архивов часто в cp866
                if not (m.flag_bits & 0x800):
                    name = name.encode("cp437").decode("cp866")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            target = os.path.realpath(os.path.join(dest, name))
            if not target.startswith(dest_real + os.sep):
                continue
            total += m.file_size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError("архив слишком большой после распаковки")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(m) as src, open(target, "wb") as dst:
                dst.write(src.read())
            out.append(target)
    return out


def unpack_archives(root: str, on_archive=None, max_depth: int = 3) -> int:
    """Распаковать все zip в папке на месте, включая вложенные (до max_depth уровней): архив → папка с его именем.
    Распакованный архив удаляется. Битый, пустой или слишком большой архив остаётся как есть — при чтении по нему
    будет строка отказа с причиной, а проверка остальных файлов продолжится. Возвращает число распакованных архивов.
    on_archive(номер, всего, относительный путь) — для прогресса."""
    done, bad = 0, set()
    for _ in range(max_depth):
        zips = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs
                      if f.lower().endswith(".zip") and os.path.join(d, f) not in bad)
        if not zips:
            break
        for i, z in enumerate(zips):
            target = os.path.splitext(z)[0]
            try:
                safe_extract(z, target)
                os.remove(z)
                done += 1
            except Exception as exc:  # noqa: BLE001 — архив не должен ронять проверку остальных файлов
                shutil.rmtree(target, ignore_errors=True)
                bad.add(z)
                BAD_ARCHIVES[os.path.realpath(z)] = f"{type(exc).__name__}: {exc}"
            if on_archive:
                on_archive(i + 1, len(zips), os.path.relpath(z, root))
    return done


# причины, по которым архив не распакован: путь → текст; читает load_image для строки отказа
BAD_ARCHIVES: dict[str, str] = {}


def iter_candidate_files(root: str):
    for dirpath, _, files in os.walk(root, followlinks=True):   # наборы подключаются ссылками
        for f in sorted(files):
            if f.startswith(".") or f.lower().endswith(SKIP_EXT):
                continue
            yield os.path.join(dirpath, f)


def _to_uint8(ds, arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=-1) if arr.shape[-1] in (3, 4) else arr[0]
    arr = arr.astype(np.float32)
    if str(ds.get("PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        arr = arr.max() - arr
    if arr.max() <= 255 and arr.min() >= 0 and int(ds.get("BitsAllocated", 8) or 8) <= 8:
        return arr.astype(np.uint8)
    lo, hi = np.percentile(arr, [0.5, 99.5])
    return np.clip((arr - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)


def load_image(path: str, root: str, force: bool = False) -> DicomImage | LoadFailure:
    rel = os.path.relpath(path, root)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".zip":
        why = BAD_ARCHIVES.get(os.path.realpath(path), "")
        return LoadFailure(rel, "архив zip не распакован: он повреждён, пуст, защищён паролем или слишком большой"
                                + (f" ({why})" if why else "") + ". Проверьте архив и загрузите его заново", code="unreadable")
    if ext in IMAGE_EXT:
        if force:
            return _load_picture(path, rel)
        return LoadFailure(rel, f"файл {ext.lstrip('.').upper()} — это картинка, а не DICOM. Сервис проверяет DICOM денситометрии DXA: "
                                "поясничный отдел и бедро", code="not_dicom", forceable=True)
    try:
        size = os.path.getsize(path)
        if size == 0:
            return LoadFailure(rel, "файл пустой (0 байт) — скорее всего, он не докачался или не скопировался")
        with open(path, "rb") as fh:
            has_magic = fh.read(132)[128:132] == b"DICM"
        # сначала только заголовок: модальность видно сразу, и чужое исследование отсекается без распаковки пикселей
        head = pydicom.dcmread(path, force=True, stop_before_pixels=True)
        if not has_magic and not any(k in head for k in ("SOPClassUID", "Modality", "StudyInstanceUID", "Rows")):
            return LoadFailure(rel, "это не DICOM: в файле нет ни заголовка DICOM, ни тегов снимка. Сервис проверяет "
                                    "DICOM денситометрии DXA", code="not_dicom")
        early = dxa_problem(head, (int(head.get("Rows", 0) or 0), int(head.get("Columns", 0) or 0)))
        if early and not force:
            return LoadFailure(rel, f"DICOM не похож на денситометрию DXA: {early}", code="not_dxa", forceable=True)
        ds = pydicom.dcmread(path, force=True)
        if "PixelData" not in ds:
            return LoadFailure(rel, "в файле нет изображения")
        try:
            raw = ds.pixel_array
        except Exception as exc:                      # сжатый DICOM, который нечем разжать, или повреждённые пиксели
            syntax = getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", None)
            how = getattr(syntax, "name", None) or (str(syntax) if syntax else "неизвестный метод")
            if syntax is not None and getattr(syntax, "is_compressed", False):
                return LoadFailure(rel, f"файл сжат ({how}) и не разжимается этим сервисом: {type(exc).__name__}. "
                                        "Пришлите тот же снимок без сжатия", code="unreadable")
            return LoadFailure(rel, f"изображение в файле повреждено и не читается ({type(exc).__name__}: {str(exc)[:120]}). "
                                    "Выгрузите снимок из аппарата заново", code="unreadable")
        pixels = _to_uint8(ds, raw)
        if pixels.ndim != 2:
            return LoadFailure(rel, f"неподдерживаемая форма изображения {pixels.shape}: ожидается один плоский снимок")
        if min(pixels.shape) < 32:
            return LoadFailure(rel, f"изображение слишком маленькое: {pixels.shape[1]}×{pixels.shape[0]} px — "
                                    "снимки DXA около 300×300 px")
        report_note = ""
        if _dxa_named(ds) and (_is_colour(ds) or max(pixels.shape) > 1024):
            # отчёт денситометра (скриншот страницы с таблицами): проверяем только вырезанный из него снимок
            box = find_scan_panel(pixels)
            if not box:
                return LoadFailure(rel, "это отчёт денситометра (страница с таблицами), а снимка на нём найти не удалось. "
                                        "Выгрузите из денситометра исходный снимок DICOM", code="not_dxa", forceable=True)
            y0, y1, x0, x1 = box
            pixels = _shrink(np.ascontiguousarray(pixels[y0:y1, x0:x1]))
            report_note = (f"Снимок вырезан из отчёта денситометра {str(ds.get('Manufacturer', '') or '').strip()} "
                           f"(область {x1 - x0}×{y1 - y0} px). Критерии рассчитаны на исходный снимок GE Lunar — "
                           "результат ориентировочный.")
        problem = dxa_problem(ds, pixels.shape)
        if problem and not force:
            return LoadFailure(rel, f"DICOM не похож на денситометрию DXA: {problem}", code="not_dxa", forceable=True)
        forced_note = ""
        if problem:
            h, w = pixels.shape
            pixels = _shrink(pixels)
            forced_note = (f"Принудительный анализ: {problem}; кадр {w}×{h} px приведён к масштабу DXA. "
                           "Результат не гарантирован.")
        sha = hashlib.sha1(pixels.tobytes()).hexdigest()
        meta = {k: str(ds.get(k, "")) for k in ("Modality", "Manufacturer", "ManufacturerModelName",
                                              "SeriesDescription", "Rows", "Columns")}
        if forced_note or report_note:
            meta.update(forced="1", forced_note=" ".join(x for x in (report_note, forced_note) if x))
        study = str(ds.get("StudyInstanceUID", "") or "") or os.path.basename(os.path.dirname(path))
        image = str(ds.get("SOPInstanceUID", "") or "") or sha[:16]
        return DicomImage(path, rel, study, image, pixels, sha, meta)
    except Exception as exc:  # файл не должен ронять пакет
        return LoadFailure(rel, f"{type(exc).__name__}: {exc}"[:300])


def collect(root: str, on_file=None, force: bool = False):
    """Все снимки из папки: уникальные изображения, отказы и число схлопнутых дублей.
    on_file(прочитано, всего, относительный путь) вызывается после каждого файла — для живого прогресса.
    force — принудительный анализ: картинки и DICOM не DXA тоже проверяются, с пометкой в пояснениях."""
    images, failures, seen, dups = [], [], set(), 0
    paths = list(iter_candidate_files(root))
    for i, path in enumerate(paths):
        res = load_image(path, root, force=force)
        if on_file:
            on_file(i + 1, len(paths), os.path.relpath(path, root))
        if isinstance(res, LoadFailure):
            failures.append(res)
            continue
        for one in (res if isinstance(res, list) else [res]):   # обзорный таз при принудительном анализе — два снимка
            key = (one.study_uid, one.sha)
            if key in seen:
                dups += 1
                continue
            seen.add(key)
            images.append(one)
    return images, failures, dups
