# -*- coding: utf-8 -*-
"""Каталог нарушений: всё, что знает система, с определением по ТЗ, способом проверки, статусом и примерами снимков.

Примеры берутся из последнего прогона всего обучающего набора: у каждой строки там есть оценка экспертов
(expert.types) и вердикт сервиса (violation_list). Для каждого нарушения снимки делятся на «сервис нашёл»,
«сервис пропустил» и «ложная тревога» — так видно не только само нарушение, но и где сервис ошибается.
Снимки показываются только на стенде; в Telegram и другие внешние системы они не отправляются.
"""
from __future__ import annotations

from collections import OrderedDict

STATUS = {"checked": ("проверяется", "✓"), "partial": ("частично", "◐"), "todo": ("пока не проверяется", "✕"),
          "state": ("состояние", "i")}

ENTRIES = [
    dict(code="coverage", region="lumbar_spine", title="Неполный охват", status="partial", metric="spine_coverage", roadmap="q_th12",
         tz="Снимок поясничного отдела должен захватывать позвоночник от гребней подвздошных костей до середины тела Th12.",
         method="Сервис ищет гребни подвздошных костей у нижнего края кадра и проверяет запас по краям. Уровень Th12 пока не "
                "определяется — поэтому статус «частично»."),
    dict(code="axis_tilt", region="lumbar_spine", title="Наклон оси позвоночника", status="checked", metric="spine_axis_tilt", roadmap="q_axis",
         tz="Ось позвоночника отклоняется от вертикали больше допуска — 5°.",
         method="Центральная линия столба по яркости, угол прямой к вертикали кадра. Слабое место — сколиоз: изгиб столба "
                "сервис принимает за наклон."),
    dict(code="artifact", region="lumbar_spine", title="Посторонние предметы и артефакты", status="checked", metric="spine_artifact",
         roadmap="q_art",
         tz="В зоне исследования нет посторонних предметов: металла, пуговиц, застёжек, пирсинга, имплантов вне зоны интереса.",
         method="Поиск ярких пятен с резкими краями на фоне позвонков. Большую часть случаев экспертов сервис пока пропускает."),
    dict(code="hip_positioning", region="hip", title="Укладка и ротация бедра", status="todo", metric=None, roadmap="q_hip",
         tz="В кадре большой вертел, шейка бедра и седалищная кость; ротация оценивается по малому вертелу.",
         method="В версии 0.5 бедро не оценивается: сервис определяет сторону и помечает снимок «не оценено». Разметка экспертов "
                "есть — это следующий шаг роудмапа."),
    dict(code="hip_roi", region="hip", title="Поля вокруг зоны интереса", status="todo", metric=None, roadmap="q_roi",
         tz="Вокруг зоны интереса бедра должны оставаться поля 3 см и 2 см.",
         method="Не проверяется: в DICOM организатора нет масштаба (PixelSpacing), сантиметры без него не посчитать."),
    dict(code="hip_not_evaluated_v0", region="state", title="Бедро не оценено", status="state", metric=None, roadmap="q_hip",
         tz="Не нарушение, а честное состояние: вердикт по бедру в этой версии не выносится.",
         method="Такие снимки не попадают ни в «качественные», ни в «с нарушением» — в таблице результатов класс качества пустой."),
    dict(code="manual", region="state", title="Отмечено вручную", status="state", metric=None, roadmap=None,
         tz="Нарушение поставил человек в пульте анализа поверх автоматического вердикта.",
         method="Правка вердикта в карточке снимка; автоматический результат сохраняется рядом, правка идёт в журнал."),
    dict(code="other", region="state", title="Другое нарушение", status="state", metric=None, roadmap=None,
         tz="Нарушение вне перечня ТЗ, отмеченное вручную.", method="Только ручная отметка."),
]
REJECTS = [
    dict(code="not_dicom", title="Не DICOM", text="Картинка (JPG, PNG и т. п.) вместо DICOM. Можно запросить принудительный анализ — "
                                                    "результат не гарантирован."),
    dict(code="not_dxa", title="DICOM, но не денситометрия", text="Например, КТ или обычный рентген. Тоже можно проверить "
                                                                   "принудительно по запросу."),
    dict(code="unreadable", title="Файл не читается", text="Повреждённый или неполный файл — анализ невозможен."),
]
REGIONS = OrderedDict([("lumbar_spine", "Поясничный отдел"), ("hip", "Бедро"), ("state", "Состояния снимка")])
# темы комментариев экспертов, которые требуют внимания, и в каких областях их показывать
ATTENTION = [("требует внимание", None), ("сколиоз", "lumbar_spine"), ("перелом", None), ("нет малых вертелов", None)]


