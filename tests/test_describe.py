"""Отклонённые картинки: что на них и что делать (вместо тупика), принудительный разбор обзорного таза."""
import os

import numpy as np
from PIL import Image

from dxaqc import pipeline
from dxaqc.describe import describe_picture
from dxaqc.desktop import synth


def _pelvis(path):
    # синтетический обзорный таз: симметрично, два бедра — фантом бедра и его зеркало
    h = synth.hip("left")
    Image.fromarray(np.hstack([h[:, ::-1], h])).resize((330, 300)).save(path)   # обзорный таз почти квадратный


def test_describe_kinds(tmp_path):
    _pelvis(tmp_path / "taz.jpg")
    Image.fromarray(synth.spine()).save(tmp_path / "spine.png")
    Image.fromarray(synth.hip("left")).save(tmp_path / "hip.png")
    Image.fromarray((np.random.default_rng(1).random((200, 300, 3)) * 255).astype("uint8")).save(tmp_path / "photo.png")
    kinds = {n: describe_picture(str(tmp_path / n))["kind"] for n in ("taz.jpg", "spine.png", "hip.png", "photo.png")}
    assert kinds == {"taz.jpg": "pelvis", "spine.png": "spine", "hip.png": "hip", "photo.png": "photo"}
    d = describe_picture(str(tmp_path / "taz.jpg"), str(tmp_path / "prev.png"))
    assert "таз" in d["title"] and d["todo"] and d["dxa"] and os.path.isfile(tmp_path / "prev.png")


def test_rejected_picture_gets_description_and_forced_pelvis_splits(tmp_path):
    src = tmp_path / "in"; src.mkdir()
    _pelvis(src / "taz.jpg")
    m = pipeline.run_batch(str(src), str(tmp_path / "out"))
    row = m["rows"][0]
    assert row["processing_status"] == "Failure" and row["described"]["kind"] == "pelvis" and row["preview_png"]
    assert os.path.isfile(tmp_path / "out" / row["preview_png"])
    f = pipeline.run_batch(str(src), str(tmp_path / "out2"), force=True)
    regions = sorted(r["anatomical_region"] for r in f["rows"])
    assert regions == ["hip_left", "hip_right"], "обзорный таз — два бедра"
    assert all("разрезан пополам" in r["explanations"][0] and "не гарантирован" in r["explanations"][0] for r in f["rows"])


def test_dashboard_shows_rejected_card(client):
    import json, sys, time
    app = sys.modules["dxaqc.web.app"]
    rid = "20260928-090000-rej001"
    out = os.path.join(app.RUNS, rid, "out"); os.makedirs(out, exist_ok=True)
    json.dump(dict(state="done", title="Загрузка", created=time.time()), open(os.path.join(app.RUNS, rid, "status.json"), "w"))
    row = dict(path_to_study="taz.jpg", processing_status="Failure", forceable=True, explanations=["файл JPG — это картинка"],
               preview_png="reject000_preview.png", described=dict(kind="pelvis", title="обычный рентгеновский снимок таза",
               facts=["оба сустава в кадре"], dxa=["DXA — отдельное исследование"], todo=["выгрузите DICOM"]))
    json.dump(dict(summary=dict(images=0, failures=1), rows=[row]), open(os.path.join(out, "manifest.json"), "w"))
    html = client.get(f"/check/{rid}").text
    assert "Что на картинке:" in html and "обычный рентгеновский снимок таза" in html and "Что можно сделать" in html
    assert "reject000_preview.png" in html and "Запросить разбор картинки" in html and "/?presets=1" in html
