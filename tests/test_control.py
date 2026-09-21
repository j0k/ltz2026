# -*- coding: utf-8 -*-
"""Тесты пульта анализа: параметры, анализ с порогами, перезапуск, отмена, удаление, правки снимков, пробный анализ, доступ."""
from __future__ import annotations

import csv
import io
import re
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "Для теста"
TRAIN_DIR = ROOT / "data" / "train" / "Исследования"
needs_data = pytest.mark.skipif(not (TEST_DIR.exists() and TRAIN_DIR.exists()), reason="нет данных организатора в data/")
PASSWORD = "correct-horse-1"


def mod(name):
    return sys.modules[name]


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


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


def admin_browser(browsers, login):
    A = mod("dxaqc.web.accounts")
    if not A.get_user_by_login(login):
        A.create_user(login, PASSWORD, role="admin", can_ask=True)
    c = browsers()
    assert c.post("/login", data={"login": login, "password": PASSWORD}, follow_redirects=False).status_code == 303
    return c


def user_browser(browsers, login):
    A = mod("dxaqc.web.accounts")
    if not A.get_user_by_login(login):
        A.create_user(login, PASSWORD)
    c = browsers()
    c.post("/login", data={"login": login, "password": PASSWORD}, follow_redirects=False)
    return c


def wait_state(c, rid, states=("done", "error", "cancelled"), timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get(f"/api/runs/{rid}").json()["state"]
        if st in states:
            return st
        time.sleep(0.2)
    pytest.fail(f"прогон {rid} не дошёл до {states}")


def start_dataset(c, **form):
    r = c.post("/runs/dataset", data=form, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"].rsplit("/", 1)[1]


def token(c):
    return csrf_of(c.get("/account").text)


def csv_rows(c, rid):
    return list(csv.reader(io.StringIO(c.get(f"/runs/{rid}/files/results.csv").content.decode("utf-8-sig"))))


# ------------------------------------------------------------------ параметры и анализ

def test_params_normalize_and_describe():
    sys.path.insert(0, str(ROOT))
    from dxaqc import params as P
    assert P.normalize(None) == P.DEFAULTS
    assert P.normalize({"axis_limit_deg": "4,5"})["axis_limit_deg"] == 4.5
    assert P.describe({"axis_limit_deg": 4, "artifact_min_pixels": "80"}) == "ось 4°, пикселей предмета 80px"
    assert P.describe({}) == "по умолчанию"
    for bad, msg in [({"axis_limit_deg": "много"}, "нужно число"), ({"axis_limit_deg": 99}, "от 1 до 15"),
                     ({"artifact_min_pixels": 10.5}, "целое")]:
        with pytest.raises(P.ParamError, match=msg):
            P.normalize(bad)


@needs_data
def test_thresholds_change_spine_verdict():
    from dxaqc import analyze
    from dxaqc.io import collect
    images, _, _ = collect(str(TEST_DIR))
    spine = next(i for i in images if i.pixels.shape[1] == 300)
    base = analyze.analyze(spine.pixels)
    assert base["region"] == "lumbar_spine" and "axis_tilt" not in base["violations"]
    assert base["limits"]["axis_limit_deg"] == 5.0
    strict = analyze.analyze(spine.pixels, {"axis_limit_deg": 1.0, "iliac_min_brightness": 60})
    assert {"axis_tilt", "coverage"} <= set(strict["violations"]) and strict["quality_class"] == 1
    assert "при допуске 1°" in " ".join(strict["explanations"])


# ------------------------------------------------------------------ доступ

def test_control_page_is_open_but_actions_need_admin(client, browsers):
    anon = browsers()
    page = anon.get("/control")
    assert page.status_code == 200 and "Пульт анализа" in page.text and 'href="/login?next=/control"' in page.text
    assert 'action="/control/runs/' not in page.text.split('id="params"')[0], "аноним не должен видеть кнопок действий"
    assert anon.get("/api/control/queue").status_code == 200
    user = user_browser(browsers, "plainuser")
    for path in ("/control/runs/nope/rerun", "/control/runs/nope/cancel", "/control/runs/nope/delete",
                 "/control/runs/nope/images/x/override", "/control/runs/nope/images/x/preview"):
        assert anon.post(path, data={"csrf": "x"}).status_code == 403
        assert user.post(path, data={"csrf": token(user)}).status_code == 403
    admin = admin_browser(browsers, "ctladmin")
    assert admin.post("/control/runs/nope/cancel", data={"csrf": "wrong"}).status_code == 403
    assert admin.post("/control/runs/nope/cancel", data={"csrf": token(admin)}).status_code == 404


# ------------------------------------------------------------------ прогоны

@needs_data
def test_rerun_with_params_and_progress(client, browsers):
    admin = admin_browser(browsers, "ctladmin")
    src = start_dataset(admin, dataset="test", mode="all")
    assert wait_state(admin, src) == "done"
    status = client.get(f"/api/runs/{src}").json()
    assert all("axis_tilt" not in r["violation_list"] for r in status["rows"])

    bad = admin.post(f"/control/runs/{src}/rerun", data={"csrf": token(admin), "axis_limit_deg": "99"})
    assert bad.status_code == 400 and "от 1 до 15" in bad.text

    r = admin.post(f"/control/runs/{src}/rerun", data={"csrf": token(admin), "axis_limit_deg": "1", "iliac_min_brightness": "4"},
                   follow_redirects=False)
    assert r.status_code == 303
    new = r.headers["location"].split("#run-")[1]
    assert new != src and wait_state(admin, new) == "done"
    data = admin.get(f"/api/runs/{new}").json()
    spine = next(x for x in data["rows"] if x["anatomical_region"] == "lumbar_spine")
    assert "axis_tilt" in spine["violation_list"]
    man = admin.get(f"/runs/{new}/files/manifest.json").json()
    assert man["params"]["axis_limit_deg"] == 1.0 and man["axis_limit"] == 1.0
    st = admin.get(f"/runs/{new}/files/../status.json")
    run_page = admin.get(f"/runs/{new}").text
    assert "Параметры анализа: ось 1°" in run_page and f'href="/runs/{src}"' in run_page
    queue = admin.get("/api/control/queue").json()
    assert any(x["id"] == new and x["progress"] == {"done": 3, "total": 3} for x in queue["runs"])
    assert "ось 1°" in admin.get("/control").text
    assert st.status_code == 404


@needs_data
def test_cancel_queued_and_running_then_delete(client, browsers):
    admin = admin_browser(browsers, "ctladmin")
    running = start_dataset(admin, dataset="train", mode="sample", n="25")
    queued = start_dataset(admin, dataset="test", mode="all")
    wait_state(admin, running, states=("running",), timeout=60)
    assert admin.post(f"/control/runs/{queued}/cancel", data={"csrf": token(admin)}, follow_redirects=False).status_code == 303
    assert wait_state(admin, queued, timeout=10) == "cancelled"
    assert admin.post(f"/control/runs/{running}/delete", data={"csrf": token(admin)}).status_code == 400, "идущий прогон не удаляется"
    assert admin.post(f"/control/runs/{running}/cancel", data={"csrf": token(admin)}, follow_redirects=False).status_code == 303
    assert wait_state(admin, running, timeout=60) == "cancelled"
    assert admin.get(f"/runs/{running}/files/manifest.json").status_code == 404
    again = admin.post(f"/control/runs/{running}/cancel", data={"csrf": token(admin)})
    assert again.status_code == 400 and "не в очереди" in again.text
    assert "отменён" in admin.get("/v1").text

    assert admin.post(f"/control/runs/{running}/delete", data={"csrf": token(admin)}, follow_redirects=False).status_code == 303
    assert admin.get(f"/api/runs/{running}").status_code == 404


# ------------------------------------------------------------------ снимки

@needs_data
def test_image_overrides_change_tables_not_evaluation(client, browsers):
    admin = admin_browser(browsers, "ctladmin")
    rid = start_dataset(admin, dataset="train", mode="sample", n="5")
    assert wait_state(admin, rid) == "done"
    man = admin.get(f"/runs/{rid}/files/manifest.json").json()
    spine = next(r for r in man["rows"] if r["anatomical_region"] == "lumbar_spine" and r["quality_class"] == 0)
    hip = next(r for r in man["rows"] if r["anatomical_region"].startswith("hip"))
    before_eval, before_rows = man["evaluation"], len(csv_rows(admin, rid))
    base = f"/control/runs/{rid}/images"

    r = admin.post(f"{base}/{spine['key']}/override", follow_redirects=False,
                   data={"csrf": token(admin), "action": "verdict", "quality_class": "1", "violations": ["artifact", "bogus"], "note": "пуговица"})
    assert r.status_code == 303 and r.headers["location"].endswith("#control")
    assert admin.post(f"{base}/{hip['key']}/override", data={"csrf": token(admin), "action": "exclude"}, follow_redirects=False).status_code == 303

    after = admin.get(f"/runs/{rid}/files/manifest.json").json()
    row = next(x for x in after["rows"] if x["key"] == spine["key"])
    assert row["quality_class"] == 1 and row["violation_list"] == ["artifact"] and row["auto"]["quality_class"] == 0
    assert row["override"]["by"] == "ctladmin" and row["override"]["note"] == "пуговица"
    assert after["summary"]["excluded"] == 1 and after["summary"]["overridden"] == 1
    assert after["evaluation"] == before_eval, "оценка сервиса против экспертов считается без правок"
    table = csv_rows(admin, rid)
    assert len(table) == before_rows - 1
    assert any(t[0] == spine["path_to_study"] and t[4] == "1" and t[5] == "artifact" for t in table)
    assert not any(t[0] == hip["path_to_study"] for t in table)

    card = admin.get(f"/runs/{rid}/images/{spine['key']}").text
    assert "Есть правка" in card and "пуговица" in card and "Автоматически: качественное" in card
    assert "пуговица" in admin.get("/control").text
    assert "правка" in admin.get(f"/runs/{rid}").text

    assert admin.post(f"{base}/{spine['key']}/override", data={"csrf": token(admin), "action": "verdict", "quality_class": "2"}).status_code == 400
    admin.post(f"{base}/{spine['key']}/override", data={"csrf": token(admin), "action": "reset"})
    admin.post(f"{base}/{hip['key']}/override", data={"csrf": token(admin), "action": "include"})
    restored = admin.get(f"/runs/{rid}/files/manifest.json").json()
    assert next(x for x in restored["rows"] if x["key"] == spine["key"])["quality_class"] == 0
    assert restored["summary"]["excluded"] == 0 and len(csv_rows(admin, rid)) == before_rows

    anon_card = browsers().get(f"/runs/{rid}/images/{spine['key']}").text
    assert "может админ" in anon_card and "/override" not in anon_card


@needs_data
def test_preview_does_not_change_run(client, browsers):
    admin = admin_browser(browsers, "ctladmin")
    rid = start_dataset(admin, dataset="test", mode="all")
    assert wait_state(admin, rid) == "done"
    man = admin.get(f"/runs/{rid}/files/manifest.json").json()
    spine = next(r for r in man["rows"] if r["anatomical_region"] == "lumbar_spine")
    url = f"/control/runs/{rid}/images/{spine['key']}/preview"
    r = admin.post(url, data={"csrf": token(admin), "axis_limit_deg": "1"})
    assert r.status_code == 200
    j = r.json()
    assert j["quality_class"] == 1 and "axis_tilt" in j["violations"] and j["run_quality_class"] == 0
    assert j["atlas_png"].startswith("data:image/png;base64,") and len(j["atlas_png"]) > 5000
    assert j["params_desc"] == "ось 1°"
    assert admin.post(url, data={"csrf": token(admin), "axis_limit_deg": "0"}).status_code == 400
    assert admin.get(f"/runs/{rid}/files/manifest.json").json() == man, "пробный анализ не меняет прогон"
