# -*- coding: utf-8 -*-
"""Документы задачи на /tz/: ТЗ организатора и материалы команды, просмотр PDF в браузере и скачивание.

Файлы лежат вне образа: scripts/tz_docs.py собирает docs/tz/ (PDF, превью первой страницы, meta.json),
каталог монтируется в контейнер только на чтение (DXAQC_TZ_DIR). Отдаём только то, что перечислено в CATALOG.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from dxaqc import __version__

CATALOG = [
    dict(slug="tz-04", source_path="4. ДепЗдрав.pdf", download="ЛЦТ2026_задача04_ТЗ_ДепЗдрав.pdf",
         title="ТЗ задачи 04: сервис оценки качества исследований плотности костей",
         origin="организатор", author="Департамент здравоохранения Москвы", received="15.09.2026",
         summary="Первоисточник требований: что должен уметь сервис, как выглядит результат и по каким метрикам его оценят.",
         points=["по DICOM без разметки определить область — поясничный отдел или проксимальный отдел бедра — и класс качества 0/1 с типами нарушений",
                 "позвоночник: охват от подвздошных костей до половины Th12, наклон оси не больше 5°, посторонние предметы и артефакты",
                 "бедро: видны большой вертел, шейка и седалищная кость, ротация по малому вертелу, поля вокруг зоны интереса",
                 "выход — таблица csv/xlsx по строке на снимок; дополнительно визуализация нарушения, DICOM SR и веб-интерфейс",
                 "контейнер, API пакетной обработки, до 3 минут на исследование, работа локально без передачи снимков наружу",
                 "метрики: F1 и ROC-AUC с 95% доверительными интервалами, отдельно по областям и типам нарушений"]),
    dict(slug="razbor", source_path="LCT2026_analysis.pdf", download="ЛЦТ2026_выбор_и_разбор_задачи04.pdf",
         title="ЛЦТ 2026: выбор задачи и разбор задачи 04",
         origin="команда", author="Квантовый Скачок", received="10.09.2026",
         summary="Почему взяли задачу 04 и как к ней подходить: оценка десяти городских задач и разбор чек-листа аудитора DXA.",
         points=["десять задач хакатона по шансу на приз, риску остаться без данных и пользе после хакатона",
                 "что проверяет аудитор DXA: укладка позвоночника и бедра, артефакты, разметка областей",
                 "схема решения: вход, три ветки проверок, агрегатор, карточка качества с причиной брака",
                 "вопросы заказчику, которые важно было задать до старта"]),
    dict(slug="komanda", source_path="codellake_crew.pdf", download="ЛЦТ2026_команда.pdf",
         title="Команда «Квантовый Скачок»",
         origin="команда", author="Квантовый Скачок", received="26.09.2026",
         summary="Одностраничник о команде: Юрий Коноплёв (капитан), Алексей Чуркин и ИИ-разработчик Claude — кто за что отвечает.",
         points=[]),
]
BY_SLUG = {d["slug"]: d for d in CATALOG}

router = APIRouter(include_in_schema=False)
templates = None


def setup(tpl):
    global templates
    templates = tpl


def _dir() -> Path:
    return Path(os.environ.get("DXAQC_TZ_DIR", "/tz"))


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} МБ".replace(".", ",") if n >= 1024 * 1024 else f"{max(1, n // 1024)} КБ"


def _docs() -> list[dict]:
    try:
        meta = json.loads((_dir() / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    out = []
    for d in CATALOG:
        pdf = _dir() / f"{d['slug']}.pdf"
        m = meta.get(d["slug"], {})
        out.append(dict(d, available=pdf.is_file(), size=_size(pdf.stat().st_size) if pdf.is_file() else "",
                        pages=m.get("pages"), thumb=(_dir() / f"{d['slug']}.png").is_file()))
    return out


def _file(slug: str, suffix: str) -> tuple[dict, Path]:
    doc = BY_SLUG.get(slug)
    path = _dir() / f"{slug}{suffix}" if doc else None
    if not doc or not path.is_file():
        raise HTTPException(404, "документ не найден")
    return doc, path


@router.get("/tz/ml-map", include_in_schema=False)
def tz_mlmap_short():
    return RedirectResponse("/tz/ml-map.html", status_code=301)


@router.get("/tz/ml-map.html", response_class=HTMLResponse)
def tz_mlmap(request: Request):
    """Интерактивная шпаргалка scikit-learn: используется ли алгоритм на стенде и насколько он перспективен для задачи 04."""
    from dxaqc.web import ml_map as ML
    est = ML.estimators()
    return templates.TemplateResponse(request, "tz_mlmap.html", dict(
        data=ML.payload(), estimators=est, beyond=ML.BEYOND, perspective=ML.PERSPECTIVE, regions=ML.REGIONS, version=__version__,
        by_level={k: sum(1 for n in est if n["perspective"] == k) for k in ML.PERSPECTIVE},
        og_title="Шпаргалка scikit-learn для задачи 04 · DXA QC", og_image="/og/mlmap.jpg",
        og_description="Какие алгоритмы scikit-learn перспективны для контроля качества денситометрии, что используется на стенде и почему."))


@router.get("/tz/mindmap")
def tz_mindmap_short():
    return RedirectResponse("/tz/mindmap.html", status_code=301)


@router.get("/tz/roadmap", include_in_schema=False)
def tz_roadmap_short():
    return RedirectResponse("/tz/roadmap.html", status_code=301)


@router.get("/tz/roadmap.html", response_class=HTMLResponse)
def tz_roadmap(request: Request):
    """Роудмап развития: направления, инициативы с оценками в режиме вайбкодинга, зависимости и рекомендуемый путь."""
    from dxaqc.web import gantt as G
    from dxaqc.web import roadmap as RM
    g = G.data()
    status = {t["id"]: t["closed"] for e in g["epics"] for t in e["tasks"]}
    closed = [t for e in g["epics"] for t in e["tasks"] if t["closed"]]
    hours = (max(t["end"] for t in closed) - min(t["start"] for e in g["epics"] for t in e["tasks"])) / 3600 if closed else 0
    d = RM.build(status if g["ok"] else {})
    t = d["totals"]
    calib = dict(closed=len(closed), hours=f"{hours:.1f} ч".replace(".", ",") if closed else "—")
    return templates.TemplateResponse(request, "tz_roadmap.html", dict(
        d=d, calib=calib, version=__version__, payload=dict(d, trac_url=g["trac_url"]),
        og_title="Роудмап развития · DXA QC", og_image="/og/roadmap.jpg",
        og_description=(f"Куда развивать контроль качества денситометрии: {t['items']} инициатив в шести направлениях, "
                        f"рекомендуемый путь из {t['path']} шагов — агент {t['path_agent']}, человек {t['path_human']}.")))


@router.get("/tz/gantt.html", response_class=HTMLResponse)
def tz_gantt(request: Request, refresh: int = 0):
    """Диаграмма Ганта по данным трекера: задачи эпиков со сроками и вехи с признаком достижения."""
    from dxaqc.web import gantt as G
    d = G.data(force=bool(refresh))
    c = d["counts"]
    return templates.TemplateResponse(request, "tz_gantt.html", dict(
        d=d, version=__version__, og_title="Диаграмма Ганта проекта · DXA QC", og_image="/og/gantt.jpg",
        og_description=(f"Задачи и вехи проекта контроля качества денситометрии: закрыто {c['closed']} из {c['total']} задач, "
                        f"достигнуто {c['reached']} из {c['epics']} вех.")))


@router.get("/tz/mindmap.html", response_class=HTMLResponse)
def tz_mindmap(request: Request):
    """Mind map ТЗ задачи 04: разделы деревом, страницы PDF и статус реализации на стенде."""
    from dxaqc.web import tz_mindmap as MM
    pdf = (_dir() / "tz-04.pdf").is_file()
    c = MM.counts()
    return templates.TemplateResponse(request, "tz_mindmap.html", dict(
        tree=MM.TREE, counts=c, status_ru=MM.STATUS, pdf_url="/tz/tz-04.pdf" if pdf else "", version=__version__,
        og_title="Mind map ТЗ задачи 04 · DXA QC", og_image="/og/mindmap.jpg",
        og_description=(f"Требования ТЗ контроля качества денситометрии деревом: сделано {c['done']}, частично {c['partial']}, "
                        f"не сделано {c['todo']} из {c['total']}.")))


@router.get("/tz")
def tz_root():
    return RedirectResponse("/tz/", status_code=301)


@router.get("/tz/", response_class=HTMLResponse)
def tz_page(request: Request):
    return templates.TemplateResponse(request, "tz.html", dict(
        docs=_docs(), version=__version__, og_image="/og/tz.jpg",
        og_description="Документы задачи 04: ТЗ ДепЗдрава постранично, mind map требований со статусом на стенде "
                       "и интерактивная шпаргалка scikit-learn."))


@router.get("/tz/{slug}.pdf")
def tz_pdf(slug: str):
    doc, path = _file(slug, ".pdf")
    return FileResponse(path, media_type="application/pdf", filename=doc["download"], content_disposition_type="inline",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/tz/{slug}.png")
def tz_thumb(slug: str):
    _, path = _file(slug, ".png")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/tz/{slug}/download")
def tz_download(slug: str):
    doc, path = _file(slug, ".pdf")
    return FileResponse(path, media_type="application/pdf", filename=doc["download"])
