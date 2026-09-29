# -*- coding: utf-8 -*-
"""Дообучение на правках врачей (29.09, Юрий): плагины, сбор правок, ворота качества, установка и откат."""
import json
import os

import numpy as np
import pytest

from dxaqc import learning as L
from dxaqc.desktop import synth


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DXAQC_DATA", str(tmp_path))
    monkeypatch.setenv("DXAQC_PLUGINS", str(tmp_path / "plugins"))
    return tmp_path


def _spine_samples(n_ok=8, n_bad=8, source="организатор"):
    out = []
    for i in range(n_ok + n_bad):
        bad = int(i >= n_ok)
        a = synth.spine(artifact=bool(bad))
        a = np.clip(a.astype(int) + (i % 5), 0, 255).astype(np.uint8)       # немного разные снимки
        out.append(L.Sample(key=f"s{i}", sha=f"sha{source}{i}", study=f"st{source}{i}", region="lumbar_spine", bad=bad,
                            types=["artifact"] if bad else [], pixels=a, source=source))
    return out


def test_feedback_from_doctor_overrides(data):
    from dxaqc import pipeline
    src = data / "runs" / "r1" / "input" / "st"
    synth.study(str(src), "artifact")
    out = data / "runs" / "r1" / "out"
    pipeline.run_batch(str(data / "runs" / "r1" / "input"), str(out))
    man = json.load(open(out / "manifest.json", encoding="utf-8"))
    keys = {r["anatomical_region"]: r["key"] for r in man["rows"]}
    ov = {keys["lumbar_spine"]: dict(quality_class=1, violations=["artifact"], by="doc", at=0),
          keys["hip_left"]: dict(excluded=True, by="doc", at=0)}                 # исключённый снимок в обучение не идёт
    json.dump(ov, open(out / "overrides.json", "w"))
    fb = L.feedback()
    assert [(s.region, s.bad, s.types) for s in fb] == [("lumbar_spine", 1, ["artifact"])]
    assert fb[0].pixels is not None and fb[0].source == "врач doc"


def test_builtin_plugins_registered(data):
    pl = L.plugins()
    assert {"hip_trees", "spine_thresholds"} <= set(pl)
    st = L.status()
    assert st["feedback"] == 0 and {p["name"] for p in st["plugins"]} >= {"hip_trees", "spine_thresholds"}


def test_external_plugin_install_gate_and_rollback(data):
    (data / "plugins").mkdir()
    (data / "plugins" / "demo.py").write_text('''
from dxaqc.learning import Learner, register
import os, json

@register
class Demo(Learner):
    name = "demo"; title = "Демо"; regions = ("lumbar_spine",); min_feedback = 1
    def train(self, samples): return {"n": len(samples), "bad": sum(s.bad for s in samples)}
    def evaluate(self, cand, samples): return {"score": cand["bad"] / max(cand["n"], 1)}
    def install(self, cand, metrics, vdir):
        p = os.path.join(vdir, "demo.json"); json.dump(cand, open(p, "w")); return p
''', encoding="utf-8")
    assert "demo" in L.plugins()
    base = _spine_samples(4, 4)
    fb = [L.Sample(key="f1", sha="new1", study="n1", region="lumbar_spine", bad=1, types=["artifact"], source="врач")]
    r1 = L.run(["demo"], base=base, fb=fb, by="t")[0]
    assert r1.ok and r1.installed and L.plugins()["demo"].active()["metrics"]["score"] == pytest.approx(5 / 9)
    # хуже действующей версии больше допуска — не устанавливается
    worse = [L.Sample(key=f"g{i}", sha=f"g{i}", study=f"g{i}", region="lumbar_spine", bad=0, source="врач") for i in range(20)]
    r2 = L.run(["demo"], base=base, fb=worse, by="t")[0]
    assert not r2.ok and not r2.installed and "не установлена" in r2.message
    # мало правок — запуск не нужен, если не force
    assert "дообучение не требуется" in L.run(["demo"], base=base, fb=[], by="t")[0].message
    assert L.rollback("demo") == "встроенная версия" and L.plugins()["demo"].active() is None
    assert any(h["plugin"] == "demo" for h in L.history())


def test_spine_thresholds_learn_and_apply(data):
    from dxaqc import params as P
    base = _spine_samples(8, 8)
    fb = _spine_samples(3, 3, source="врач")
    res = L.run(["spine_thresholds"], base=base, fb=fb, by="t", force=True)[0]
    assert res.metrics["samples"] == 22 and "thresholds" in res.metrics
    assert res.ok, res.message                          # на разделимых фантомах кандидат не хуже
    learned = P.learned()
    assert "artifact_contrast" in learned and isinstance(learned["artifact_contrast"], int)
    assert P.normalize(None)["axis_limit_deg"] == 5.0, "допуск оси по ТЗ плагин не меняет"
    assert P.normalize(None)["artifact_contrast"] == learned["artifact_contrast"]
    L.rollback("spine_thresholds")
    assert P.learned() == {} and P.normalize(None)["artifact_contrast"] == P.DEFAULTS["artifact_contrast"]


def test_hip_plugin_installs_weights_service_can_load(data):
    pytest.importorskip("sklearn")
    from dxaqc import hipmodel as HM
    from dxaqc.learning.hip import HipTrees
    rng = np.random.default_rng(0)
    samples = []
    for i in range(24):
        side = "hip_left" if i % 2 else "hip_right"
        a = synth.hip(side.split("_")[1])
        a = np.clip(a.astype(int) + rng.integers(-6, 7, a.shape), 0, 255).astype(np.uint8)
        samples.append(L.Sample(key=f"h{i}", sha=f"h{i}", study=f"s{i}", region=side, bad=int(i % 3 == 0),
                                types=["hip_positioning"] if i % 3 == 0 else [], pixels=a, source="организатор"))
    p = HipTrees(); p.reps = 1
    cand = p.train(samples)
    vdir = data / "learning" / "hip_trees" / "versions" / "v1"; vdir.mkdir(parents=True)
    path = p.install(cand, p.evaluate(cand, samples), str(vdir))
    (data / "learning" / "hip_trees" / "active.json").write_text(json.dumps(dict(version="v1", path=path)), encoding="utf-8")
    assert HM.active_path() == path
    m = HM.load()
    assert m["meta"]["method"]["source"] == "дообучение на правках врачей"
    r = HM.predict(samples[0].pixels, samples[0].region)
    assert r is not None and 0.0 <= r["prob"]["bad"] <= 1.0


def test_control_learning_admin_only(client):
    st = client.get("/api/control/learning").json()
    assert {p["name"] for p in st["plugins"]} >= {"hip_trees", "spine_thresholds"} and st["job"]["state"] in ("idle", "done", "error")
    r = client.post("/control/learning/run", data={"csrf": "x"}, follow_redirects=False)
    assert r.status_code in (403, 400)
    html = client.get("/control").text
    assert "Дообучение на правках врачей" in html
