# -*- coding: utf-8 -*-
"""Синтетический фантом DXA для демо и самопроверки: не снимок пациента, данные организатора в приложение не входят.

Поясничный отдел — 300 px в ширину (протокол позвоночника), бедро — 280 px (протокол бедра), как у GE Lunar
в данных задачи; в описании серии — пометка «синтетический фантом».
"""
from __future__ import annotations

import os

import numpy as np


def _noise(h, w, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(0, 3.0, (h, w))


def _blur(a, k=5):
    from dxaqc.analyze import _blur as b
    return b(a.astype(np.float32), k)


def spine(artifact: bool = False, tilt_deg: float = 0.0, seed: int = 1) -> np.ndarray:
    h, w = 317, 300
    a = np.full((h, w), 12.0) + _noise(h, w, seed)
    yy, xx = np.mgrid[0:h, 0:w]
    k = np.tan(np.radians(tilt_deg))
    # мягкие ткани вокруг столба
    a += 28 * np.exp(-((xx - w / 2) / 70.0) ** 2)
    # шесть позвонков (Th12–L5) и межпозвонковые щели
    top, step = 28, 44
    for i in range(6):
        cy = top + i * step + 18
        cx = w / 2 + k * (cy - h / 2)
        half_w = 34 + i * 2.5
        body = (np.abs(xx - cx) < half_w) & (np.abs(yy - cy) < 17)
        a[body] += 150 - i * 4
        a[(np.abs(xx - cx) < 8) & (np.abs(yy - cy) < 10)] += 30          # остистый отросток
    # гребни подвздошных костей в нижних углах
    for sx in (40, w - 40):
        crest = ((xx - sx) / 58.0) ** 2 + ((yy - (h + 18)) / 52.0) ** 2 < 1
        a[crest] += 95
    if artifact:                                                        # металлическая застёжка сбоку от столба
        a[(np.abs(xx - 232) < 7) & (np.abs(yy - 120) < 11)] = 255
    return np.clip(_blur(a, 3), 0, 255).astype(np.uint8)


def hip(side: str = "left", seed: int = 2) -> np.ndarray:
    h, w = 300, 280
    a = np.full((h, w), 10.0) + _noise(h, w, seed)
    yy, xx = np.mgrid[0:h, 0:w]
    # рисуем левое бедро (таз слева от диафиза), правое — зеркально; кости не касаются краёв кадра
    shaft_x = 168
    a[(np.abs(xx - shaft_x) < 21) & (yy > 165) & (yy < 292)] += 150                 # диафиз
    neck = np.abs((yy - 160) + 0.8 * (xx - shaft_x + 8)) < 15
    a[neck & (xx > 108) & (xx < shaft_x + 5) & (yy < 185) & (yy > 95)] += 140
    head = ((xx - 104) ** 2 + (yy - 104) ** 2) < 27 ** 2
    a[head] += 155
    a[((xx - 198) / 24.0) ** 2 + ((yy - 142) / 32.0) ** 2 < 1] += 130               # большой вертел
    a[((xx - 146) / 11.0) ** 2 + ((yy - 202) / 9.0) ** 2 < 1] += 60                 # малый вертел
    pelvis = (((xx - 70) / 48.0) ** 2 + ((yy - 96) / 62.0) ** 2 < 1) & ~(((xx - 104) ** 2 + (yy - 104) ** 2) < 31 ** 2)
    a[pelvis] += 150
    a = np.clip(_blur(a, 5), 0, 255).astype(np.uint8)
    return a if side == "left" else a[:, ::-1].copy()


def write_dicom(path: str, pixels: np.ndarray, desc: str, study_uid: str, series_no: int):
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid, SecondaryCaptureImageStorage
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = SecondaryCaptureImageStorage, meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, generate_uid()
    ds.Modality = "OT"
    ds.Manufacturer = "DXA QC synthetic phantom"
    ds.SeriesDescription = f"DXA {desc} — синтетический фантом, не снимок пациента"
    ds.PatientName, ds.PatientID = "PHANTOM^DXAQC", "PHANTOM"
    ds.SeriesNumber, ds.InstanceNumber = series_no, 1
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit, ds.PixelRepresentation = 7, 0
    ds.PixelData = pixels.tobytes()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ds.save_as(path, enforce_file_format=True)


def study(dest: str, variant: str = "ok") -> list[str]:
    """Исследование-фантом: поясница и оба бедра. variant: ok | artifact."""
    from pydicom.uid import generate_uid
    uid = generate_uid()
    folder = os.path.join(dest, f"phantom_{variant}")
    files = [(os.path.join(folder, "spine.dcm"), spine(artifact=variant == "artifact"), "lumbar spine"),
             (os.path.join(folder, "hip_left.dcm"), hip("left"), "left hip"),
             (os.path.join(folder, "hip_right.dcm"), hip("right"), "right hip")]
    for i, (p, px, d) in enumerate(files, 1):
        write_dicom(p, px, d, uid, i)
    return [p for p, _, _ in files]
