# -*- coding: utf-8 -*-
"""Слои атласа: наложение слоёв совпадает с файлом атласа, подписи и зоны лежат в своих слоях,
пайплайн сохраняет слои, карточка показывает переключатели и лупу, старые прогоны без слоёв открываются."""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dxaqc import atlas, pipeline, render
from dxaqc.io import collect

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "Для теста"
SEED_ZIP = ROOT / "Для теста.zip"
needs_data = pytest.mark.skipif(not (TEST_DIR.exists() and SEED_ZIP.exists()), reason="нет тестовых данных организатора")


@needs_data
def test_layers_compose_into_atlas():
    images, _, _ = collect(str(TEST_DIR))
    assert images
    regions = set()
    for img in images:
        res, art = pipeline.analyze_image(img.pixels)
        assert art, res["region"]
        regions.add(res["region"])
        L, (x, y) = art["layers"], art["image_box"]
        W, H = art["atlas"].size
        assert {"frame", "zones", "axis", "labels"} <= set(L)
        assert all(im.size == (W, H) for im in L.values())

        base = render.original(img.pixels)
        comp = L["frame"].convert("RGBA")
        comp.paste(base.convert("RGBA"), (x, y))
        for name in atlas.LAYER_ORDER[2:]:
            if name in L:
                comp.alpha_composite(L[name])
        diff = np.abs(np.asarray(comp.convert("RGB"), int) - np.asarray(art["atlas"], int))
        assert diff.max() == 0, "страница собирает рисунок из original_png и слоёв — он должен совпасть с атласом"

        bw, bh = base.size
        zones = np.asarray(L["zones"])[..., 3]
        assert zones[y:y + bh, x:x + bw].any() and not zones[:y].any() and not zones[:, :x].any(), "зоны только на снимке"
        labels = np.asarray(L["labels"])[..., 3]
        assert labels[:, :x].any() or labels[:, x + bw:].any(), "выноски в полях рядом со снимком"
    assert "lumbar_spine" in regions


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        data = client.get(f"/api/runs/{rid}").json()
        if data.get("state") in ("done", "error"):
            return data
        time.sleep(0.5)
    raise AssertionError("прогон не завершился")


@needs_data
def test_pipeline_saves_layers_and_card_shows_controls(client):
    with open(SEED_ZIP, "rb") as f:
        r = client.post("/runs", files={"files": ("Для теста.zip", f, "application/zip")}, follow_redirects=False)
    rid = r.headers["location"].rsplit("/", 1)[1]
    data = _wait(client, rid)
    assert data["state"] == "done", data.get("error")

    row = next(x for x in data["rows"] if x["anatomical_region"] == "lumbar_spine")
    layers = {l["name"]: l for l in row["layers"]}
    assert {"frame", "image", "zones", "axis", "labels"} <= set(layers)
    assert layers["image"]["file"] == row["original_png"], "слой снимка не дублирует файл"
    overlay = client.get(f"/runs/{rid}/files/{row['overlay_png']}")
    atlas_size = Image.open(io.BytesIO(overlay.content)).size
    for l in row["layers"]:
        got = client.get(f"/runs/{rid}/files/{l['file']}")
        assert got.status_code == 200 and got.headers["content-type"] == "image/png"
        if l["name"] != "image":
            assert Image.open(io.BytesIO(got.content)).size == atlas_size

    card = client.get(f"/runs/{rid}/images/{row['key']}").text
    for marker in ('data-layer="image"', 'data-layer="zones"', 'data-layer="axis"', 'data-layer="labels"',
                   'id="bLoupe"', 'id="loupe"', 'id="atlasCv"', 'data-zoom="6"'):
        assert marker in card, marker
    assert ('data-layer="artifacts"' in card) == ("artifacts" in layers)
    assert '_layer_frame.png' in card

    page = client.get(f"/runs/{rid}").text
    assert '_layer_' not in page, "список слоёв не нужен странице прогона"

    # старый прогон без слоёв: карточка открывается, лупа есть, переключателей слоёв нет
    man_path = Path(os.environ["DXAQC_DATA"]) / "runs" / rid / "out" / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    for x in man["rows"]:
        x.pop("layers", None)
    man_path.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    old = client.get(f"/runs/{rid}/images/{row['key']}")
    assert old.status_code == 200 and 'id="bLoupe"' in old.text and 'data-layer=' not in old.text
