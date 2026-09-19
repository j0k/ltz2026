# -*- coding: utf-8 -*-
"""Веб-стенд DXA QC: загрузка исследований, пакетная обработка, таблица и карточки снимков.

Контракт с пайплайном: pipeline.run_batch(input_dir, out_dir) пишет out_dir/manifest.json,
results.csv, results.xlsx, overlays.zip и PNG-файлы снимков.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from dxaqc import __version__, atlas, datasets, pipeline, voice
from dxaqc import params as P
from dxaqc.io import safe_extract
from dxaqc.web import accounts, analysis, ask, control, datastats, mcp, og, progress, showcase, tgbot, tz

DATA = os.environ.get("DXAQC_DATA", "/data")
RUNS = os.path.join(DATA, "runs")
TTS_CACHE = os.path.join(DATA, "tts")
SEED = os.environ.get("DXAQC_SEED", "")
TRAC_URL = os.environ.get("DXAQC_TRAC_URL", "/trac/")
HOME_DESIGN = os.environ.get("DXAQC_HOME", "bio")  # главная в стиле biotech одобрена Юрием 16.09; прежняя — /?design=classic
EXAMPLE_ID = "example"
os.makedirs(RUNS, exist_ok=True)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
ask.setup(templates)
# абсолютные адреса для превью ссылок: за nginx request.base_url видит внутренний http-адрес
PUBLIC_URL = os.environ.get("DXAQC_PUBLIC_URL", "https://ltz2026.juri-konoplev.pro").rstrip("/")
templates.env.globals["public_url"] = PUBLIC_URL
executor = ThreadPoolExecutor(max_workers=1)      # сервер слабый: одна пачка за раз
_lock = threading.Lock()
_jobs: dict[str, dict] = {}                        # прогон -> future и флаг отмены, для пульта


MAX_RESTARTS = 3


def _recover_interrupted():
    """Прогоны, оборванные перезапуском сервиса (деплой, падение), снова ставим в очередь и считаем с начала.
    Вход на диске не меняется, пайплайн воспроизводим; после MAX_RESTARTS перезапусков прогон помечается ошибкой."""
    try:
        ids = sorted(os.listdir(RUNS))
    except OSError:
        return
    stale = []
    for run_id in ids:
        if run_id == EXAMPLE_ID or not run_id.replace("-", "").isalnum():
            continue
        st = _read(run_id, "status.json")
        if st and st.get("state") in ("queued", "running"):
            stale.append((st.get("created") or 0, run_id, st))
    for _, run_id, st in sorted(stale):
        restarts = (st.get("restarts") or 0) + 1
        if restarts > MAX_RESTARTS:
            _write_status(run_id, state="error", error="прогон прерывался перезапуском сервиса слишком часто", finished=time.time())
            continue
        received = (st.get("stages") or {}).get("received")
        _write_status(run_id, state="queued", stage=None, step=None, progress=None, tally=None, recent=None, eta=None, detail="",
                      stages={"received": received} if received else {}, restarts=restarts, restarted=time.time())
        print(f"[runs] прогон {run_id} прерван перезапуском, поставлен в очередь снова ({restarts})")
        _submit(run_id)


@asynccontextmanager
async def lifespan(_app):
    _recover_interrupted()
    _seed_example()
    ask.start_worker()
    datastats.warm()                     # разбор ~500 файлов данных — заранее, а не на первом заходе
    if tgbot.start():
        print("[tg] Telegram-бот запущен")
    yield
    tgbot.stop()
    ask.stop_worker()
    executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="DXA QC · ЛЦТ 2026", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def attach_user(request: Request, call_next):
    # кто вошёл: шапка всех страниц и доступ к вопросам Claude; остальной стенд открыт без входа
    request.state.user, request.state.csrf = await run_in_threadpool(ask.current_user, request)
    response = await call_next(request)
    # без явной кодировки Safari на iPhone читает русский текст в JSON и CSV как Windows-1251 — кракозябры
    ctype = response.headers.get("content-type", "")
    if ctype.split(";")[0].strip() in ("application/json", "text/csv") and "charset" not in ctype.lower():
        response.headers["content-type"] = ctype.split(";")[0].strip() + "; charset=utf-8"
    return response


app.include_router(ask.router)
tz.setup(templates)
app.include_router(tz.router)

REGION_RU = {"lumbar_spine": "поясничный отдел", "hip_right": "правое бедро", "hip_left": "левое бедро", "unknown": "не определена"}
VIOLATION_RU = {
    "axis_tilt": "наклон оси позвоночника больше допуска",
    "coverage": "неполный охват: подвздошные кости или Th12",
    "artifact": "посторонний предмет или артефакт",
    "hip_not_evaluated_v0": "качество бедра в этой версии не оценивается",
    "hip_positioning": "бедро: позиционирование или ротация",
    "hip_roi": "бедро: поля вокруг зоны интереса",
    "other": "другое нарушение",
    "manual": "нарушение отмечено вручную",
}


def _status_path(run_id):
    return os.path.join(RUNS, run_id, "status.json")


def _write_status(run_id, **kw):
    p = _status_path(run_id)
    cur = {}
    if os.path.exists(p):
        with open(p) as f:
            cur = json.load(f)
    cur.update(kw)
    with open(p + ".tmp", "w") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def _read(run_id, name):
    if not run_id.replace("-", "").isalnum():
        raise HTTPException(404)
    p = os.path.join(RUNS, run_id, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except ValueError:  # файл дописывается старой версией или повреждён: считаем, что его ещё нет
        return None


def _process(run_id, stop: threading.Event | None = None):
    base = os.path.join(RUNS, run_id)
    st = _read(run_id, "status.json") or {}
    tracker = progress.Tracker(lambda **kw: _write_status(run_id, **kw), stages=st.get("stages"))
    try:
        if stop is not None and stop.is_set():
            _write_status(run_id, state="cancelled", finished=time.time())
            return
        _write_status(run_id, state="running", started=time.time())
        input_dir = os.path.join(base, "input")
        # архивы распаковываются здесь, в фоне, а не в запросе загрузки: страница не подвисает и видит этап
        archives = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(".zip") and os.path.isfile(os.path.join(input_dir, f)))
        if archives:
            tracker.start("unpack", total=len(archives), detail=archives[0])
            for i, name in enumerate(archives):
                path = os.path.join(input_dir, name)
                try:
                    safe_extract(path, os.path.join(input_dir, os.path.splitext(name)[0]))
                except Exception as exc:
                    raise RuntimeError(f"архив {name} не распакован: {exc}") from exc
                os.remove(path)
                tracker("unpack", i + 1, len(archives), name)
        ds = st.get("dataset")
        pipeline.run_batch(input_dir, os.path.join(base, "out"),
                           labels=datasets.load_labels(ds) if ds else None, dataset=ds, params=st.get("params"), force=bool(st.get("force")),
                           progress=tracker, should_stop=stop.is_set if stop is not None else None)
        tracker.finish()
        _write_status(run_id, state="done", finished=time.time())
    except pipeline.Cancelled:
        _write_status(run_id, state="cancelled", finished=time.time())
    except Exception as exc:
        _write_status(run_id, state="error", error=f"{type(exc).__name__}: {exc}"[:500], finished=time.time())
    finally:
        _jobs.pop(run_id, None)


def _submit(run_id):
    """Поставить прогон в очередь с флагом отмены."""
    stop = threading.Event()
    _jobs[run_id] = {"stop": stop}
    fut = executor.submit(_process, run_id, stop)
    if run_id in _jobs:
        _jobs[run_id]["future"] = fut
    return fut


def _cancel(run_id) -> bool:
    """Отменить прогон: в очереди снимается сразу, при обработке останавливается перед следующим снимком."""
    job = _jobs.get(run_id)
    if not job:
        return False
    job["stop"].set()
    fut = job.get("future")
    if fut is not None and fut.cancel():
        _jobs.pop(run_id, None)
        _write_status(run_id, state="cancelled", finished=time.time())
    return True


def _new_run(title, run_id=None):
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    os.makedirs(os.path.join(RUNS, run_id, "input"), exist_ok=True)
    now = time.time()
    _write_status(run_id, state="queued", title=title, created=now, stages={"received": {"start": now, "end": now}})
    return run_id


def _has_archives(run_id) -> bool:
    d = os.path.join(RUNS, run_id, "input")
    return any(f.lower().endswith(".zip") for f in os.listdir(d)) if os.path.isdir(d) else False


def _queue_position(run_id, created) -> int:
    """Сколько прогонов обрабатывается или стоит в очереди раньше этого."""
    n = 0
    for rid in os.listdir(RUNS):
        if rid == run_id or not rid.replace("-", "").isalnum():
            continue
        s = _read(rid, "status.json") or {}
        if s.get("state") in ("queued", "running") and s.get("created", 0) <= created:
            n += 1
    return n


def _progress_payload(run_id) -> dict:
    st = _read(run_id, "status.json")
    if not st:
        raise HTTPException(404, "прогон не найден")
    ds = st.get("dataset")
    has_labels = bool(ds and (datasets.REGISTRY.get(ds) or {}).get("labels"))
    stages = st.get("stages") or {}
    out = {k: st.get(k) for k in ("state", "title", "stage", "step", "progress", "detail", "tally", "recent", "eta", "error",
                                  "created", "started", "finished")}
    out.update(run_id=run_id, stages=stages,
               stage_list=progress.stage_plan(bool(st.get("has_archives")) or "unpack" in stages, has_labels or "evaluate" in stages))
    if st.get("state") == "queued":
        out["queue_position"] = _queue_position(run_id, st.get("created", 0))
    return out


def _seed_example():
    if not SEED or not os.path.exists(SEED):
        return
    st = _read(EXAMPLE_ID, "status.json")
    if not (st and st.get("state") == "done" and st.get("version") == __version__):
        shutil.rmtree(os.path.join(RUNS, EXAMPLE_ID), ignore_errors=True)
        _new_run("Пример: «Для теста.zip» от организаторов", EXAMPLE_ID)
        safe_extract(SEED, os.path.join(RUNS, EXAMPLE_ID, "input"))
        _write_status(EXAMPLE_ID, version=__version__)
        _submit(EXAMPLE_ID)
    executor.submit(_warm_tts, EXAMPLE_ID)


def _warm_tts(run_id):
    """Заранее озвучиваем пояснения примера, чтобы рассказ на стенде начинался без ожидания синтеза."""
    if not voice.status()["tts"]:
        return
    man = _read(run_id, os.path.join("out", "manifest.json")) or {}
    for r in man.get("rows", []):
        for g in r.get("regions") or []:
            try:
                voice.tts_wav(g["text"], TTS_CACHE)
            except Exception as exc:
                print(f"[tts] прогрев озвучки не удался: {exc}")
                return


def _list_runs(limit: int = 30):
    out = []
    for rid in sorted(os.listdir(RUNS), reverse=True):
        st = _read(rid, "status.json")
        if not st:
            continue
        man = _read(rid, os.path.join("out", "manifest.json")) or {}
        # московское время без tzdata в образе: у Москвы нет перехода на летнее время, сдвиг всегда +3 часа
        created_str = time.strftime("%d.%m %H:%M", time.gmtime(st.get("created", 0) + 3 * 3600)) if st.get("created") else ""
        out.append(dict(id=rid, **st, summary=man.get("summary", {}), created_str=created_str,
                        params_desc=P.describe(st.get("params"))))
    out.sort(key=lambda r: (r["id"] != EXAMPLE_ID, -r.get("created", 0)))
    return out[:limit]


async def _save_uploads(files: list[UploadFile], dest: str):
    n = 0
    for uf in files:
        name = os.path.basename(uf.filename or f"file{n}")
        if not name:
            continue
        path = os.path.join(dest, name)
        with open(path, "wb") as out:
            while chunk := await uf.read(1024 * 1024):
                out.write(chunk)
        n += 1  # архивы распаковывает _process в фоне
    return n


# ------------------------------------------------------------------ страницы

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    runs = _list_runs()
    # самый свежий готовый прогон всего обучающего набора: на нём интервалы и графики точности
    train_run = next((r["id"] for r in runs if r.get("dataset") == "train" and r.get("state") == "done"
                      and r.get("summary", {}).get("studies", 0) >= 90), None)
    design = request.query_params.get("design") or HOME_DESIGN
    return templates.TemplateResponse(request, "index_classic.html" if design == "classic" else "index.html",
                                      dict(runs=runs, datasets=datasets.available(), train_run=train_run,
                                           hero=_hero(), facts=_facts(train_run), trac_url=TRAC_URL, version=__version__,
                                           showcase=_showcase(train_run)))


def _showcase(train_run):
    """Примеры снимков для загрузки: прогон примера и последний прогон всего обучающего набора."""
    sources = [(EXAMPLE_ID, _read(EXAMPLE_ID, os.path.join("out", "manifest.json")))]
    if train_run:
        sources.append((train_run, _read(train_run, os.path.join("out", "manifest.json"))))
    return showcase.pick(sources)


@app.get("/showcase/{run_id}/{key}.jpg", include_in_schema=False)
def showcase_frame(run_id: str, key: str):
    if not key.isalnum() or not run_id.replace("-", "").isalnum():
        raise HTTPException(404)
    cache = os.path.join(DATA, "showcase", f"v{showcase.VERSION}", f"{run_id}_{key}.jpg")
    if not os.path.isfile(cache):
        man = _read(run_id, os.path.join("out", "manifest.json")) or {}
        row = next((r for r in man.get("rows", []) if r.get("key") == key and r.get("original_png")), None)
        src = os.path.join(RUNS, run_id, "out", row["original_png"]) if row else ""
        if not row or not os.path.isfile(src):
            raise HTTPException(404, "кадр не найден")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        showcase.stylize(src).save(cache + ".tmp", "JPEG", quality=86, optimize=True, progressive=True)
        os.replace(cache + ".tmp", cache)
    return FileResponse(cache, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


def _hero():
    """Снимок позвоночника из прогона примера для визуализации на главной; None, если примера нет."""
    man = _read(EXAMPLE_ID, os.path.join("out", "manifest.json"))
    row = next((r for r in (man or {}).get("rows", [])
                if r.get("anatomical_region") == "lumbar_spine" and r.get("atlas") and r.get("metrics")), None)
    if not row:
        return None
    codes = row.get("violation_list") or []
    return dict(run_id=EXAMPLE_ID, key=row["key"], image=row["overlay_png"], quality_class=row.get("quality_class"),
                angle=row["metrics"].get("abs_angle", 0.0), axis_limit=P.normalize(man.get("params"))["axis_limit_deg"],
                axis_ok="axis_tilt" not in codes, iliac_ok="coverage" not in codes,
                levels=[g["key"] for g in row.get("regions") or [] if g.get("key") in ("Th12", "L1", "L2", "L3", "L4", "L5")],
                seconds=row.get("time_of_processing", 0.0),
                callouts=row.get("callouts") if row.get("layers") else None)


def _facts(train_run):
    """Факты для первого экрана по прогону всего обучающего набора."""
    if not train_run:
        return None
    man = _read(train_run, os.path.join("out", "manifest.json")) or {}
    ev = man.get("evaluation") or {}
    return dict(images=(man.get("summary") or {}).get("images", 0), seconds=round((man.get("summary") or {}).get("wall_time", 0)),
                studies=ev.get("spine_studies", 0), f1=f"{(ev.get('spine_overall') or {}).get('f1', 0):.2f}")


@app.post("/runs/dataset")
def create_dataset_run(dataset: str = Form(...), mode: str = Form("all"), n: int = Form(10), study: str = Form("")):
    meta = datasets.REGISTRY.get(dataset)
    if not meta:
        raise HTTPException(400, "неизвестный набор данных")
    what = {"all": "весь набор", "sample": f"случайные {n}", "study": "одно исследование"}.get(mode, mode)
    run_id = _new_run(f"{meta['title']}: {what}")
    try:
        chosen = datasets.link_selection(dataset, mode, os.path.join(RUNS, run_id, "input"), n=n, study=study)
    except Exception as exc:
        _write_status(run_id, state="error", error=str(exc)[:300])
        return RedirectResponse(f"/runs/{run_id}", status_code=303)
    _write_status(run_id, dataset=dataset, studies=len(chosen), has_labels=bool(meta.get("labels")))
    _submit(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.get("/api/datasets")
def api_datasets():
    return [dict(d, studies=None) for d in datasets.available()]


@app.get("/api/datasets/{ds_id}/studies")
def api_dataset_studies(ds_id: str):
    if ds_id not in datasets.REGISTRY:
        raise HTTPException(404)
    return datasets.studies(ds_id)


@app.post("/runs")
async def create_run(files: list[UploadFile] = File(...)):
    run_id = _new_run("Загрузка " + time.strftime("%d.%m %H:%M"))
    try:
        n = await _save_uploads(files, os.path.join(RUNS, run_id, "input"))
    except Exception as exc:
        _write_status(run_id, state="error", error=f"не удалось принять файлы: {exc}"[:300])
        return RedirectResponse(f"/runs/{run_id}", status_code=303)
    if n == 0:
        _write_status(run_id, state="error", error="файлы не выбраны")
    else:
        _write_status(run_id, has_archives=_has_archives(run_id))
        _submit(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    st = _read(run_id, "status.json")
    if not st:
        raise HTTPException(404, "прогон не найден")
    man = _read(run_id, os.path.join("out", "manifest.json"))
    if man:  # пояснения зон нужны только карточке, на странице прогона они раздували бы встроенный JSON
        man["rows"] = [{k: v for k, v in r.items() if k not in ("regions", "layers", "callouts")} for r in man["rows"]]
    live = _progress_payload(run_id) if st.get("state") in ("queued", "running") else None
    return templates.TemplateResponse(request, "run.html", dict(run_id=run_id, st=st, man=man, region_ru=REGION_RU,
                                                                violation_ru=VIOLATION_RU, trac_url=TRAC_URL, version=__version__,
                                                                params_desc=P.describe(man.get("params")) if man else "", live=live,
                                                                user=request.state.user, csrf=request.state.csrf,
                                                                requests=analysis.requests_by_target(run_id, request.state.user) if man else {},
                                                                organizer=analysis.organizer_run(run_id, st),
                                                                **_run_og(run_id, st, man)))


def _partial_rows(run_id) -> list[dict]:
    """Строки снимков, уже проанализированных в идущем или прерванном прогоне; недописанная последняя строка пропускается."""
    rows = []
    try:
        with open(os.path.join(RUNS, run_id, "out", pipeline.PARTIAL), encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    break
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    break
    except OSError:
        pass
    return rows


@app.get("/runs/{run_id}/images/{key}", response_class=HTMLResponse)
def card_page(request: Request, run_id: str, key: str):
    man = _read(run_id, os.path.join("out", "manifest.json"))
    row = next((r for r in man["rows"] if r.get("key") == key), None) if man else None
    st, preliminary = None, False
    if row is None:
        # прогон ещё идёт: результат снимка уже на диске, таблиц и manifest.json пока нет
        st = _read(run_id, "status.json")
        row = next((r for r in _partial_rows(run_id) if r.get("key") == key), None) if st else None
        if not row:
            raise HTTPException(404, "снимок не найден")
        man, preliminary = None, True
    user = request.state.user
    return templates.TemplateResponse(request, "card.html", dict(
        run_id=run_id, row=row, man=man, region_ru=REGION_RU, violation_ru=VIOLATION_RU, trac_url=TRAC_URL, version=__version__,
        is_admin=bool(user and user.get("is_admin")), csrf=request.state.csrf, spec=P.SPEC,
        run_params=P.normalize((man or st or {}).get("params")), override_codes=pipeline.OVERRIDE_CODES,
        preliminary=preliminary, run_state=(st or {}).get("state"), **_card_og(run_id, row),
        user=user, st=st or _read(run_id, "status.json") or {}, requests=analysis.requests_by_target(run_id, user),
        organizer=analysis.organizer_run(run_id, st or _read(run_id, "status.json"))))


@app.get("/runs/{run_id}/files/{name}")
def run_file(run_id: str, name: str):
    if "/" in name or name.startswith(".") or not run_id.replace("-", "").isalnum():
        raise HTTPException(404)
    p = os.path.join(RUNS, run_id, "out", name)
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p, filename=name if not name.endswith(".png") else None)


# ------------------------------------------------------------------ API

STATIC = os.path.join(os.path.dirname(__file__), "static")
_ICONS = {"favicon.ico": "image/x-icon", "favicon.svg": "image/svg+xml", "apple-touch-icon.png": "image/png"}
app.mount("/static", StaticFiles(directory=STATIC), name="static")  # шрифты: вёрстка одинакова на всех платформах


def _icon(name):
    return FileResponse(os.path.join(STATIC, name), media_type=_ICONS[name], headers={"Cache-Control": "public, max-age=604800"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    return _icon("favicon.ico")


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg():
    return _icon("favicon.svg")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return _icon("apple-touch-icon.png")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/voice")
def api_voice():
    """Какие голосовые функции есть в этой сборке."""
    return voice.status()


@app.get("/api/tts")
def api_tts(text: str):
    """Озвучка текста локальным синтезом Piper, ответ WAV."""
    text = text.strip()
    if not text or len(text) > voice.MAX_TEXT:
        raise HTTPException(400, "текст пустой или слишком длинный")
    if not voice.status()["tts"]:
        raise HTTPException(503, "озвучка в этой сборке не установлена")
    path = voice.tts_wav(text, TTS_CACHE)
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})


_AUDIO_SUFFIX = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4", "audio/mpeg": ".mp3",
                 "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/aac": ".aac"}


@app.post("/api/stt")
async def api_stt(file: UploadFile = File(...)):
    """Распознавание голосового вопроса локальным Whisper, ответ {"text": ...}."""
    if not voice.status()["stt"]:
        raise HTTPException(503, "распознавание речи в этой сборке не установлено")
    data = await file.read(voice.MAX_AUDIO + 1)
    if not data:
        raise HTTPException(400, "пустая запись")
    if len(data) > voice.MAX_AUDIO:
        raise HTTPException(413, "запись слишком длинная")
    suffix = _AUDIO_SUFFIX.get((file.content_type or "").split(";")[0].strip(), ".webm")
    try:
        text = await run_in_threadpool(voice.transcribe, data, suffix)
    except Exception as exc:
        raise HTTPException(422, f"не удалось разобрать запись: {type(exc).__name__}")
    return {"text": text}


@app.post("/api/batch")
async def api_batch(files: list[UploadFile] = File(...), wait: bool = True):
    """Пакетная обработка: zip или набор DICOM. При wait=true ответ приходит после обработки."""
    run_id = _new_run("API " + time.strftime("%d.%m %H:%M"))
    n = await _save_uploads(files, os.path.join(RUNS, run_id, "input"))
    if n == 0:
        raise HTTPException(400, "файлы не переданы")
    _write_status(run_id, has_archives=_has_archives(run_id))
    fut = _submit(run_id)
    if wait:
        fut.result()
    return JSONResponse(_api_run(run_id))


def _api_run(run_id):
    st = _read(run_id, "status.json") or {}
    man = _read(run_id, os.path.join("out", "manifest.json")) or {}
    base = f"/runs/{run_id}/files"
    return {"run_id": run_id, "state": st.get("state"), "error": st.get("error"),
            "summary": man.get("summary"), "rows": man.get("rows"),
            "results_csv": f"{base}/results.csv", "results_xlsx": f"{base}/results.xlsx",
            "overlays_zip": f"{base}/overlays.zip", "page": f"/runs/{run_id}"}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str, pretty: bool = False):
    """Результат прогона. pretty=true — с отступами, для чтения глазами в браузере."""
    if not _read(run_id, "status.json"):
        raise HTTPException(404)
    if pretty:
        return Response(json.dumps(_api_run(run_id), ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8")
    return _api_run(run_id)


@app.get("/api/runs/{run_id}/progress")
def api_progress(run_id: str):
    """Ход прогона без строк результата: этапы, прогресс, счётчики, последние снимки, позиция в очереди."""
    return JSONResponse(_progress_payload(run_id), headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ превью ссылок (OpenGraph)

def _card_texts(row: dict) -> tuple[str, list[str], str]:
    region = REGION_RU.get(row.get("anatomical_region"), "снимок").capitalize()
    viol = [VIOLATION_RU.get(v, v) for v in row.get("violation_list") or [] if not str(v).startswith("hip_not")]
    notes = viol or [e for e in (row.get("explanations") or [])[1:] if e][:3]
    return region, notes, os.path.basename(row.get("path_to_study") or "")


def _card_og(run_id: str, row: dict) -> dict:
    region, notes, name = _card_texts(row)
    verdict = {0: "качественное", 1: "нарушение"}.get(row.get("quality_class"), "не оценено")
    lead = ("Нарушения: " + "; ".join(notes) + ".") if row.get("violation_list") and row.get("quality_class") == 1 else " ".join(notes)
    return dict(og_title=f"{region}: {verdict} · DXA QC", og_description=f"{lead} {name}".strip()[:300],
                og_image=f"/runs/{run_id}/images/{row.get('key')}/og.jpg" if row.get("key") else None)


def _run_og(run_id: str, st: dict, man: dict | None) -> dict:
    s = (man or {}).get("summary") or {}
    if man:
        desc = (f"{s.get('studies', 0)} исследований, {s.get('images', 0)} снимков: {s.get('good', 0)} качественных, "
                f"{s.get('bad', 0)} с нарушением, {s.get('not_evaluated', 0)} не оценено.")
    else:
        desc = "Идёт обработка: этапы, счётчики и результаты снимков по мере анализа."
    return dict(og_title=f"{st.get('title') or run_id} · DXA QC", og_description=desc, og_image=f"/runs/{run_id}/og.jpg")


def _jpeg(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88, optimize=True, progressive=True)
    return buf.getvalue()


def _og_response(build, cache_path: str | None):
    """Картинка превью; готовые прогоны кэшируются на диске, идущие рисуются заново."""
    headers = {"Cache-Control": "public, max-age=600"}
    if cache_path and os.path.isfile(cache_path):
        return FileResponse(cache_path, media_type="image/jpeg", headers=headers)
    data = _jpeg(build())
    if cache_path:
        with open(cache_path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(cache_path + ".tmp", cache_path)
    return Response(data, media_type="image/jpeg", headers=headers)


@app.get("/runs/{run_id}/images/{key}/clean.png", include_in_schema=False)
def clean_atlas(run_id: str, key: str):
    """Атлас без впечатанных подписей, шапки и легенды — подложка компонента atlas-callouts (macros/atlas_callouts.html)."""
    if not key.isalnum():
        raise HTTPException(404)
    out = os.path.join(RUNS, run_id, "out")
    cache = os.path.join(out, f"{key}_clean.png")
    if not os.path.isfile(cache):
        man = _read(run_id, os.path.join("out", "manifest.json"))
        row = next((r for r in (man["rows"] if man else _partial_rows(run_id)) if r.get("key") == key), None)
        layers = {l["name"]: l for l in (row or {}).get("layers") or []}
        if "frame" not in layers or "image" not in layers:
            raise HTTPException(404, "у снимка нет слоёв атласа")
        atlas.compose_clean(out, layers).save(cache + ".tmp", "PNG", optimize=True)
        os.replace(cache + ".tmp", cache)
    return FileResponse(cache, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/runs/{run_id}/images/{key}/og.jpg", include_in_schema=False)
def card_og(run_id: str, key: str):
    if not key.isalnum():
        raise HTTPException(404)
    man = _read(run_id, os.path.join("out", "manifest.json"))
    row = next((r for r in (man["rows"] if man else _partial_rows(run_id)) if r.get("key") == key), None)
    if not row:
        raise HTTPException(404, "снимок не найден")
    out = os.path.join(RUNS, run_id, "out")
    region, notes, name = _card_texts(row)
    build = lambda: og.card(os.path.join(out, row.get("overlay_png") or "-"), region, row.get("quality_class"), notes, name)
    return _og_response(build, os.path.join(out, f"og_{key}_v{og.VERSION}.jpg") if man else None)


@app.get("/runs/{run_id}/og.jpg", include_in_schema=False)
def run_og(run_id: str):
    st = _read(run_id, "status.json")
    if not st:
        raise HTTPException(404, "прогон не найден")
    man = _read(run_id, os.path.join("out", "manifest.json"))
    out = os.path.join(RUNS, run_id, "out")
    if man:
        summary, rows, state = man["summary"], man["rows"], ""
    else:
        rows, t, pr = _partial_rows(run_id), st.get("tally") or {}, st.get("progress") or {}
        summary = dict(images=pr.get("done", 0), good=t.get("good", 0), bad=t.get("bad", 0), not_evaluated=t.get("na", 0) + t.get("failed", 0))
        state = {"queued": "в очереди", "running": f"идёт обработка: {pr.get('done', 0)} из {pr.get('total', 0)}",
                 "error": "обработка остановилась с ошибкой", "cancelled": "прогон отменён"}.get(st.get("state"), "")
    order = sorted((r for r in rows if r.get("thumb_png")), key=lambda r: {1: 0, 0: 1}.get(r.get("quality_class"), 2))
    thumbs = [os.path.join(out, r["thumb_png"]) for r in order[:8]]
    build = lambda: og.run(st.get("title") or run_id, summary, thumbs, state)
    return _og_response(build, os.path.join(out, f"og_run_v{og.VERSION}.jpg") if man and st.get("state") == "done" else None)


@app.get("/tz/data", include_in_schema=False)
def data_short():
    return RedirectResponse("/tz/data.html", status_code=301)


@app.get("/tz/data.html", response_class=HTMLResponse)
def data_page(request: Request):
    """Данные задачи: состав наборов, разметка экспертов, технические параметры — только агрегаты."""
    d = datastats.get()
    ev, train_id = None, None
    for r in _list_runs(300):
        if r.get("dataset") == "train" and r.get("state") == "done" and (r.get("summary") or {}).get("studies", 0) >= 90:
            man = _read(r["id"], os.path.join("out", "manifest.json")) or {}
            ev, train_id = man.get("evaluation"), r["id"]
            break
    example = _read(EXAMPLE_ID, os.path.join("out", "manifest.json")) or {}
    thumbs = [dict(key=r["key"], thumb=r.get("thumb_png") or r.get("overlay_png"), region=REGION_RU.get(r.get("anatomical_region"), ""),
                   name=os.path.basename(r.get("path_to_study") or ""))
              for r in example.get("rows", []) if r.get("key") and (r.get("thumb_png") or r.get("overlay_png"))]
    t = (d.get("train") or {})
    return templates.TemplateResponse(request, "tz_data.html", dict(
        d=d, ev=ev, train_id=train_id, thumbs=thumbs, example_id=EXAMPLE_ID, version=__version__,
        og_title="Данные задачи 04 · DXA QC", og_image="/og/data.jpg",
        og_description=(f"Данные организатора: {t.get('studies', 0)} исследований, {t.get('unique', 0)} уникальных снимков "
                        f"из {t.get('files', 0)} файлов, экспертная разметка по 10 критериям и технические параметры."
                        if d.get("ok") else "Данные организатора задачи 04: состав, разметка экспертов, технические параметры.")))


@app.get("/cookies", response_class=HTMLResponse)
def cookies_page(request: Request):
    """Что стенд хранит в браузере: одна техническая cookie входа, настройки в localStorage, никакой аналитики."""
    return templates.TemplateResponse(request, "cookies.html", dict(
        version=__version__, trac_url=TRAC_URL, session_days=round(accounts.SESSION_TTL / 86400),
        og_description="Какие cookie ставит стенд контроля качества денситометрии, зачем и на какой срок: "
                       "одна техническая cookie входа, аналитики и сторонних трекеров нет."))


@app.get("/og.jpg", include_in_schema=False)
def site_og():
    man = _read(EXAMPLE_ID, os.path.join("out", "manifest.json")) or {}
    row = next((r for r in man.get("rows", []) if r.get("anatomical_region") == "lumbar_spine" and r.get("overlay_png")), None)
    example = os.path.join(RUNS, EXAMPLE_ID, "out", row["overlay_png"]) if row else None
    cache = os.path.join(RUNS, EXAMPLE_ID, "out", f"og_site_v{og.VERSION}.jpg") if row else None
    return _og_response(lambda: og.site(example), cache)


# страницы без собственной картинки: карточка с заголовком, счётчиками и мотивом — чтобы ссылка узнавалась в Telegram
OG_PAGES = ("tz", "mindmap", "mlmap", "gantt", "roadmap", "data", "control", "ask")


def _og_page(key: str):
    if key == "tz":
        return og.page("Документы задачи 04", [
            "техническое задание ДепЗдрава постранично",
            "mind map требований со статусом на стенде",
            "интерактивная шпаргалка scikit-learn для задачи",
        ], "docs", [("документов", len(tz._docs()), og.WHITE)])
    if key == "mindmap":
        from dxaqc.web import tz_mindmap as MM
        c = MM.counts()
        return og.page("Mind map ТЗ задачи 04", [
            "все требования ТЗ деревом, с номерами страниц",
            "у каждого пункта — статус на стенде и что именно сделано",
        ], "tree", [("сделано", c["done"], (70, 205, 100)), ("частично", c["partial"], (232, 170, 60)),
                    ("не сделано", c["todo"], og.MUTED)])
    if key == "mlmap":
        from dxaqc.web import ml_map as ML
        est = ML.estimators()
        hot = sum(1 for e in est if e.get("perspective") in ("high", "mid"))
        return og.page("Шпаргалка scikit-learn для задачи 04", [
            "карта выбора алгоритма для контроля качества денситометрии",
            "по каждому: используется ли на стенде и насколько перспективен",
        ], "scatter", [("алгоритмов", len(est), og.WHITE), ("перспективных", hot, og.ACCENT)])
    if key == "gantt":
        from dxaqc.web import gantt as G
        c = G.data()["counts"]
        return og.page("Диаграмма Ганта проекта", [
            "задачи трекера по эпикам: когда заведены и когда закрыты",
            "вехи со сроками и признаком достижения, линия сегодня",
        ], "gantt", [("задач закрыто", c["closed"], (70, 205, 100)), ("в работе", c["open"], og.ACCENT),
                     ("вех достигнуто", c["reached"], (232, 170, 60))])
    if key == "data":
        d = datastats.get()
        t = d.get("train") or {}
        return og.page("Данные задачи 04", [
            "обучающий набор организатора и фрагмент «Для теста»",
            "разметка экспертов, дубли, технические параметры снимков",
        ], "gantt", [("исследований", t.get("studies", 0), og.WHITE), ("уникальных снимков", t.get("unique", 0), og.ACCENT),
                     ("лишних копий", t.get("extra", 0), (232, 170, 60))])
    if key == "roadmap":
        from dxaqc.web import roadmap as RM
        t = RM.build({})["totals"]
        return og.page("Роудмап развития", [
            "шесть направлений: качество анализа, ТЗ, защита, работа врача",
            f"рекомендуемый путь: агент {t['path_agent']}, человек {t['path_human']}",
        ], "roadmap", [("инициатив", t["items"], og.WHITE), ("шагов пути", t["path"], og.ACCENT),
                       ("высокий эффект", t["high"], (70, 205, 100))])
    if key == "control":
        return og.page("Пульт анализа", [
            "пороги и параметры разбора меняются без пересборки сервиса",
            "перезапуск прогона с новыми параметрами, очередь и отмена",
            "правка вердикта снимка и пробный анализ",
        ], "sliders")
    if key == "ask":
        return og.page("Спросить Claude о сервисе", [
            "вопрос по коду и данным стенда прямо из браузера",
            "отвечает Claude через Codellake по копии проекта",
            "лимиты и одобрение админом, снимки наружу не уходят",
        ], "chat")
    raise HTTPException(404)


@app.get("/og/{key}.jpg", include_in_schema=False)
def page_og(key: str):
    if key not in OG_PAGES:
        raise HTTPException(404)
    folder = os.path.join(DATA, "og")
    os.makedirs(folder, exist_ok=True)
    return _og_response(lambda: _og_page(key), os.path.join(folder, f"page_{key}_v{og.VERSION}.jpg"))


LIVE_FIELDS = ("key", "path_to_study", "anatomical_region", "quality_class", "violation_list", "processing_status",
               "explanations", "overlay_png", "thumb_png", "time_of_processing")
LIVE_PAGE = 500


@app.get("/api/runs/{run_id}/live-rows")
def api_live_rows(run_id: str, after: int = 0):
    """Снимки прогона после номера after: пока прогон идёт — по мере анализа, после — итоговые строки (final=true)."""
    st = _read(run_id, "status.json")
    if not st:
        raise HTTPException(404, "прогон не найден")
    man = _read(run_id, os.path.join("out", "manifest.json"))
    rows = man["rows"] if man else _partial_rows(run_id)
    start = max(0, after)
    part = [dict({k: r.get(k) for k in LIVE_FIELDS}, n=i + 1) for i, r in enumerate(rows[start:start + LIVE_PAGE], start)]
    return JSONResponse(dict(state=st.get("state"), final=bool(man), total=len(rows), rows=part),
                        headers={"Cache-Control": "no-store"})


@app.get("/api/runs/{run_id}/events")
async def api_events(run_id: str, request: Request):
    """Ход прогона потоком Server-Sent Events: событие progress при каждом изменении, поток закрывается по завершении."""
    _progress_payload(run_id)  # 404 сразу, до открытия потока

    async def stream():
        last, pinged, t0 = None, time.time(), time.time()
        while time.time() - t0 < 3600:
            if await request.is_disconnected():
                return
            try:
                payload = await run_in_threadpool(_progress_payload, run_id)
            except HTTPException:  # прогон удалили
                return
            data = json.dumps(payload, ensure_ascii=False)
            if data != last:
                last, pinged = data, time.time()
                yield f"event: progress\ndata: {data}\n\n"
            elif time.time() - pinged > 15:
                pinged = time.time()
                yield ": ping\n\n"
            if payload.get("state") in ("done", "error", "cancelled"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# пульт анализа получает доступ к прогонам через эти функции, чтобы не импортировать app и не зациклиться
control.setup(templates=templates, runs_dir=RUNS, read=_read, write_status=_write_status, new_run=_new_run, submit=_submit,
              cancel=_cancel, list_runs=_list_runs, region_ru=REGION_RU, violation_ru=VIOLATION_RU, trac_url=TRAC_URL,
              example_id=EXAMPLE_ID)
app.include_router(control.router)
analysis.setup(read=_read, new_run=_new_run, write_status=_write_status, submit=_submit, runs_dir=RUNS, data_dir=DATA,
               example_id=EXAMPLE_ID)
app.include_router(analysis.router)
mcp.setup(read=_read, new_run=_new_run, write_status=_write_status, submit=_submit, runs_dir=RUNS, list_runs=_list_runs,
          has_archives=_has_archives, progress_payload=_progress_payload, partial_rows=_partial_rows, datasets=datasets,
          columns=pipeline.COLUMNS, region_ru=REGION_RU, violation_ru=VIOLATION_RU, public_url=PUBLIC_URL, templates=templates,
          trac_url=TRAC_URL)
app.include_router(mcp.router)
tgbot.setup(read=_read, new_run=_new_run, write_status=_write_status, submit=_submit, runs_dir=RUNS, list_runs=_list_runs,
            has_archives=_has_archives, progress_payload=_progress_payload, datasets=datasets, region_ru=REGION_RU,
            violation_ru=VIOLATION_RU, public_url=PUBLIC_URL, templates=templates)
analysis.ctx["notify"] = tgbot.notify_request
app.include_router(tgbot.router)
