# -*- coding: utf-8 -*-
"""Сменяющиеся кадры на главной: выбор примеров по областям, стилизация, маршрут кадра с кэшем, карусель в обеих главных."""
from __future__ import annotations

import io
import os
import re
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dxaqc.web import showcase

ROOT = Path(__file__).resolve().parents[1]
needs_data = pytest.mark.skipif(not (ROOT / "data" / "Для теста").exists(), reason="нет тестовых данных организатора")


def _row(key, region, q=None, ok=True):
    return dict(key=key, anatomical_region=region, quality_class=q, original_png=f"{key}_original.png",
                processing_status="Success" if ok else "Failure")


def test_pick_rotates_regions_prefers_good_and_skips_duplicates():
    example = dict(rows=[_row("s1", "lumbar_spine", 1), _row("s2", "lumbar_spine", 0), _row("hr", "hip_right"),
                         _row("bad", "hip_left", ok=False), _row("un", "unknown")])
    train = dict(rows=[_row("s2", "lumbar_spine", 0), _row("hl", "hip_left"), _row("s3", "lumbar_spine", 0)])
    frames = showcase.pick([("example", example), ("run1", train), ("none", None)])
    assert [f["key"] for f in frames] == ["s2", "hr", "hl", "s3", "s1"]
    assert frames[0]["run_id"] == "example" and frames[2]["run_id"] == "run1"
    assert all(f["region_ru"] and "DICOM" in f["note"] for f in frames)
    assert len(showcase.pick([("r", dict(rows=[_row(f"k{i}", "lumbar_spine", 0) for i in range(20)]))])) == showcase.MAX_FRAMES


def test_stylize_gives_blue_square(tmp_path):
    src = tmp_path / "x.png"
    g = np.tile(np.linspace(0, 255, 300, dtype=np.uint8), (290, 1))
    Image.fromarray(g).convert("RGB").resize((600, 580)).save(src)
    im = showcase.stylize(str(src))
    a = np.asarray(im, float)
    assert im.size == (showcase.SIZE, showcase.SIZE)
    assert a[..., 2].mean() > a[..., 0].mean() + 10, "дуотон уводит в синий"


def _wait(client, rid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get(f"/api/runs/{rid}/progress").json()["state"] in ("done", "error", "cancelled"):
            return
        time.sleep(0.3)
    raise AssertionError("прогон не завершился")


@needs_data
def test_home_carousel_and_frames(client):
    runs = Path(os.environ["DXAQC_DATA"]) / "runs"
    example = runs / "example"
    had_example = example.exists()
    if not had_example:   # в тестах пример не засевается: делаем его из прогона тестового фрагмента
        rid = client.post("/runs/dataset", data={"dataset": "test", "mode": "all"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
        _wait(client, rid)
        shutil.copytree(runs / rid, example)
    try:
        home = client.get("/", params={"design": "classic"}).text
        srcs = re.findall(r'src="(/showcase/example/[0-9a-f]+\.jpg)"', home)
        assert 'id="shots"' in home and len(srcs) == 3 and "можно загружать" in home
        assert home.count('role="tab"') == 3 and "Обычный рентген, КТ, JPG и PNG" in home
        r = client.get(srcs[0])
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        assert Image.open(io.BytesIO(r.content)).size == (560, 560)
        key = srcs[0].rsplit("/", 1)[1][:-4]
        assert (Path(os.environ["DXAQC_DATA"]) / "showcase" / f"v{showcase.VERSION}" / f"example_{key}.jpg").exists()
        assert client.get(srcs[0]).status_code == 200

        bio = client.get("/v1").text
        assert "shots shots--compact" in bio and len(re.findall(r'src="/showcase/example/', bio)) == 3

        for bad in ("/showcase/example/nope.jpg", "/showcase/..%2Fexample/abc.jpg", "/showcase/missing/abc.jpg"):
            assert client.get(bad).status_code == 404, bad
    finally:
        if not had_example:
            shutil.rmtree(example, ignore_errors=True)
