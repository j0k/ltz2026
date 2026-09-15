# -*- coding: utf-8 -*-
"""Стилизованные подписи атласа: выноски данными из atlas.render, атлас без текста, компонент на главной."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dxaqc import atlas, pipeline
from dxaqc.io import collect

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "Для теста"
needs_data = pytest.mark.skipif(not TEST_DIR.exists(), reason="нет тестовых данных организатора")
HEX = re.compile(r"^#[0-9a-f]{6}$")


@needs_data
def test_render_exports_callouts_inside_the_picture():
    images, _, _ = collect(str(TEST_DIR))
    for img in images:
        res, art = pipeline.analyze_image(img.pixels)
        c = art["callouts"]
        W, H = c["size"]
        assert (W, H) == art["atlas"].size and list(art["image_box"]) == c["image_box"][:2]
        assert c["items"] and c["legend"] and c["title"] and c["marks"]
        for it in c["items"]:
            for x, y in (it["anchor"], it["knee"], it["end"]):
                assert 0 <= x <= W and 0 <= y <= H, it
            assert it["align"] in ("left", "right") and HEX.match(it["color"]) and it["label"]
            # плашка стоит со своей стороны от зоны: левая колонка левее точки на снимке, правая — правее
            assert (it["end"][0] < it["anchor"][0]) if it["align"] == "left" else (it["end"][0] > it["anchor"][0]), it
        labels = [it["label"] for it in c["items"]]
        if res["region"] == "lumbar_spine":
            assert "L3" in labels and any(l.startswith("ось столба") for l in labels)
        else:
            assert "большой вертел" in labels


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get(f"/api/runs/{rid}/progress").json()["state"] in ("done", "error", "cancelled"):
            return client.get(f"/api/runs/{rid}").json()
        time.sleep(0.3)
    raise AssertionError("прогон не завершился")


@needs_data
def test_clean_atlas_route_and_component_on_home(client):
    runs = Path(os.environ["DXAQC_DATA"]) / "runs"
    rid = client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    data = _wait(client, rid)
    row = next(r for r in data["rows"] if r["anatomical_region"] == "lumbar_spine")
    c = row["callouts"]
    clean = client.get(f"/runs/{rid}/images/{row['key']}/clean.png")
    assert clean.status_code == 200 and clean.headers["content-type"] == "image/png"
    im = np.asarray(Image.open(io.BytesIO(clean.content)).convert("RGB"))
    assert (im.shape[1], im.shape[0]) == tuple(c["size"])
    x0, y0, bw, bh = c["image_box"]
    assert (im[:, :x0 - 1] == atlas.BG).all() and (im[:y0 - 1] == atlas.BG).all(), "в полях нет впечатанного текста и выносок"
    overlay = np.asarray(Image.open(io.BytesIO(client.get(f"/runs/{rid}/files/{row['overlay_png']}").content)).convert("RGB"))
    assert not (overlay[:, :x0 - 1] == atlas.BG).all(), "в обычном атласе подписи в поле есть"
    assert client.get(f"/runs/{rid}/images/nope/clean.png").status_code == 404
    assert '"callouts"' not in client.get(f"/runs/{rid}").text

    css, js = client.get("/static/atlas-callouts.css"), client.get("/static/atlas-callouts.js")
    assert css.status_code == 200 and ".acall-chip" in css.text and js.status_code == 200 and "AtlasCallouts" in js.text

    example = runs / "example"
    had = example.exists()
    if not had:   # в тестах пример не засевается: главная берёт снимок из прогона примера
        shutil.copytree(runs / rid, example)
    try:
        home = client.get("/").text
        assert 'class="hero"' in home and "data-atlas-callouts" in home and "/static/atlas-callouts.js" in home
        assert re.search(r'/runs/example/images/[0-9a-f]+/clean\.png', home) and 'data-title="off"' in home
        payload = json.loads(re.search(r'<script type="application/json" class="acall-data">(.*?)</script>', home, re.S).group(1))
        assert payload["items"] and payload["size"] == c["size"]
        assert 'class="hero"' not in client.get("/", params={"design": "classic"}).text
    finally:
        if not had:
            shutil.rmtree(example, ignore_errors=True)
