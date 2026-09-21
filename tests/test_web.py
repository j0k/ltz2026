# -*- coding: utf-8 -*-
"""Тесты веб-стенда: главная, формы, прогоны до готовности, файлы, карточка, API и ошибки.

    .venv/bin/python -m pytest tests -q

Сервер поднимается в процессе через TestClient на временном каталоге данных. Тесты с данными организатора берут
«Для теста.zip» из корня проекта и распакованные наборы из data/; если их нет, такие тесты пропускаются.
Прогон всего обучающего набора идёт около минуты.
"""
from __future__ import annotations

import csv
import importlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED_ZIP = ROOT / "Для теста.zip"
TEST_DIR = ROOT / "data" / "Для теста"
TRAIN_DIR = ROOT / "data" / "train" / "Исследования"
LABELS = ROOT / "data" / "labels_clean.csv"
HAVE_DATA = all(p.exists() for p in (SEED_ZIP, TEST_DIR, TRAIN_DIR, LABELS))
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="нет данных организатора в data/ и «Для теста.zip»")
COLUMNS = ["path_to_study", "study_uid", "image_uid", "anatomical_region", "quality_class", "violation_type",
           "processing_status", "time_of_processing"]


def run_id_from(resp) -> str:
    assert resp.status_code == 303, resp.text[:300]
    loc = resp.headers["location"]
    assert re.fullmatch(r"/runs/[0-9]{8}-[0-9]{6}-[0-9a-f]{6}", loc), loc
    return loc.rsplit("/", 1)[1]


def wait_done(client, run_id: str, timeout: float = 180) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        data = client.get(f"/api/runs/{run_id}").json()
        if data["state"] in ("done", "error"):
            return data
        time.sleep(0.5)
    pytest.fail(f"прогон {run_id} не завершился за {timeout} с")


