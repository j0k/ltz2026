# -*- coding: utf-8 -*-
"""Новый интерфейс: главная из двух действий, страница результата, прежний интерфейс по /v1."""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "Для теста"
needs_data = pytest.mark.skipif(not TEST_DIR.exists(), reason="нет данных организатора")


def test_home_is_just_upload_and_3d(client):
    html = client.get("/").text
    assert 'id="v2Upload"' in html and 'action="/runs"' in html and 'name="ui" value="v2"' in html
    assert "window.addEventListener('drop'" in html and "window.addEventListener('dragover'" in html, "файл, брошенный мимо рамки, не скачивается браузером"
    assert 'id="bone3d"' in html and "/static/bone3d.js" in html and "/static/bone/poster.jpg" in html, "справа 3D-модель таза"
    for extra in ('href="/login"', 'href="/register"', 'href="/v1"', 'href="/tz/"', 'id="cookieBar"', "<footer>", "Подробнее"):
        assert extra not in html, f"на главной только загрузка: лишнее {extra}"
    assert 'Команда «<span class="neon">Квантовый Скачок</span>»' in html and 'class="qf-art"' in html, "внизу — команда и квантовый скачок (29.09, Юрий)"
    old = client.get("/start").text
    assert "Демо" in old and 'href="/v1"' in old and 'href="/tz/"' in old, "прежняя главная — по /start"
    assert 'href="/control">Пульт' not in old


def test_v1_keeps_everything(client):
    for path in ("/v1", "/v1/"):
        r = client.get(path)
        assert r.status_code == 200 and 'href="/control">Пульт' in r.text and 'class="hero"' in r.text, path
    for src, dst in (("/v1/gallery", "/gallery"), ("/v1/tz/data.html?x=1", "/tz/data.html?x=1"), ("/v1/runs/example", "/runs/example")):
        r = client.get(src, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == dst, src
    assert 'id="upload"' in client.get("/", params={"design": "classic"}).text, "старые ссылки ?design= открывают v1"
    assert 'href="/v1">Прогоны' in client.get("/gallery").text, "«Прогоны» в меню ведут в v1"
    assert client.get("/check/нет-такой").status_code == 404


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get(f"/api/runs/{rid}/progress").json()["state"] in ("done", "error", "cancelled"):
            return
        time.sleep(0.3)
    raise AssertionError("проверка не завершилась")


@needs_data
def test_upload_goes_to_new_result_page(client):
    spine = next(TEST_DIR.glob("*ПОП*.dcm"))
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("L", (64, 48), 128).save(buf, "JPEG")      # картинка вместо DICOM — отказ с причиной
    files = [("files", (spine.name, spine.read_bytes(), "application/dicom")), ("files", ("photo.jpg", buf.getvalue(), "image/jpeg"))]
    r = client.post("/runs", files=files, data={"ui": "v2"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/check/")
    rid = r.headers["location"].rsplit("/", 1)[1]
    running = client.get(f"/check/{rid}").text
    _wait(client, rid)
    html = client.get(f"/check/{rid}").text
    assert html.count('<article class="d-img') == 1 and "Поясничный отдел" in html
    assert "годен" in html or "нарушение" in html
    assert 'class="d-kpis"' in html and 'class="d-checks"' in html and "Таблица результатов" in html, "дашборд по ТЗ"
    assert 'id="regMap"' in html and 'td data-region="lumbar_spine"' in html, "наведение на anatomical_region показывает схему тела (29.09, Юрий)"
    for f in ('data-f="all"', 'data-f="ok"', 'data-f="bad"', 'id="dFilterBar"'):
        assert f in html, f"плитки фильтруют снимки (29.09, Юрий): {f}"
    assert 'data-k="' in html and '<article class="d-img' in html
    assert 'class="d-card d-rej"' in html and "Что на картинке:" in html and "photo.jpg" in html and "не DICOM" in html.replace("а не DICOM", "не DICOM"), "отказ с причиной"
    for f in ("results.csv", "results.xlsx", "overlays.zip"):
        assert f'/runs/{rid}/files/{f}' in html, f
    assert f'/runs/{rid}/images/' in html and 'id="cookieBar"' not in html and 'href="/login"' not in html
    assert "v2Wait" in running or "d-img" in running

    legacy = client.post("/runs", files=[("files", (spine.name, spine.read_bytes(), "application/dicom"))], follow_redirects=False)
    assert legacy.headers["location"].startswith("/runs/"), "прежняя загрузка ведёт на страницу прогона"


def test_demo_from_example_run(client):
    app = sys.modules["dxaqc.web.app"]
    ex = os.path.join(app.RUNS, app.EXAMPLE_ID)
    existed = os.path.isdir(ex)
    if not existed:
        os.makedirs(os.path.join(ex, "out"))
        with open(os.path.join(ex, "status.json"), "w") as f:
            json.dump(dict(state="done", title="Пример", created=time.time()), f)
        rows = [dict(key="demo01", thumb_png="demo01_thumb.png", overlay_png="demo01_overlay.png", anatomical_region="lumbar_spine",
                     quality_class=0, violation_list=[], processing_status="Success", explanations=["Ось в пределах допуска."],
                     path_to_study="a/b.dcm")]
        with open(os.path.join(ex, "out", "manifest.json"), "w") as f:
            json.dump(dict(summary=dict(images=1, good=1, bad=0, not_evaluated=0, studies=1), rows=rows), f)
    try:
        home = client.get("/start").text
        assert f'href="/check/{app.EXAMPLE_ID}"' in home and f'/runs/{app.EXAMPLE_ID}/files/' in home
        demo = client.get(f"/check/{app.EXAMPLE_ID}").text
        assert "Демо: пример организатора" in demo and '<article class="d-img' in demo
    finally:
        if not existed:
            shutil.rmtree(ex, ignore_errors=True)
