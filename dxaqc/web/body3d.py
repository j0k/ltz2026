# -*- coding: utf-8 -*-
"""3D-вид исследования: схематичный скелет (поясница, таз, бёдра) на подиуме, области окрашены по вердикту.

DXA — плоская проекция, объём по ней не восстанавливается: модель общая для всех, а из результатов проверки берутся
вердикты и нарушения областей, угол оси позвоночника, уровни позвонков Th12–L5 и места найденных предметов
(в долях кадра), вероятности модели бедра. Сцену рисует static/body3d.js на three.js из static/vendor — без сети.
"""
from __future__ import annotations

from collections import OrderedDict

REGIONS = ("lumbar_spine", "hip_left", "hip_right")
TITLE = {"lumbar_spine": "Поясничный отдел", "hip_left": "Левое бедро", "hip_right": "Правое бедро"}
VIOL = {"axis_tilt": "наклон оси", "coverage": "неполный охват", "artifact": "посторонний предмет",
        "hip_positioning": "укладка или ротация", "hip_roi": "поля зоны интереса", "manual": "отмечено вручную",
        "other": "другое нарушение"}


def studies(rows: list[dict]) -> "OrderedDict[str, list[dict]]":
    out: OrderedDict[str, list[dict]] = OrderedDict()
    for r in rows:
        if r.get("anatomical_region") in REGIONS:
            out.setdefault(r.get("study_key") or r.get("study_uid") or "исследование", []).append(r)
    return out


def _status(r: dict | None) -> str:
    if r is None:
        return "absent"
    q = r.get("quality_class")
    return "bad" if q == 1 else "ok" if q == 0 else "na"


def _num(v, nd=1) -> str:
    return f"{v:.{nd}f}".replace(".", ",")


def _spine(r: dict) -> dict:
    m = r.get("metrics") or {}
    c = r.get("callouts") or {}
    x0, y0, w, h = (c.get("image_box") or [0, 0, 1, 1])[:4]
    uv = lambda a: [round((a[0] - x0) / max(w, 1), 3), round((a[1] - y0) / max(h, 1), 3)]
    levels = {it["label"]: uv(it["anchor"]) for it in c.get("items", []) if it.get("label") in ("Th12", "L1", "L2", "L3", "L4", "L5")}
    spots = [uv(it["anchor"]) for it in c.get("items", []) if it.get("label") == "посторонний предмет"]
    v = set(r.get("violation_list") or [])
    lines = [f"ось {_num(m.get('angle_deg', 0))}° (допуск 5°)" + (" ✕" if "axis_tilt" in v else " ✓"),
             "охват " + ("✕" if "coverage" in v else "✓"),
             "предметы " + (f"✕ {len(spots)}" if "artifact" in v else "✓")]
    return dict(angle=float(m.get("angle_deg") or 0.0), levels=levels, aspect=round(w / max(h, 1), 4), spots=spots if "artifact" in v else [],
                coverage_bad="coverage" in v, axis_bad="axis_tilt" in v, lines=lines)


def _hip(r: dict) -> dict:
    m = r.get("metrics") or {}
    c = r.get("callouts") or {}
    x0, y0, w, h = (c.get("image_box") or [0, 0, 1, 1])[:4]
    pts = {}
    for it in c.get("items", []):                     # опоры для совмещения снимка с моделью: головка и большой вертел
        lab = it.get("label") or ""
        k = "head" if lab.startswith("шейка и головка") else "gt" if lab.startswith("большой вертел") else None
        if k:
            pts[k] = [round((it["anchor"][0] - x0) / max(w, 1), 3), round((it["anchor"][1] - y0) / max(h, 1), 3)]
    v = set(r.get("violation_list") or [])
    p = m.get("hip_prob_bad")
    lines = [f"вероятность брака {_num(p, 2)}" if p is not None else "не оценено"]
    if v & {"hip_positioning", "hip_roi"}:
        lines.append(", ".join(VIOL[x] for x in ("hip_positioning", "hip_roi") if x in v))
    return dict(prob=p, positioning="hip_positioning" in v, roi="hip_roi" in v, lines=lines, anchors=pts,
                aspect=round(w / max(h, 1), 4))


def scene(run_id: str, rows: list[dict]) -> dict:
    """Одна запись на область; если снимков области несколько, берётся худший вердикт."""
    by: dict[str, dict] = {}
    rank = {"bad": 3, "ok": 2, "na": 1}
    for r in rows:
        reg = r.get("anatomical_region")
        if reg in REGIONS and (reg not in by or rank[_status(r)] > rank[_status(by[reg])]):
            by[reg] = r
    regions = {}
    for reg in REGIONS:
        r = by.get(reg)
        st = _status(r)
        d = dict(title=TITLE[reg], status=st, violations=[VIOL.get(x, x) for x in (r or {}).get("violation_list") or []
                                                         if x != "hip_not_evaluated_v0"],
                 card=f"/runs/{run_id}/images/{r['key']}" if r else None,
                 image=f"/runs/{run_id}/files/{r['original_png']}" if r and r.get("original_png") else None)
        if r is None:
            d["lines"] = ["снимка нет в исследовании"]
        elif reg == "lumbar_spine":
            d.update(_spine(r))
        else:
            d.update(_hip(r))
        regions[reg] = d
    bad = [TITLE[k] for k, d in regions.items() if d["status"] == "bad"]
    verdict = "bad" if bad else "ok" if any(d["status"] == "ok" for d in regions.values()) else "na"
    return dict(regions=regions, verdict=verdict, bad=bad)


def hero_scene() -> dict:
    """Сцена для главной: все области годные, без выносок и снимков — просто модель на подиуме."""
    blank = dict(status="ok", violations=[], lines=[], card=None, image=None)
    return dict(regions={"lumbar_spine": dict(blank, title=TITLE["lumbar_spine"], angle=0.0, levels={}, spots=[], aspect=1.0,
                                              coverage_bad=False, axis_bad=False),
                         "hip_left": dict(blank, title=TITLE["hip_left"], prob=None, positioning=False, roi=False, anchors={}),
                         "hip_right": dict(blank, title=TITLE["hip_right"], prob=None, positioning=False, roi=False, anchors={})},
                verdict="ok", bad=[])
