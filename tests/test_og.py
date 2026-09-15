# -*- coding: utf-8 -*-
"""Превью ссылок: OpenGraph-теги с абсолютными адресами на страницах и картинки 1200×630 для снимка, прогона и стенда."""
from __future__ import annotations

import html
import io
import os
import re
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
needs_data = pytest.mark.skipif(not (ROOT / "data" / "Для теста").exists(), reason="нет тестовых данных организатора")


def og_version() -> int:
    """Версия оформления превью: имя кэша меняется вместе с ней."""
    return sys.modules["dxaqc.web.og"].VERSION


def meta(page: str) -> dict:
    return {k: html.unescape(v) for k, v in re.findall(r'<meta (?:property|name)="([^"]+)" content="([^"]*)"', page)}


def image(client, url: str) -> Image.Image:
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg", (url, r.status_code)
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (1200, 630) and len(r.content) < 400_000
    return im


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get(f"/api/runs/{rid}/progress").json()["state"] in ("done", "error", "cancelled"):
            return
        time.sleep(0.3)
    raise AssertionError("прогон не завершился")


@needs_data
def test_open_graph_for_card_run_and_site(client):
    public = sys.modules["dxaqc.web.app"].PUBLIC_URL
    assert public.startswith("http")
    rid = client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    _wait(client, rid)
    row = next(r for r in client.get(f"/api/runs/{rid}").json()["rows"] if r["anatomical_region"] == "lumbar_spine")
    key = row["key"]

    m = meta(client.get(f"/runs/{rid}/images/{key}").text)
    assert m["og:title"].startswith("Поясничный отдел: ") and "DXA QC" in m["og:title"]
    assert m["og:image"] == f"{public}/runs/{rid}/images/{key}/og.jpg"
    assert m["og:url"] == f"{public}/runs/{rid}/images/{key}"
    assert m["twitter:card"] == "summary_large_image" and m["og:locale"] == "ru_RU"
    assert m["og:description"] and os.path.basename(row["path_to_study"]) in m["og:description"]
    im = image(client, f"/runs/{rid}/images/{key}/og.jpg")
    assert len(set(im.resize((40, 21)).getdata())) > 30, "на картинке атлас, а не пустой фон"
    assert (Path(os.environ["DXAQC_DATA"]) / "runs" / rid / "out" / f"og_{key}_v{og_version()}.jpg").exists(), "картинка готового прогона кэшируется"
    image(client, f"/runs/{rid}/images/{key}/og.jpg")

    rm = meta(client.get(f"/runs/{rid}").text)
    assert rm["og:image"] == f"{public}/runs/{rid}/og.jpg" and "снимков" in rm["og:description"]
    image(client, f"/runs/{rid}/og.jpg")

    home = meta(client.get("/").text)
    assert home["og:image"] == f"{public}/og.jpg" and home["og:title"].endswith("· DXA QC")
    image(client, "/og.jpg")
    assert meta(client.get("/tz/").text)["og:title"] == "Документы задачи · DXA QC"

    for bad in (f"/runs/{rid}/images/nope/og.jpg", "/runs/nope/og.jpg", f"/runs/{rid}/images/..%2F/og.jpg"):
        assert client.get(bad).status_code == 404, bad


def test_page_previews_are_own_pictures(client):
    """У документов, пульта и вопросов своя картинка превью, а не общая картинка стенда."""
    public = sys.modules["dxaqc.web.app"].PUBLIC_URL
    site = client.get("/og.jpg").content
    seen = {}
    for key in ("tz", "mindmap", "mlmap", "control", "ask"):
        im = image(client, f"/og/{key}.jpg")
        assert len(set(im.resize((40, 21)).getdata())) > 20, f"{key}: картинка пустая"
        data = client.get(f"/og/{key}.jpg").content
        assert data != site, f"{key}: отдаётся общая картинка стенда"
        assert data not in seen, f"{key}: совпадает с {seen.get(data)}"
        seen[data] = key
    assert client.get("/og/unknown.jpg").status_code == 404

    for path, img in {"/tz/": "/og/tz.jpg", "/tz/mindmap.html": "/og/mindmap.jpg",
                      "/tz/ml-map.html": "/og/mlmap.jpg", "/control": "/og/control.jpg"}.items():
        m = meta(client.get(path).text)
        assert m["og:image"] == public + img, path
        assert len(m["og:description"]) > 30 and m["og:title"].endswith("· DXA QC"), path
