# -*- coding: utf-8 -*-
"""Устойчивость к чужим и испорченным данным (28.09, Алексей: «убедись, что система работает на любых данных»).
Прогон на открытых наборах pydicom, pydicom-data и BonelabData показал: битый zip ронял весь пакет, а цветные картинки,
маски SEG и служебные скриншоты без модальности принимались за бедро. Здесь — те же случаи на встроенных файлах."""
import io
import os
import zipfile

import numpy as np
import pydicom
import pytest
from pydicom.data import get_testdata_file
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dxaqc import io as dio
from dxaqc import pipeline


def _load(path, root=None):
    return dio.load_image(str(path), str(root or os.path.dirname(path)))


def _dcm(path, pixels, **tags):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    colour = pixels.ndim == 3
    ds.Rows, ds.Columns = pixels.shape[:2]
    ds.SamplesPerPixel = 3 if colour else 1
    ds.PhotometricInterpretation = "RGB" if colour else "MONOCHROME2"
    if colour:
        ds.PlanarConfiguration = 0
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit, ds.PixelRepresentation = 7, 0
    ds.PixelData = pixels.astype(np.uint8).tobytes()
    for k, v in tags.items():
        setattr(ds, k, v)
    ds.save_as(str(path), enforce_file_format=True)
    return path


@pytest.mark.parametrize("name, words", [
    ("SC_rgb.dcm", "цветное изображение"),
    ("liver_1frame.dcm", "SEG"),
    ("rtdose.dcm", "RTDOSE"),
    ("CT_small.dcm", "компьютерная томография"),
])
def test_foreign_dicom_rejected_with_reason(name, words):
    res = _load(get_testdata_file(name))
    assert isinstance(res, dio.LoadFailure) and words in res.error and res.code == "not_dxa"


def test_empty_and_random_files(tmp_path):
    (tmp_path / "empty.dcm").write_bytes(b"")
    (tmp_path / "random.dcm").write_bytes(os.urandom(5000))
    assert "пустой" in _load(tmp_path / "empty.dcm").error
    r = _load(tmp_path / "random.dcm")
    assert isinstance(r, dio.LoadFailure) and ("не DICOM" in r.error or "модальность" in r.error)


def test_broken_and_nested_zip_do_not_stop_batch(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    (src / "broken.zip").write_bytes(b"PK\x03\x04" + b"\0" * 100)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.write(get_testdata_file("MR_small.dcm"), "mr.dcm")
    with zipfile.ZipFile(src / "nested.zip", "w") as z:
        z.writestr("inner.zip", inner.getvalue())
    work = tmp_path / "work"
    work.mkdir()
    root = pipeline._unpack_inputs(str(src), str(work))
    files = {os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs}
    assert os.path.join("nested", "inner", "mr.dcm") in files, "вложенный zip распакован"
    assert "broken.zip" in files, "битый архив остаётся — по нему строка отказа"
    fail = dio.load_image(os.path.join(root, "broken.zip"), root)
    assert "архив zip не распакован" in fail.error
    assert (src / "broken.zip").exists(), "исходные данные не тронуты"


def test_dxa_report_page_is_cropped_to_scan(tmp_path):
    page = np.full((1300, 1200, 3), 128, np.uint8)            # серая страница отчёта
    page[40:80, 100:1100] = 20                                 # чёрная строка заголовка — мелкий кусок
    page[300:580, 400:680] = 5                                 # чёрная панель снимка
    page[330:560, 500:560] = 200                               # светлая кость делит панель на части
    page[300:580, 470] = 255                                   # линия разметки
    res = _load(_dcm(tmp_path / "rep.dcm", page, Manufacturer="HOLOGIC", Modality="OT"))
    assert isinstance(res, dio.DicomImage), getattr(res, "error", "")
    h, w = res.pixels.shape
    assert 200 <= w <= 320 and 200 <= h <= 320, (w, h)
    assert "вырезан из отчёта" in res.meta["forced_note"] and res.meta["forced"] == "1"


def test_dxa_report_without_scan_is_explained(tmp_path):
    page = np.full((1300, 1200, 3), 128, np.uint8)
    res = _load(_dcm(tmp_path / "rep.dcm", page, Manufacturer="HOLOGIC", Modality="OT"))
    assert isinstance(res, dio.LoadFailure) and "отчёт денситометра" in res.error


def test_grey_dxa_like_file_still_accepted(tmp_path):
    img = (np.random.default_rng(0).random((290, 300)) * 200).astype(np.uint8)
    res = _load(_dcm(tmp_path / "cr.dcm", img, Modality="CR", Manufacturer="GE Healthcare",
                     ManufacturerModelName="Lunar Prodigy Advance"))
    assert isinstance(res, dio.DicomImage) and not res.meta.get("forced")


def test_broken_zip_as_whole_input(tmp_path):
    bad = tmp_path / "set.zip"
    bad.write_bytes(b"not a zip at all")
    out = tmp_path / "out"
    pipeline.main([str(bad), str(out)])
    import json
    m = json.load(open(out / "manifest.json", encoding="utf-8"))
    assert m["summary"]["failures"] == 1 and "архив zip не распакован" in m["rows"][0]["explanations"][0]
