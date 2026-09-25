# -*- coding: utf-8 -*-
"""Отказы с причиной, принудительный анализ и анализ снимка в Claude с одобрения админа."""
from __future__ import annotations

import base64
import io
import re
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from dxaqc.io import collect

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-1"
has_data = (ROOT / "data" / "Для теста").exists()


def accounts():
    return sys.modules["dxaqc.web.accounts"]


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def picture(fmt: str, w=1200, h=900) -> bytes:
    g = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    buf = io.BytesIO()
    Image.fromarray(g).save(buf, fmt)
    return buf.getvalue()


def ct_dicom(path: Path, size: int = 64):
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    ct = "1.2.840.10008.5.1.4.1.1.2"
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID, meta.TransferSyntaxUID = ct, generate_uid(), ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Modality, ds.SOPClassUID, ds.SOPInstanceUID, ds.StudyInstanceUID = "CT", ct, meta.MediaStorageSOPInstanceUID, generate_uid()
    ds.Rows = ds.Columns = size
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = 8, 8, 7, 0, 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.random.default_rng(1).integers(0, 255, (size, size), dtype=np.uint8).tobytes()
    ds.save_as(str(path), enforce_file_format=True)


def test_loader_rejects_pictures_and_non_dxa_and_forces_them(tmp_path):
    (tmp_path / "study").mkdir()
    (tmp_path / "study" / "xray.jpg").write_bytes(picture("JPEG"))
    ct_dicom(tmp_path / "study" / "ct.dcm")
    (tmp_path / "notes.txt").write_text("не снимок")
    images, failures, _ = collect(str(tmp_path))
    by = {f.rel_path: f for f in failures}
    assert not images and set(by) == {"study/xray.jpg", "study/ct.dcm"}, "текстовый файл пропускается молча, картинка — нет"
    assert by["study/xray.jpg"].code == "not_dicom" and by["study/xray.jpg"].forceable and "JPG" in by["study/xray.jpg"].error
    assert by["study/ct.dcm"].code == "not_dxa" and "компьютерная томография" in by["study/ct.dcm"].error

    images, failures, _ = collect(str(tmp_path), force=True)
    assert not failures and len(images) == 2
    pic = next(i for i in images if i.rel_path.endswith(".jpg"))
    assert max(pic.pixels.shape) == 320 and pic.meta["forced"] and "Принудительный анализ" in pic.meta["forced_note"]


@pytest.fixture()
def browsers(client):
    made = []

    def make():
        c = TestClient(client.app)
        made.append(c)
        return c
    yield make
    for c in made:
        c.close()


def login(browsers, name, admin=False):
    A = accounts()
    if not A.get_user_by_login(name):
        A.create_user(name, PASSWORD, role="admin" if admin else "user", can_ask=admin)
    c = browsers()
    assert c.post("/login", data={"login": name, "password": PASSWORD}, follow_redirects=False).status_code == 303
    return c


