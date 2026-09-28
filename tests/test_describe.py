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


def _lateral_spine():
    """Синтетический позвоночник сбоку, как на сагиттальном срезе КТ: симметричный контур тела, по центру тела
    позвонков, асимметрия только рядом со столбом — спереди тёмная брюшная полость, сзади канал и задняя дуга."""
    yy, xx = np.mgrid[0:420, 0:400]
    a = np.where(((xx - 200) / 190) ** 2 + ((yy - 210) / 260) ** 2 < 1, 70, 12).astype(np.uint8)
    for i in range(7):
        y = 15 + i * 58
        a[y:y + 46, 160:240] = 200                           # тела позвонков
        a[y + 4:y + 40, 250:290] = 215                       # дуга и отростки сразу за каналом
    a[:, 110:160] = 35                                       # брюшная полость спереди
    a[:, 240:250] = 40                                       # позвоночный канал
    return a


def test_lateral_spine_is_told_apart(tmp_path):
    Image.fromarray(_lateral_spine()).save(tmp_path / "lat.png")
    Image.fromarray(synth.spine()).save(tmp_path / "ap.png")
    lat, ap = describe_picture(str(tmp_path / "lat.png")), describe_picture(str(tmp_path / "ap.png"))
    assert lat["kind"] == "spine_lateral" and "сбоку" in lat["title"], lat["title"]
    assert ap["kind"] == "spine" and "прямой проекции" in ap["title"]
    assert any("прямой проекции" in t for t in lat["dxa"])


def test_black_side_bars_listed(tmp_path):
    a = np.zeros((300, 400), np.uint8)
    a[:, 80:320] = synth.spine()[:300, :240] if synth.spine().shape[1] >= 240 else 120
    Image.fromarray(a).save(tmp_path / "bars.png")
    assert any("чёрные поля" in e for e in describe_picture(str(tmp_path / "bars.png"))["elements"])


def test_text_on_picture_is_read_and_classified(tmp_path):
    import pytest
    from PIL import ImageDraw, ImageFont
    from dxaqc import ocr
    if not ocr.available():
        pytest.skip("нет модели OCR (DXAQC_OCR_MODEL)")
    img = Image.fromarray(_lateral_spine()).convert("RGB").resize((800, 840))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    d.text((20, 10), "Остеопороз позвоночника", font=font, fill="white")
    d.text((560, 300), "Spin: -83", font=font, fill="white")
    d.text((400, 780), "rentgen-example.ru", font=font, fill="white")
    img.save(tmp_path / "ct.jpg", quality=95)
    r = describe_picture(str(tmp_path / "ct.jpg"))
    joined = " | ".join(r["elements"])
    assert "заголовок" in joined and "Остеопороз" in joined, joined
    assert "служебная надпись" in joined and "Spin" in joined, joined
    assert "водяной знак" in joined and "example.ru" in joined, joined
    assert r["modality"] == "КТ" and r["title"].startswith("КТ позвоночника, вид сбоку"), r["title"]
