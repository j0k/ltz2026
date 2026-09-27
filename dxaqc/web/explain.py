# -*- coding: utf-8 -*-
"""Пояснение вердикта графом: снимок → область → проверки ТЗ с измерением и порогом → вердикт.

Узлы строятся из результата анализа (metrics, violation_list, quality_class) и порогов прогона; текстовые пояснения
(explanations) остаются рядом — граф сворачивается в них по желанию.
"""
from __future__ import annotations

from dxaqc import params as P

REGION = {"lumbar_spine": "поясничный отдел", "hip_left": "левое бедро", "hip_right": "правое бедро"}


def _n(v, nd=1):
    return f"{v:.{nd}f}".replace(".", ",")


def graph(row: dict, run_params: dict | None, hip_thr: dict | None) -> dict | None:
    reg = row.get("anatomical_region")
    if reg not in REGION or row.get("processing_status") != "Success":
        return None
    m = row.get("metrics") or {}
    viol = set(row.get("violation_list") or [])
    basis = next((e[len("Область: "):].rstrip(".") for e in row.get("explanations") or [] if e.startswith("Область: ")), "")
    checks = []
    if reg == "lumbar_spine":
        p = P.normalize(run_params)
        il, ir = m.get("iliac_left"), m.get("iliac_right")
        if il is not None and ir is not None:
            checks.append(dict(title="Охват", code="coverage", value=f"гребни {_n(il)} / {_n(ir)}",
                               rule=f"оба ≥ {_n(p['iliac_min_brightness'])}"))
        if m.get("angle_deg") is not None:
            checks.append(dict(title="Ось", code="axis_tilt", value=f"угол {_n(m['angle_deg'])}°", rule=f"|угол| ≤ {_n(p['axis_limit_deg'])}°"))
        if m.get("artifact_contrast") is not None:
            checks.append(dict(title="Предметы", code="artifact", value=f"контраст {m['artifact_contrast']:.0f}",
                               rule=f"< {p['artifact_contrast']}"))
        method = "правила по яркости и геометрии"
    else:
        t = hip_thr or {}
        if m.get("hip_prob_bad") is None:
            checks.append(dict(title="Модель", code="", value="не оценено", rule="", state="na"))
        else:
            checks.append(dict(title="Брак", code="", value=f"p = {_n(m['hip_prob_bad'], 2)}", rule=f"< {_n(t.get('bad', 0.5), 2)}",
                               state="bad" if row.get("quality_class") == 1 else "ok"))
            checks.append(dict(title="Укладка", code="hip_positioning", value=f"p = {_n(m.get('hip_prob_positioning') or 0, 2)}",
                               rule=f"< {_n(t.get('hip_positioning', 0.5), 2)}"))
            checks.append(dict(title="Поля ROI", code="hip_roi", value=f"p = {_n(m.get('hip_prob_roi') or 0, 2)}",
                               rule=f"< {_n(t.get('hip_roi', 0.5), 2)}"))
        method = "ExtraTrees · 47 признаков формы и ориентиров"
    for c in checks:
        c.setdefault("state", "bad" if c["code"] in viol else "ok")
    q = row.get("quality_class")
    verdict = dict(state="bad" if q == 1 else "ok" if q == 0 else "na",
                   text="брак" if q == 1 else "годен" if q == 0 else "не оценено")
    return dict(region=REGION[reg], basis=basis, method=method, checks=checks, verdict=verdict)