def embedded_manifest(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="man-data">(.*?)</script>', html, re.S)
    assert m, "на странице прогона нет встроенного manifest"
    return json.loads(m.group(1))


# ------------------------------------------------------------------ главная

def test_index_has_all_blocks(client):
    r = client.get("/v1")
    assert r.status_code == 200
    html = r.text
    for block in ("upload", "about", "runs", "accuracy"):
        assert f'id="{block}"' in html
    assert re.search(r"<h1[^>]*>Контроль качества", html)
    assert re.search(r'<form class="upload" action="/runs" method="post" enctype="multipart/form-data">', html)
    assert re.search(r'<input id="files" type="file" name="files" multiple required', html)
    assert '<label for="files"' in html
    assert 'href="/docs"' in html and "/trac/" in html
    assert "Что умеет версия" in html and "0.45" in html


def test_index_without_runs_says_so(client):
    if client.get("/api/health").status_code == 200 and "Прогонов пока нет" not in client.get("/v1").text:
        pytest.skip("прогоны уже созданы другими тестами")
    assert "Прогонов пока нет" in client.get("/v1").text


@needs_data
def test_index_dataset_forms_have_all_modes(client):
    html = client.get("/v1").text
    assert 'id="check"' in html
    forms = re.findall(r'<form[^>]*action="/runs/dataset"[^>]*>(.*?)</form>', html, re.S)
    by_id = {re.search(r'name="dataset" value="([^"]+)"', f).group(1): f for f in forms}
    assert set(by_id) == {"test", "train"}
    assert 'name="mode" value="all"' in by_id["test"] and 'type="radio"' not in by_id["test"]
    train = by_id["train"]
    for mode in ("sample", "all", "study"):
        assert f'value="{mode}"' in train
    assert re.findall(r'<option value="(\d+)"', train) == ["5", "10", "25", "50"]
    assert '<option value="10" selected>' in train
    assert len(re.findall(r'<option value="[^"]{20,}">', train)) == 100, "в списке одного исследования должны быть все 100"


# ------------------------------------------------------------------ API и ошибки

def test_health_and_datasets_api(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and re.fullmatch(r"\d+\.\d+\.\d+", h["version"])
    ds = client.get("/api/datasets").json()
    assert isinstance(ds, list)
    if HAVE_DATA:
        assert {d["id"] for d in ds} == {"test", "train"}
        assert len(client.get("/api/datasets/train/studies").json()) == 100
    assert client.get("/api/datasets/nope/studies").status_code == 404


@pytest.mark.parametrize("path, mime", [
    ("/favicon.ico", "image/x-icon"),
    ("/favicon.svg", "image/svg+xml"),
    ("/apple-touch-icon.png", "image/png"),
])
def test_favicons_are_served_and_linked(client, path, mime):
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith(mime) and len(r.content) > 100
    assert f'href="{path}"' in client.get("/v1").text


def test_json_and_csv_declare_utf8(client):
    """Без charset Safari на iPhone показывает русский текст кракозябрами."""
    for path in ("/api/health", "/api/datasets", "/api/runs/nope", "/api/control/queue"):
        assert client.get(path).headers["content-type"] == "application/json; charset=utf-8", path


@needs_data
def test_run_json_button_is_readable_utf8(client):
    rid = run_id_from(client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False))
    assert wait_done(client, rid)["state"] == "done"
    assert f'href="/api/runs/{rid}?pretty=true"' in client.get(f"/runs/{rid}").text
    r = client.get(f"/api/runs/{rid}", params={"pretty": "true"})
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert "\n  " in r.text and "Область:" in r.text, "с отступами и кириллицей как есть, без \\u-экранирования"
    assert json.loads(r.content.decode("utf-8"))["run_id"] == rid
    for name, ctype in (("manifest.json", "application/json; charset=utf-8"), ("results.csv", "text/csv; charset=utf-8")):
        assert client.get(f"/runs/{rid}/files/{name}").headers["content-type"] == ctype, name


def test_upload_without_files_is_rejected(client):
    assert client.post("/runs", follow_redirects=False).status_code == 422


def test_unknown_dataset_is_rejected(client):
    assert client.post("/runs/dataset", data={"dataset": "nope", "mode": "all"}, follow_redirects=False).status_code == 400


@pytest.mark.parametrize("path", [
    "/runs/nope",
    "/runs/nope/images/abc",
    "/runs/nope/files/results.csv",
    "/runs/..%2F..%2Fetc/files/passwd",
    "/api/runs/nope",
])
def test_missing_things_are_404(client, path):
    assert client.get(path).status_code == 404


def test_voice_endpoints_follow_installed_models(client):
    st = client.get("/api/voice").json()
    assert set(st) == {"tts", "stt"}
    assert client.get("/api/tts", params={"text": ""}).status_code in (400, 503)
    tts = client.get("/api/tts", params={"text": "проверка"})
    assert tts.status_code == (200 if st["tts"] else 503)
    stt = client.post("/api/stt", files={"file": ("q.webm", b"", "audio/webm")})
    assert stt.status_code == (400 if st["stt"] else 503)


def test_garbage_upload_does_not_crash(client):
    rid = run_id_from(client.post("/runs", files={"files": ("note.txt", b"not a dicom", "text/plain")}, follow_redirects=False))
    data = wait_done(client, rid)
    assert data["state"] == "done", data.get("error")
    assert data["summary"]["images"] == 0


# ------------------------------------------------------------------ прогоны с данными

@needs_data
def test_upload_zip_full_flow(client):
    with open(SEED_ZIP, "rb") as f:
        rid = run_id_from(client.post("/runs", files={"files": ("Для теста.zip", f, "application/zip")}, follow_redirects=False))
    data = wait_done(client, rid)
    assert data["state"] == "done", data.get("error")
    assert data["summary"]["images"] == 3 and data["summary"]["failures"] == 0

    page = client.get(f"/runs/{rid}")
    assert page.status_code == 200
    for marker in ('class="card tile" data-tile="bad"', 'id="box-grid"', 'id="results"'):
        assert marker in page.text
    man = embedded_manifest(page.text)
    assert all("regions" not in r for r in man["rows"]), "пояснения зон не должны попадать в страницу прогона"

    table = client.get(f"/runs/{rid}/files/results.csv")
    assert table.status_code == 200
    rows = list(csv.reader(io.StringIO(table.content.decode("utf-8-sig"))))
    assert rows[0] == COLUMNS and len(rows) == 4
    assert client.get(f"/runs/{rid}/files/results.xlsx").status_code == 200
    assert zipfile.ZipFile(io.BytesIO(client.get(f"/runs/{rid}/files/overlays.zip").content)).namelist()

    row = next(r for r in data["rows"] if r["anatomical_region"] == "lumbar_spine")
    card = client.get(f"/runs/{rid}/images/{row['key']}")
    assert card.status_code == 200 and 'id="atlasOv"' in card.text
    assert 'id="vWave"' in card.text and 'id="vwCanvas"' in card.text, "панель волны голосового вопроса"
    hit = client.get(f"/runs/{rid}/files/{row['hit_png']}")
    assert hit.status_code == 200 and hit.headers["content-type"] == "image/png"

    for bad in (f"/runs/{rid}/files/..%2Fstatus.json", f"/runs/{rid}/files/.hidden", f"/runs/{rid}/images/nope"):
        assert client.get(bad).status_code == 404

    index = client.get("/v1").text
    item = re.search(rf'<tr>\s*<td><a href="/runs/{rid}">.*?</tr>', index, re.S)
    assert item, "прогон должен появиться в таблице на главной"
    row = item.group(0)
    assert re.search(r"\d\d\.\d\d \d\d:\d\d · ", row), "у прогона должно быть время"
    assert "готово" in row and "<td>3</td>" in row
    assert f'href="/runs/{rid}/files/results.csv"' in row


@needs_data
def test_api_batch_waits_for_result(client):
    with open(SEED_ZIP, "rb") as f:
        r = client.post("/api/batch", params={"wait": "true"}, files={"files": ("Для теста.zip", f, "application/zip")})
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "done" and len(data["rows"]) == 3
    assert data["results_csv"].endswith("/results.csv") and data["page"].startswith("/runs/")


@needs_data
@pytest.mark.parametrize("form, images, studies", [
    ({"dataset": "test", "mode": "all"}, 3, 2),
    ({"dataset": "train", "mode": "sample", "n": "5"}, None, 5),
])
def test_dataset_runs(client, form, images, studies):
    rid = run_id_from(client.post("/runs/dataset", data=form, follow_redirects=False))
    data = wait_done(client, rid)
    assert data["state"] == "done", data.get("error")
    if images is not None:
        assert data["summary"]["images"] == images
    assert data["summary"]["studies"] == studies
    if form["dataset"] == "train":
        man = embedded_manifest(client.get(f"/runs/{rid}").text)
        assert man["has_labels"] and man["evaluation"]["spine_studies"] <= 5
        assert 'id="ci-grid"' in client.get(f"/runs/{rid}").text


@needs_data
def test_dataset_single_study_and_bad_study(client):
    study = client.get("/api/datasets/train/studies").json()[0]
    study = study["id"] if isinstance(study, dict) else study
    rid = run_id_from(client.post("/runs/dataset", data={"dataset": "train", "mode": "study", "study": study}, follow_redirects=False))
    data = wait_done(client, rid)
    assert data["state"] == "done" and data["summary"]["studies"] == 1
    bad = run_id_from(client.post("/runs/dataset", data={"dataset": "train", "mode": "study", "study": "../../etc"}, follow_redirects=False))
    assert client.get(f"/api/runs/{bad}").json()["state"] == "error"


@needs_data
def test_full_train_run_is_linked_from_index(client):
    rid = run_id_from(client.post("/runs/dataset", data={"dataset": "train", "mode": "all"}, follow_redirects=False))
    data = wait_done(client, rid, timeout=400)
    assert data["state"] == "done" and data["summary"]["studies"] == 100 and data["summary"]["images"] == 252
    man = embedded_manifest(client.get(f"/runs/{rid}").text)
    assert round(man["evaluation"]["spine_overall"]["f1"], 2) == 0.45
    assert f'<a href="/runs/{rid}">в прогоне обучающего набора</a>' in client.get("/v1").text