def wait_run(client, rid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/runs/{rid}/progress").json()
        if st["state"] in ("done", "error", "cancelled"):
            return client.get(f"/api/runs/{rid}").json()
        time.sleep(0.3)
    raise AssertionError("прогон не завершился")


def request_on(c, rid, kind, target):
    token = csrf_of(c.get("/account").text)   # у прогона без кнопок запроса формы нет, токен сессии тот же
    return c.post(f"/runs/{rid}/requests", data={"kind": kind, "target": target, "csrf": token}, follow_redirects=False)


def test_force_and_claude_requests_need_admin_approval(client, browsers, broker):
    A = accounts()
    anon = browsers()
    r = anon.post("/runs", files=[("files", ("r-p.jpg", picture("JPEG"), "image/jpeg")),
                                  ("files", ("photo.png", picture("PNG", 400, 300), "image/png"))], follow_redirects=False)
    rid = r.headers["location"].rsplit("/", 1)[1]
    data = wait_run(client, rid)
    assert data["summary"]["images"] == 0 and data["summary"]["failures"] == 2
    page = anon.get(f"/runs/{rid}").text
    assert 'id="no-images"' in page and "это картинка, а не DICOM" in page and f'href="/login?next=/runs/{rid}"' in page

    user = login(browsers, "requester")
    assert request_on(user, rid, "force", "r-p.jpg").status_code == 303
    req = next(x for x in A.pending_requests() if x["run_id"] == rid and x["target"] == "r-p.jpg")
    assert req["kind"] == "force" and req["login"] == "requester"
    assert "ждёт одобрения админа" in user.get(f"/runs/{rid}").text

    admin = login(browsers, "req-admin", admin=True)
    admin_page = admin.get("/admin").text
    assert 'id="requests"' in admin_page and "r-p.jpg" in admin_page
    assert user.post(f"/admin/requests/{req['id']}", data={"decision": "approve", "csrf": csrf_of(user.get(f"/runs/{rid}").text)}).status_code == 403
    assert admin.post(f"/admin/requests/{req['id']}", data={"decision": "approve", "csrf": csrf_of(admin_page)},
                      follow_redirects=False).status_code == 303
    done = A.get_request(req["id"])
    assert done["status"] == "approved" and done["approver"] == "req-admin" and done["result_run"]
    forced = wait_run(client, done["result_run"])
    row = forced["rows"][0]
    assert row["forced"] and row["explanations"][0].startswith("Принудительный анализ: исходный файл — картинка JPG")
    assert "Результат принудительного анализа" in user.get(f"/runs/{rid}").text
    assert "Принудительный анализ файла" in user.get(f"/runs/{done['result_run']}").text

    # анализ в Claude: после одобрения вопрос со снимком уходит брокеру, ответ видит автор
    assert request_on(user, rid, "claude", "r-p.jpg").status_code == 303
    creq = next(x for x in A.pending_requests() if x["kind"] == "claude")
    admin.post(f"/admin/requests/{creq['id']}", data={"decision": "approve", "csrf": csrf_of(admin.get("/admin").text)})
    creq = A.get_request(creq["id"])
    q = A.get_question(creq["question_id"])
    assert q["mode"] == "read" and Path(q["attachment"]).read_bytes().startswith(b"\x89PNG")
    t0 = time.time()
    while A.get_question(q["id"])["status"] not in ("done", "error") and time.time() - t0 < 20:
        time.sleep(0.1)
    assert A.get_question(q["id"])["status"] == "done"
    call = next(c for c in broker.calls if c["id"].startswith(f"ltz-q{q['id']}-"))
    assert base64.b64decode(call["attachments"][0]["data"]).startswith(b"\x89PNG") and "пригодно ли оно" in call["text"]
    assert f'href="/ask#q{q["id"]}"' in user.get(f"/runs/{rid}").text
    assert f'href="/ask#q{q["id"]}"' not in anon.get(f"/runs/{rid}").text, "ссылку на ответ видят автор и админы"

    # отклонение и запрос админа, который выполняется сразу
    assert request_on(user, rid, "force", "photo.png").status_code == 303
    rej = next(x for x in A.pending_requests() if x["target"] == "photo.png")
    admin.post(f"/admin/requests/{rej['id']}", data={"decision": "reject", "csrf": csrf_of(admin.get("/admin").text)})
    assert A.get_request(rej["id"])["status"] == "rejected" and "отклонено админом" in user.get(f"/runs/{rid}").text
    assert request_on(admin, rid, "force", "photo.png").status_code == 303
    own = [x for x in A.run_requests(rid) if x["target"] == "photo.png" and x["user_id"] == A.get_user_by_login("req-admin")["id"]][-1]
    assert own["status"] == "approved" and own["result_run"]
    assert request_on(user, rid, "force", "nope.jpg").status_code == 404


@pytest.mark.skipif(not has_data, reason="нет тестовых данных организатора")
def test_organizer_images_are_not_sent_to_claude(client, browsers):
    rid = client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    data = wait_run(client, rid)
    row = next(r for r in data["rows"] if r["processing_status"] == "Success")
    user = login(browsers, "requester2")
    r = request_on(user, rid, "claude", row["path_to_study"])
    assert r.status_code == 400 and "не отправляются" in r.text
    assert request_on(user, rid, "force", row["path_to_study"]).status_code == 400, "успешный снимок не принуждают"
    card = user.get(f"/runs/{rid}/images/{row['key']}").text
    assert "Спросить Claude про этот снимок" not in card


def mr_dicom(path, compressed=False):
    """Синтетическая МРТ: модальность MR, без пикселей DXA — такие файлы сервис принимать не должен."""
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, JPEGLosslessSV1, generate_uid
    mr = "1.2.840.10008.5.1.4.1.1.4"
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID = mr, generate_uid()
    meta.TransferSyntaxUID = JPEGLosslessSV1 if compressed else ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Modality, ds.SOPClassUID, ds.SOPInstanceUID, ds.StudyInstanceUID = "MR", mr, meta.MediaStorageSOPInstanceUID, generate_uid()
    ds.SeriesDescription = "AX. FSE PD"
    ds.Rows = ds.Columns = 512
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = 8, 8, 7, 0, 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    if compressed:
        from pydicom.encaps import encapsulate
        ds.PixelData = encapsulate([b"\xff\xd8\xff\xee not really jpeg"])   # заголовок есть, данных нет
        ds["PixelData"].is_undefined_length = True
    else:
        ds.PixelData = np.zeros((512, 512), dtype=np.uint8).tobytes()
    ds.save_as(str(path), enforce_file_format=True)


def test_mri_is_rejected_by_header_before_decoding(tmp_path):
    from dxaqc.io import load_image
    mr_dicom(tmp_path / "mri.dcm")
    fail = load_image(str(tmp_path / "mri.dcm"), str(tmp_path))
    assert fail.code == "not_dxa" and "MR" in fail.error and "МРТ" in fail.error, fail.error
    assert fail.forceable, "принудительный анализ остаётся возможным"


def test_unreadable_compression_is_explained(tmp_path):
    from dxaqc.io import load_image
    mr_dicom(tmp_path / "packed.dcm", compressed=True)
    fail = load_image(str(tmp_path / "packed.dcm"), str(tmp_path), force=True)   # force, чтобы дойти до распаковки
    assert fail.code == "unreadable" and "сжат" in fail.error and "без сжатия" in fail.error, fail.error
    assert "JPEG" in fail.error.upper()
