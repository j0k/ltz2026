# -*- coding: utf-8 -*-
"""Заготовки для главной: по одному показательному исследованию обучающего набора на каждый тип нарушения ТЗ.

Берутся из последнего прогона всего обучающего набора: у строк там есть оценка экспертов (expert) и миниатюра.
Среди подходящих предпочитаются исследования, где сервис согласен с экспертами, — заготовка показывает, как
выглядит нарушение и его разбор. Плюс фрагмент «Для теста» организатора целиком.
"""
from __future__ import annotations

CATEGORIES = [
    ("ok", "Качественное исследование", "поясница и оба бедра без нарушений"),
    ("artifact", "Посторонний предмет", "металл или артефакт в зоне позвоночника"),
    ("coverage", "Неполный охват", "гребни подвздошных костей не в кадре"),
    ("axis_tilt", "Наклон оси", "позвоночник отклонён больше 5°"),
    ("hip_positioning", "Укладка бедра", "ротация или положение бедра"),
    ("hip_roi", "Поля зоны интереса", "мало места вокруг шейки бедра"),
]
TYPE_RU = {"coverage": "неполный охват", "axis_tilt": "наклон оси", "artifact": "посторонний предмет",
           "hip_positioning": "укладка бедра", "hip_roi": "поля зоны интереса"}


def expert_text(e: dict | None) -> str:
    if not e or e.get("bad") not in (0, 1):
        return "нет оценки экспертов"
    return "эксперты: годен" if e["bad"] == 0 else "эксперты: " + (", ".join(TYPE_RU.get(t, t) for t in e.get("types") or []) or "брак")


def build(run_id: str | None, manifest: dict | None) -> list[dict]:
    rows = [r for r in (manifest or {}).get("rows", []) if r.get("expert") and r.get("thumb_png") and r.get("study_key")]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["study_key"], []).append(r)
    out, used = [], set()
    for code, title, sub in CATEGORIES:
        best = None
        for study in sorted(by):
            if study in used:
                continue
            rs = by[study]
            if code == "ok":
                if len({r["anatomical_region"] for r in rs}) < 3 or any(r["expert"].get("bad") != 0 for r in rs):
                    continue
                hit, agree = rs[0], all(r.get("quality_class") == 0 for r in rs)
            else:
                cand = [r for r in rs if code in (r["expert"].get("types") or [])]
                if not cand:
                    continue
                caught = [r for r in cand if code in (r.get("violation_list") or [])]
                hit, agree = (caught or cand)[0], bool(caught)
            score = (agree, len(rs))
            if best is None or score > best[0]:
                best = (score, study, hit)
        if best:
            _, study, hit = best
            used.add(study)
            out.append(dict(key=code, title=title, sub=sub, dataset="train", study=study,
                            thumb=f"/runs/{run_id}/files/{hit['thumb_png']}", expert=expert_text(hit["expert"])))
    return out
