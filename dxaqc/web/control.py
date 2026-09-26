# -*- coding: utf-8 -*-
"""Пульт управления анализом: очередь и прогоны, параметры, перезапуск, отмена, удаление, правки снимков, пробный анализ.

Смотреть пульт может любой; запускать, отменять, удалять и править снимки — только админ (вход и CSRF из dxaqc.web.ask).
Доступ к прогонам app.py передаёт через setup(), чтобы модули не импортировали друг друга.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from dxaqc import __version__, pipeline, render
from dxaqc import params as P
from dxaqc.io import LoadFailure, load_image
from dxaqc.web import ask

router = APIRouter(include_in_schema=False)
ctx: dict = {}
_ov_lock = threading.Lock()
ACTIVE = ("queued", "running")


def setup(**kw):
    ctx.update(kw)


# ------------------------------------------------------------------ помощники

def _admin(request: Request) -> dict:
    user = request.state.user
    if not user or not user.get("is_admin"):
        raise HTTPException(403, "действие доступно только админу: войдите под учётной записью админа")
    return user


def _run_dir(run_id: str) -> str:
    if not run_id.replace("-", "").isalnum():
        raise HTTPException(404)
    d = os.path.join(ctx["runs_dir"], run_id)
    if not os.path.isfile(os.path.join(d, "status.json")):
        raise HTTPException(404, "прогон не найден")
    return d


def _manifest(run_id: str) -> dict:
    man = ctx["read"](run_id, os.path.join("out", "manifest.json"))
    if not man:
        raise HTTPException(400, "прогон ещё не готов")
    return man


def _row(man: dict, key: str) -> dict:
    row = next((r for r in man["rows"] if r.get("key") == key), None)
    if not row:
        raise HTTPException(404, "снимок не найден")
    return row


def _link_or_copy(src, dst):
    try:
        os.link(src, dst)  # жёсткая ссылка: исходные файлы не дублируются на диске
    except OSError:
        shutil.copy2(src, dst)


def load_overrides(run_id: str) -> dict:
    p = os.path.join(_run_dir(run_id), "out", "overrides.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_overrides(run_id: str, overrides: dict):
    out = os.path.join(_run_dir(run_id), "out")
    with open(os.path.join(out, "overrides.json.tmp"), "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=1)
    os.replace(os.path.join(out, "overrides.json.tmp"), os.path.join(out, "overrides.json"))
    pipeline.apply_overrides(out, overrides)


def queue_state(limit: int = 200) -> dict:
    runs = ctx["list_runs"](limit=limit)
    counts = dict(queued=0, running=0, done=0, failed=0)
    for r in runs:
        state = r.get("state")
        counts["failed" if state in ("error", "cancelled") else state if state in counts else "queued"] += 1
    items = [dict(id=r["id"], state=r.get("state"), progress=r.get("progress"), title=r.get("title"), error=r.get("error"))
             for r in runs]
    return dict(counts=counts, runs=items)


def _calibration(run_id: str) -> list:
    """Сохранённые измерения позвоночника с метками экспертов: пульт пересчитывает по ним метрики без повторного анализа."""
    man = ctx["read"](run_id, os.path.join("out", "manifest.json")) or {}
    rows = []
    for r in man.get("rows", []):
        m = r.get("metrics") or {}
        if (r.get("processing_status") != "Success" or r.get("anatomical_region") != "lumbar_spine"
                or not r.get("expert") or "abs_angle" not in m):
            continue
        rows.append([r["study_key"], m["abs_angle"], min(m.get("iliac_left", 0), m.get("iliac_right", 0)),
                     m.get("artifact_contrast", 0), r["expert"]["types"], r["expert"]["bad"]])
    return rows


def _journal(runs: list[dict]) -> list[dict]:
    out = []
    for r in runs:
        if r.get("state") != "done":
            continue
        ov = load_overrides(r["id"])
        if not ov:
            continue
        man = ctx["read"](r["id"], os.path.join("out", "manifest.json")) or {}
        names = {x.get("key"): x.get("path_to_study", "") for x in man.get("rows", [])}
        for key, o in ov.items():
            out.append(dict(run_id=r["id"], run_title=r.get("title") or r["id"], key=key,
                            image=os.path.basename(names.get(key, key)), **o))
    out.sort(key=lambda o: -(o.get("at") or 0))
    return out[:100]


def _page(request: Request, source: str = "", error: str = "", status_code: int = 200, values: dict | None = None):
    user = request.state.user
    runs = ctx["list_runs"](limit=200)
    done = [r for r in runs if r.get("state") == "done"]
    source = source if any(r["id"] == source for r in done) else (done[0]["id"] if done else "")
    if values is None:
        src_status = ctx["read"](source, "status.json") if source else None
        values = P.normalize((src_status or {}).get("params"))
    train = next((r for r in done if r.get("dataset") == "train" and r.get("summary", {}).get("studies", 0) >= 90
                  and not P.changed(r.get("params"))), None)
    return ctx["templates"].TemplateResponse(request, "control.html", dict(
        user=user, csrf=request.state.csrf, is_admin=bool(user and user.get("is_admin")), runs=runs, done_runs=done,
        counts=queue_state()["counts"], spec=P.SPEC, defaults=P.DEFAULTS, values=values, source=source, error=error,
        calib=_calibration(train["id"]) if train else None, calib_run=train["id"] if train else "",
        journal=_journal(runs), example_id=ctx["example_id"], trac_url=ctx["trac_url"], version=__version__,
        violation_ru=ctx["violation_ru"], og_image="/og/control.jpg",
        og_description="Пороги и параметры анализа, перезапуск прогонов с новыми параметрами, очередь, отмена и правка вердикта снимка."), status_code=status_code)


# ------------------------------------------------------------------ страницы и состояние

@router.get("/control", response_class=HTMLResponse)
def control_page(request: Request, source: str = ""):
    return _page(request, source=source)


@router.get("/api/control/queue")
def api_queue():
    return queue_state()


# ------------------------------------------------------------------ действия с прогонами

@router.post("/control/runs/{run_id}/rerun")
async def rerun(request: Request, run_id: str):
    admin = _admin(request)
    form = await request.form()
    ask._check_csrf(request, str(form.get("csrf", "")))
    src = _run_dir(run_id)
    st = ctx["read"](run_id, "status.json") or {}
    raw = {s["name"]: form.get(s["name"]) for s in P.SPEC}
    try:
        p = P.normalize(raw)
    except P.ParamError as exc:
        return _page(request, source=run_id, error=str(exc), status_code=400, values=P.normalize(None) | {
            k: v for k, v in raw.items() if v not in (None, "")})
    if st.get("state") in ACTIVE:
        return _page(request, source=run_id, error="этот прогон ещё обрабатывается", status_code=400, values=p)
    if not os.path.isdir(os.path.join(src, "input")):
        return _page(request, source=run_id, error="у прогона не сохранились исходные файлы", status_code=400, values=p)
    title = (st.get("title") or run_id).removeprefix("Перезапуск: ").split(" · ")[0]
    new_id = ctx["new_run"](f"Перезапуск: {title} · {P.describe(p)}")
    shutil.copytree(os.path.join(src, "input"), os.path.join(ctx["runs_dir"], new_id, "input"), symlinks=True,
                    dirs_exist_ok=True, copy_function=_link_or_copy)
    ctx["write_status"](new_id, params=p, parent=run_id, dataset=st.get("dataset"), studies=st.get("studies"),
                        started_by=admin["login"])
    ctx["submit"](new_id)
    return RedirectResponse(f"/control#run-{new_id}", status_code=303)


@router.post("/control/runs/{run_id}/cancel")
async def cancel(request: Request, run_id: str):
    _admin(request)
    form = await request.form()
    ask._check_csrf(request, str(form.get("csrf", "")))
    _run_dir(run_id)
    st = ctx["read"](run_id, "status.json") or {}
    if st.get("state") not in ACTIVE:
        return _page(request, error="прогон не в очереди и не обрабатывается", status_code=400)
    if not ctx["cancel"](run_id):  # задача потеряна при перезапуске сервиса: просто отмечаем
        ctx["write_status"](run_id, state="cancelled", finished=time.time())
    return RedirectResponse(f"/control#run-{run_id}", status_code=303)


@router.post("/control/runs/{run_id}/delete")
async def delete(request: Request, run_id: str):
    _admin(request)
    form = await request.form()
    ask._check_csrf(request, str(form.get("csrf", "")))
    d = _run_dir(run_id)
    st = ctx["read"](run_id, "status.json") or {}
    if run_id == ctx["example_id"]:
        return _page(request, error="пример организатора не удаляется: он пересоздаётся при запуске стенда", status_code=400)
    if st.get("state") in ACTIVE:
        return _page(request, error="сначала отмените прогон", status_code=400)
    shutil.rmtree(d, ignore_errors=True)
    return RedirectResponse("/control#queue", status_code=303)


# ------------------------------------------------------------------ снимки

@router.post("/control/runs/{run_id}/images/{key}/override")
async def override(request: Request, run_id: str, key: str):
    admin = _admin(request)
    form = await request.form()
    ask._check_csrf(request, str(form.get("csrf", "")))
    man = _manifest(run_id)
    row = _row(man, key)
    if row.get("processing_status") != "Success":
        raise HTTPException(400, "снимок не был обработан, править нечего")
    action = str(form.get("action", ""))
    stamp = dict(by=admin["login"], at=time.time())
    with _ov_lock:
        ov = load_overrides(run_id)
        cur = dict(ov.get(key) or {})
        if action == "reset":
            ov.pop(key, None)
        elif action == "exclude":
            ov[key] = cur | {"excluded": True} | stamp
        elif action == "include":
            cur.pop("excluded", None)
            if "quality_class" in cur:
                ov[key] = cur | stamp
            else:
                ov.pop(key, None)
        elif action == "verdict":
            q = str(form.get("quality_class", ""))
            if q not in ("0", "1"):
                raise HTTPException(400, "выберите вердикт: качественное или есть нарушение")
            codes = [c for c in form.getlist("violations") if c in pipeline.OVERRIDE_CODES] if q == "1" else []
            note = str(form.get("note", "")).strip()[:500]
            ov[key] = {k: v for k, v in cur.items() if k == "excluded"} | dict(quality_class=int(q), violations=codes, note=note) | stamp
        else:
            raise HTTPException(400, "неизвестное действие")
        _save_overrides(run_id, ov)
    return RedirectResponse(f"/runs/{run_id}/images/{key}#control", status_code=303)


@router.post("/control/runs/{run_id}/images/{key}/preview")
async def preview(request: Request, run_id: str, key: str):
    _admin(request)
    form = await request.form()
    ask._check_csrf(request, str(form.get("csrf", "")))
    man = _manifest(run_id)
    row = _row(man, key)
    try:
        p = P.normalize({s["name"]: form.get(s["name"]) for s in P.SPEC})
    except P.ParamError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    input_dir = os.path.join(_run_dir(run_id), "input")
    path = os.path.join(input_dir, row["path_to_study"])  # путь берём из manifest, не из запроса
    if not os.path.exists(path):
        return JSONResponse({"error": "исходный файл снимка не найден"}, status_code=404)
    img = await run_in_threadpool(load_image, path, input_dir)
    if isinstance(img, LoadFailure):
        return JSONResponse({"error": f"не удалось прочитать снимок: {img.error}"}, status_code=422)
    res, art = await run_in_threadpool(pipeline.analyze_image, img.pixels, p)
    picture = art["atlas"] if art else render.overlay(img.pixels, res)
    buf = io.BytesIO()
    picture.save(buf, format="PNG", optimize=True)
    auto = row.get("auto") or row
    vr = ctx["violation_ru"]
    return JSONResponse(dict(
        params=p, params_desc=P.describe(p), quality_class=res["quality_class"], violations=res["violations"],
        violations_ru=[vr.get(v, v) for v in res["violations"]], explanations=res["explanations"],
        measurements=res["measurements"], atlas_png="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
        run_quality_class=auto.get("quality_class"), run_violations_ru=[vr.get(v, v) for v in auto.get("violation_list") or []]))