def _example(r: dict, run_id: str) -> dict:
    return dict(key=r["key"], region=r.get("anatomical_region"), comment=(r.get("expert") or {}).get("comment", ""),
                thumb=f"/runs/{run_id}/files/{r['thumb_png']}", card=f"/runs/{run_id}/images/{r['key']}")


def _region_ok(entry_region: str, row_region: str | None) -> bool:
    return (row_region or "").startswith("hip") if entry_region == "hip" else row_region == entry_region


def build(manifest: dict | None, run_id: str | None) -> dict:
    """Каталог с примерами из прогона обучающего набора; без прогона — только определения."""
    rows = [r for r in (manifest or {}).get("rows", []) if r.get("key") and r.get("thumb_png")] if run_id else []
    ev = (manifest or {}).get("evaluation") or {}
    entries = []
    for e in ENTRIES:
        caught, missed, false_alarm, seen = [], [], [], []
        for r in rows:
            if not _region_ok(e["region"], r.get("anatomical_region")) and e["region"] != "state":
                continue
            expert = e["code"] in ((r.get("expert") or {}).get("types") or [])
            service = e["code"] in (r.get("violation_list") or [])
            if e["region"] == "state":
                if service:
                    seen.append(_example(r, run_id))
            elif expert and service:
                caught.append(_example(r, run_id))
            elif expert:
                missed.append(_example(r, run_id))
            elif service:
                false_alarm.append(_example(r, run_id))
        m = ev.get(e["metric"]) if e["metric"] else None
        label, icon = STATUS[e["status"]]
        entries.append(dict(e, status_label=label, status_icon=icon, caught=caught, missed=missed, false_alarm=false_alarm,
                            seen=seen, expert_total=len(caught) + len(missed), metric_values=m))
    attention = []
    for theme, region in ATTENTION:
        found = [_example(r, run_id) for r in rows if theme in ((r.get("expert") or {}).get("comment") or "").lower()
                 and (region is None or r.get("anatomical_region") == region)]
        if found:
            attention.append(dict(theme=theme, examples=found))
    normals = {}
    for key in ("lumbar_spine", "hip"):
        normals[key] = [_example(r, run_id) for r in rows if _region_ok(key, r.get("anatomical_region"))
                        and (r.get("expert") or {}).get("bad") == 0 and not (r.get("expert") or {}).get("comment")
                        and (key != "lumbar_spine" or r.get("quality_class") == 0)][:4]
    groups = [dict(id=rid, title=title, entries=[e for e in entries if e["region"] == rid]) for rid, title in REGIONS.items()]
    # сквозная нумерация для оглавления и заголовков карточек, с количеством по данным обучающего набора
    toc, num = [], 0
    for g in groups:
        section = dict(title=g["title"], anchor=g["id"], items=[])
        for e in g["entries"]:
            num += 1
            e["num"], e["anchor"] = num, f"v-{e['code']}"
            if e["status"] in ("checked", "partial"):
                facts = f"эксперты {e['expert_total']} · нашёл {len(e['caught'])} · ложных {len(e['false_alarm'])}"
            elif e["status"] == "todo":
                facts = f"эксперты {e['expert_total']}"
            else:
                facts = f"снимков {len(e['seen'])}" if e["seen"] else "в обучающем наборе нет"
            section["items"].append(dict(num=num, title=e["title"], code=e["code"], anchor=e["anchor"], status=e["status"],
                                         status_icon=e["status_icon"], facts=facts if rows else ""))
        toc.append(section)
    section = dict(title="Требует внимания", anchor="attention", items=[])
    for i, a in enumerate(attention, 1):
        num += 1
        a["num"], a["anchor"] = num, f"a-{i}"
        section["items"].append(dict(num=num, title=f"«{a['theme']}»", code="", anchor=a["anchor"], status="state",
                                     status_icon="!", facts=f"снимков {len(a['examples'])}"))
    if section["items"]:
        toc.append(section)
    section = dict(title="Отказы", anchor="rejects", items=[])
    rejects = [dict(r) for r in REJECTS]
    for r in rejects:
        num += 1
        r["num"], r["anchor"] = num, f"r-{r['code']}"
        section["items"].append(dict(num=num, title=r["title"], code=r["code"], anchor=r["anchor"], status="state", status_icon="✕",
                                     facts="файл не анализируется"))
    toc.append(section)
    return dict(groups=groups, entries=entries, rejects=rejects, attention=attention, normals=normals, run_id=run_id, toc=toc,
                has_examples=bool(rows),
                counts=dict(total=len(ENTRIES) + len(REJECTS),
                            checked=sum(1 for e in ENTRIES if e["status"] in ("checked", "partial")),
                            todo=sum(1 for e in ENTRIES if e["status"] == "todo"),
                            examples=sum(len(e["caught"]) + len(e["missed"]) for e in entries)))
