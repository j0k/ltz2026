"""Главная: готовые примеры — по одному исследованию на тип нарушения, запуск ведёт на дашборд."""
import importlib


def P():
    return importlib.import_module("dxaqc.web.presets")


def row(study, reg, bad, types, viol, key):
    return dict(study_key=study, anatomical_region=reg, key=key, thumb_png=f"{key}_thumb.png", quality_class=int(bool(viol)),
                violation_list=viol, expert=dict(bad=bad, types=types, comment=""))


def test_build_prefers_studies_where_service_agrees():
    rows = [row("s1", "lumbar_spine", 1, ["artifact"], [], "a1"),                  # эксперты — предмет, сервис пропустил
            row("s2", "lumbar_spine", 1, ["artifact"], ["artifact"], "a2"),       # сервис нашёл — эту и берём
            row("s3", "lumbar_spine", 0, [], [], "o1"), row("s3", "hip_left", 0, [], [], "o2"), row("s3", "hip_right", 0, [], [], "o3")]
    items = {p["key"]: p for p in P().build("r1", dict(rows=rows))}
    assert items["artifact"]["study"] == "s2" and items["artifact"]["thumb"] == "/runs/r1/files/a2_thumb.png"
    assert items["ok"]["study"] == "s3" and items["ok"]["expert"] == "эксперты: годен"
    assert "coverage" not in items, "нет примера — нет и заготовки"
    assert P().build(None, None) == []


def test_home_shows_quiet_preset_picker(client):
    html = client.get("/").text
    # без прогона обучающего набора заготовок может не быть — тогда и кнопки нет; с прогоном — тихая кнопка и диалог
    if 'id="kPresetBtn"' in html:
        assert '<dialog class="k-dlg" id="kPresets"' in html and 'action="/presets/run"' in html
    assert client.post("/presets/run", data={"key": "нет-такого"}).status_code == 404
