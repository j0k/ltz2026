# -*- coding: utf-8 -*-
"""MCP-сервер стенда: Model Context Protocol поверх Streamable HTTP на /mcp.

Клиент (Claude Code, Claude Desktop, Cursor и другие) отправляет JSON-RPC 2.0 методом POST с заголовком
«Authorization: Bearer dxq_…». Токены выдают админы в /admin/mcp: права read (результаты) или analyze
(ещё и запуск анализа), срок и суточный лимит вызовов инструментов. Каждый запрос пишется в журнал
api_usage — из него страница админа строит подробную статистику.

Ответы — обычный JSON без потока SSE (спецификация это разрешает); сессия Mcp-Session-Id выдаётся при
initialize и нужна только для статистики клиентов. Атлас снимков организатора через MCP не передаётся:
клиент обычно пересылает картинки своей модели во внешний сервис.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from collections import Counter

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from dxaqc import __version__
from dxaqc.web import accounts as A
from dxaqc.web import activity
from dxaqc.web import analysis, ask

router = APIRouter(include_in_schema=False)
ctx: dict = {}

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_BODY = 40 * 1024 * 1024
MAX_FILES_BYTES = 30 * 1024 * 1024
WAIT_MAX = 170
KEY_RE = re.compile(r"^[A-Za-z0-9]{1,40}$")
RUN_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
INSTRUCTIONS = ("Kostik — контроль качества денситометрии DXA (ЛЦТ 2026, задача 04 Департамента здравоохранения Москвы). "
                "Сервис по DICOM определяет область (поясничный отдел, правое или левое бедро), выносит вердикт качества и объясняет "
                "нарушения. Порядок: analyze_dataset или analyze_files запускают прогон и сразу возвращают run_id; get_run показывает ход; "
                "get_results и get_image отдают результаты. Версия на правилах: результаты для отладки стенда, не для клинических выводов.")


def setup(**kw):
    """read, new_run, write_status, submit, runs_dir, list_runs, has_archives, progress_payload, partial_rows, datasets,
    columns, region_ru, violation_ru, public_url, templates, trac_url — функции и настройки приложения."""
    ctx.update(kw)


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class ToolError(Exception):
    """Ошибка, которую видит модель: результат инструмента с isError=true."""


def _url(path: str) -> str:
    return ctx["public_url"] + path


# ------------------------------------------------------------------ инструменты

def _schema(props: dict | None = None, required: list | None = None) -> dict:
    s = {"type": "object", "properties": props or {}, "additionalProperties": False}
    if required:
        s["required"] = required
    return s


TOOLS = [
    dict(name="service_info", scope="read", title="О сервисе",
         description="Версия сервиса, что он проверяет, какие файлы принимает, столбцы результата по ТЗ, права и лимит токена.",
         inputSchema=_schema()),
    dict(name="list_datasets", scope="read", title="Наборы организатора",
         description="Наборы данных организатора, которые можно проверить без загрузки файлов: фрагмент «Для теста» и обучающий набор "
                     "с экспертной разметкой.",
         inputSchema=_schema({"with_studies": {"type": "boolean", "default": False,
                                               "description": "вернуть идентификаторы исследований для analyze_dataset с mode=study"}})),
    dict(name="list_runs", scope="read", title="Прогоны",
         description="Последние прогоны стенда: run_id, название, состояние, число снимков и вердиктов.",
         inputSchema=_schema({"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}})),
    dict(name="analyze_dataset", scope="analyze", title="Проверить набор организатора",
         description="Запускает прогон на наборе организатора и сразу возвращает run_id. Ход — get_run, результаты — get_results. "
                     "Весь обучающий набор (100 исследований) считается около полутора минут.",
         inputSchema=_schema({"dataset": {"type": "string", "enum": ["test", "train"]},
                              "mode": {"type": "string", "enum": ["all", "sample", "study"], "default": "sample"},
                              "n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10,
                                    "description": "сколько случайных исследований для mode=sample"},
                              "study": {"type": "string", "description": "идентификатор исследования для mode=study"}}, ["dataset"])),
    dict(name="analyze_files", scope="analyze", title="Проверить свои файлы",
         description="Проверяет переданные файлы: DICOM денситометрии DXA или zip-архив с папками исследований, содержимое в base64, "
                     "суммарно до 30 МБ. Картинки, обычный рентген, КТ и МРТ получают отказ с причиной. wait=true ждёт результата "
                     "до 170 секунд, иначе ответ сразу с run_id.",
         inputSchema=_schema({"files": {"type": "array", "minItems": 1, "maxItems": 200,
                                        "items": {"type": "object", "additionalProperties": False, "required": ["name", "content_base64"],
                                                  "properties": {"name": {"type": "string"}, "content_base64": {"type": "string"}}}},
                              "wait": {"type": "boolean", "default": False},
                              "title": {"type": "string", "description": "название прогона на стенде"}}, ["files"])),
    dict(name="get_run", scope="read", title="Ход и итоги прогона",
         description="Состояние прогона: этап, прогресс, счётчики вердиктов, оценка оставшегося времени; после завершения — итоги, "
                     "сравнение с экспертами и ссылки на таблицы csv и xlsx.",
         inputSchema=_schema({"run_id": {"type": "string"}}, ["run_id"])),
    dict(name="get_results", scope="read", title="Результаты по снимкам",
         description="Строки результата по снимкам в формате ТЗ (path_to_study, study_uid, image_uid, anatomical_region, quality_class, "
                     "violation_type, processing_status, time_of_processing) с пояснениями и ссылкой на карточку. Работает и во время прогона.",
         inputSchema=_schema({"run_id": {"type": "string"},
                              "filter": {"type": "string", "enum": ["all", "good", "bad", "not_evaluated", "failed"], "default": "all"},
                              "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                              "offset": {"type": "integer", "minimum": 0, "default": 0}}, ["run_id"])),
    dict(name="get_image", scope="read", title="Результат снимка",
         description="Подробный результат одного снимка по key из get_results: вердикт, нарушения, пояснения, измерения, ссылка на "
                     "интерактивную карточку. include_atlas=true добавляет картинку разметки PNG, кроме снимков организатора.",
         inputSchema=_schema({"run_id": {"type": "string"}, "key": {"type": "string"},
                              "include_atlas": {"type": "boolean", "default": False}}, ["run_id", "key"])),
]
TOOL_BY_NAME = {t["name"]: t for t in TOOLS}


def _run_state(run_id) -> dict:
    run_id = str(run_id or "")
    st = ctx["read"](run_id, "status.json") if RUN_RE.match(run_id) else None
    if not st:
        raise ToolError(f"прогон {run_id or '(пусто)'} не найден — список в list_runs")
    return st


def _rows(run_id: str) -> tuple[list[dict], bool]:
    man = ctx["read"](run_id, os.path.join("out", "manifest.json"))
    return (man["rows"], True) if man else (ctx["partial_rows"](run_id), False)


def t_service_info(args, token):
    return dict(service="Kostik — контроль качества денситометрии", version=__version__,
                task="ЛЦТ 2026, задача 04 Департамента здравоохранения Москвы",
                checks={"lumbar_spine": "поясничный отдел: наклон оси (допуск 5°), охват по гребням подвздошных костей, посторонние предметы",
                        "hip_right, hip_left": "бедро: сторона и ориентиры; качество бедра в этой версии не оценивается"},
                accepts="DICOM денситометрии DXA или zip с папками исследований; картинки, обычный рентген, КТ и МРТ получают отказ с причиной",
                result_columns=ctx["columns"], quality_class={"0": "качественное", "1": "есть нарушение", "null": "не оценено"},
                token=dict(name=token["name"], scope=token["scope"], scope_ru=A.TOKEN_SCOPES[token["scope"]],
                           daily_limit=token["daily_limit"], calls_today=A.calls_today(token["id"])),
                links=dict(stand=_url("/"), http_api=_url("/docs"), documents=_url("/tz/")),
                note="Версия на правилах, без обученной модели: результаты для отладки стенда, не для клинических выводов.")


def t_list_datasets(args, token):
    out = []
    for d in ctx["datasets"].available():
        item = {k: d[k] for k in ("id", "title", "desc", "has_labels", "n_studies")}
        if args.get("with_studies") and d.get("per_study"):
            item["studies"] = d["studies"][:500]
        out.append(item)
    return dict(datasets=out)


def t_list_runs(args, token):
    limit = max(1, min(100, int(args.get("limit") or 20)))
    runs = []
    for r in ctx["list_runs"](limit):
        s = r.get("summary") or {}
        runs.append(dict(run_id=r["id"], title=r.get("title"), state=r.get("state"), created_msk=r.get("created_str"),
                         dataset=r.get("dataset"), images=s.get("images"), good=s.get("good"), bad=s.get("bad"),
                         not_evaluated=s.get("not_evaluated"), failures=s.get("failures"), page=_url(f"/runs/{r['id']}")))
    return dict(runs=runs)


def _started(token) -> dict:
    return dict(started_by=f"mcp:{token['name']}", mcp_token=token["id"])


def t_analyze_dataset(args, token):
    ds = str(args.get("dataset") or "")
    meta = ctx["datasets"].REGISTRY.get(ds)
    if not meta:
        raise ToolError("неизвестный набор: test или train, список в list_datasets")
    mode = str(args.get("mode") or "sample")
    if mode not in ("all", "sample", "study"):
        raise ToolError("mode: all, sample или study")
    n = max(1, min(100, int(args.get("n") or 10)))
    study = str(args.get("study") or "")
    if mode == "study" and not study:
        raise ToolError("для mode=study нужен study — идентификаторы в list_datasets(with_studies=true)")
    what = {"all": "весь набор", "sample": f"случайные {n}", "study": "одно исследование"}[mode]
    run_id = ctx["new_run"](f"MCP · {token['name']}: {meta['title']}: {what}")
    try:
        chosen = ctx["datasets"].link_selection(ds, mode, os.path.join(ctx["runs_dir"], run_id, "input"), n=n, study=study)
    except Exception as exc:
        ctx["write_status"](run_id, state="error", error=str(exc)[:300], **_started(token))
        raise ToolError(f"набор не подключён: {exc}")
    ctx["write_status"](run_id, dataset=ds, studies=len(chosen), has_labels=bool(meta.get("labels")), **_started(token))
    ctx["submit"](run_id)
    return dict(run_id=run_id, state="queued", studies=len(chosen), page=_url(f"/runs/{run_id}"),
                next="вызывайте get_run, пока state не станет done, затем get_results")


def t_analyze_files(args, token):
    files = args.get("files")
    if not isinstance(files, list) or not files:
        raise ToolError("files: список объектов {name, content_base64}")
    decoded, total = [], 0
    for i, f in enumerate(files[:200]):
        if not isinstance(f, dict):
            raise ToolError("files: каждый элемент — объект {name, content_base64}")
        name = re.sub(r"[\x00-\x1f\\/]", "_", os.path.basename(str(f.get("name") or "")).strip())[:120] or f"file{i}"
        try:
            data = base64.b64decode(str(f.get("content_base64") or ""), validate=True)
        except Exception:
            raise ToolError(f"файл {name}: content_base64 не декодируется")
        if not data:
            raise ToolError(f"файл {name} пустой")
        total += len(data)
        if total > MAX_FILES_BYTES:
            raise ToolError("больше 30 МБ за вызов — разбейте на несколько вызовов или используйте HTTP API /api/batch")
        decoded.append((name, data))
    title = str(args.get("title") or "").strip()[:80] or time.strftime("%d.%m %H:%M", time.gmtime(time.time() + A.MSK))
    run_id = ctx["new_run"](f"MCP · {token['name']}: {title}")
    dest = os.path.join(ctx["runs_dir"], run_id, "input")
    used = set()
    for name, data in decoded:
        base, ext, k = os.path.splitext(name)[0], os.path.splitext(name)[1], 1
        while name in used:
            k += 1
            name = f"{base}_{k}{ext}"
        used.add(name)
        with open(os.path.join(dest, name), "wb") as out:
            out.write(data)
    ctx["write_status"](run_id, has_archives=ctx["has_archives"](run_id), **_started(token))
    ctx["submit"](run_id)
    result = dict(run_id=run_id, files=len(decoded), bytes=total, state="queued", page=_url(f"/runs/{run_id}"))
    if args.get("wait"):
        t0 = time.time()
        while time.time() - t0 < WAIT_MAX:
            if (ctx["read"](run_id, "status.json") or {}).get("state") in ("done", "error", "cancelled"):
                break
            time.sleep(0.5)
        result.update(t_get_run({"run_id": run_id}, token))
        if result.get("state") not in ("done", "error", "cancelled"):
            result["note"] = f"не завершился за {WAIT_MAX} с — продолжайте get_run"
    return result


def t_get_run(args, token):
    run_id = str(args.get("run_id") or "")
    st = _run_state(run_id)
    p = ctx["progress_payload"](run_id)
    stage = next((s["label"] for s in p.get("stage_list") or [] if s["key"] == p.get("stage")), None)
    info = dict(run_id=run_id, title=st.get("title"), state=st.get("state"), error=st.get("error"), stage=stage,
                progress=p.get("progress"), tally=p.get("tally"), eta_seconds=p.get("eta"), queue_position=p.get("queue_position"),
                forced=bool(st.get("force")), page=_url(f"/runs/{run_id}"))
    man = ctx["read"](run_id, os.path.join("out", "manifest.json"))
    if man:
        ev = man.get("evaluation")
        base = f"/runs/{run_id}/files"
        info.update(summary=man.get("summary"), has_labels=man.get("has_labels"),
                    evaluation=ev if ev and len(json.dumps(ev, ensure_ascii=False)) < 20000 else None,
                    files=dict(results_csv=_url(f"{base}/results.csv"), results_xlsx=_url(f"{base}/results.xlsx"),
                               overlays_zip=_url(f"{base}/overlays.zip")))
    return info


def _match(row: dict, flt: str) -> bool:
    ok, q = row.get("processing_status") == "Success", row.get("quality_class")
    return {"all": True, "good": ok and q == 0, "bad": ok and q == 1, "not_evaluated": ok and q is None, "failed": not ok}[flt]


def t_get_results(args, token):
    run_id = str(args.get("run_id") or "")
    st = _run_state(run_id)
    flt = str(args.get("filter") or "all")
    if flt not in ("all", "good", "bad", "not_evaluated", "failed"):
        raise ToolError("filter: all, good, bad, not_evaluated или failed")
    limit, offset = max(1, min(500, int(args.get("limit") or 50))), max(0, int(args.get("offset") or 0))
    rows, final = _rows(run_id)
    sel = [r for r in rows if _match(r, flt)]
    items = []
    for r in sel[offset:offset + limit]:
        item = {c: r.get(c) for c in ctx["columns"]}
        item.update(key=r.get("key") or None, violations=[{"code": v, "text": ctx["violation_ru"].get(v, v)} for v in r.get("violation_list") or []],
                    explanations=(r.get("explanations") or [])[:4], forced=bool(r.get("forced")))
        if r.get("expert"):
            item["expert"] = r["expert"]
        if r.get("key") and r.get("overlay_png"):
            item["card"] = _url(f"/runs/{run_id}/images/{r['key']}")
        items.append(item)
    return dict(run_id=run_id, state=st.get("state"), final=final, filter=flt, total=len(sel), offset=offset, limit=limit,
                returned=len(items), rows=items)


def t_get_image(args, token):
    run_id, key = str(args.get("run_id") or ""), str(args.get("key") or "")
    st = _run_state(run_id)
    if not KEY_RE.match(key):
        raise ToolError("key — из поля key в get_results")
    rows, _ = _rows(run_id)
    row = next((r for r in rows if r.get("key") == key), None)
    if not row:
        raise ToolError(f"снимок {key} не найден в прогоне {run_id}")
    q = row.get("quality_class")
    info = dict(run_id=run_id, key=key, path_to_study=row.get("path_to_study"), study_uid=row.get("study_uid"),
                anatomical_region=row.get("anatomical_region"), region=ctx["region_ru"].get(row.get("anatomical_region")),
                quality_class=q, verdict={0: "качественное", 1: "есть нарушение"}.get(q, "не оценено"),
                violations=[{"code": v, "text": ctx["violation_ru"].get(v, v)} for v in row.get("violation_list") or []],
                explanations=row.get("explanations") or [], measurements=row.get("measurements") or {}, metrics=row.get("metrics") or {},
                processing_status=row.get("processing_status"), time_of_processing=row.get("time_of_processing"),
                forced=bool(row.get("forced")), expert=row.get("expert"), card=_url(f"/runs/{run_id}/images/{key}"))
    images = []
    if args.get("include_atlas"):
        path = os.path.join(ctx["runs_dir"], run_id, "out", row.get("overlay_png") or "-")
        if analysis.organizer_run(run_id, st):
            info["atlas_note"] = "атлас снимков организатора через MCP не передаётся — откройте карточку по ссылке card"
        elif os.path.isfile(path):
            with open(path, "rb") as f:
                images.append(base64.b64encode(f.read()).decode())
            info["atlas"] = "картинка разметки приложена"
        else:
            info["atlas_note"] = "картинки разметки у этого снимка нет"
    return info, images


HANDLERS = {"service_info": t_service_info, "list_datasets": t_list_datasets, "list_runs": t_list_runs,
            "analyze_dataset": t_analyze_dataset, "analyze_files": t_analyze_files, "get_run": t_get_run,
            "get_results": t_get_results, "get_image": t_get_image}


def _tool_result(data, images=(), is_error=False, structured=True) -> dict:
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=1)
    res = {"content": [{"type": "text", "text": text}] + [{"type": "image", "data": b, "mimeType": "image/png"} for b in images],
           "isError": is_error}
    if structured and isinstance(data, dict) and not is_error:
        res["structuredContent"] = data
    return res


# ------------------------------------------------------------------ JSON-RPC поверх HTTP

def _client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or \
        (request.client.host if request.client else "")


async def _handle(msg, token: dict, request: Request, bytes_in: int, session: dict | None) -> tuple[dict | None, dict]:
    """→ (ответ JSON-RPC или None для уведомления, заголовки)."""
    t0 = time.perf_counter()
    headers: dict = {}
    log = dict(token_id=token["id"], ip=_client_ip(request), bytes_in=bytes_in, session=(session or {}).get("id", ""),
               client=(session or {}).get("client", ""))
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        A.log_usage(method="invalid", status="bad_request", error="не JSON-RPC 2.0", duration_ms=(time.perf_counter() - t0) * 1000, **log)
        return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32600, "message": "ожидается запрос JSON-RPC 2.0"}}, headers
    method, mid, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:   # уведомления: initialized, cancelled и прочие — без ответа
        return None, headers
    log.update(method=method)
    try:
        if not isinstance(params, dict):
            raise RpcError(-32602, "params должны быть объектом")
        if method == "initialize":
            asked = str(params.get("protocolVersion") or "")
            version = asked if asked in PROTOCOLS else PROTOCOLS[0]
            info = params.get("clientInfo") or {}
            client = f"{info.get('name', '')} {info.get('version', '')}".strip()
            sid = uuid.uuid4().hex
            A.save_session(sid, token["id"], client, version)
            headers["Mcp-Session-Id"] = sid
            log.update(client=client, session=sid)
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "dxa-qc", "title": "Kostik · ЛЦТ 2026", "version": __version__},
                      "instructions": INSTRUCTIONS}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            allowed = [t for t in TOOLS if t["scope"] == "read" or token["scope"] == "analyze"]
            result = {"tools": [{k: v for k, v in t.items() if k != "scope"} for t in allowed]}
        elif method == "tools/call":
            name = params.get("name")
            log["tool"] = name
            tool = TOOL_BY_NAME.get(name)
            if not tool:
                raise RpcError(-32602, f"неизвестный инструмент {name!r} — список в tools/list")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                raise RpcError(-32602, "arguments должны быть объектом")
            structured = (request.headers.get("mcp-protocol-version") or (session or {}).get("protocol") or PROTOCOLS[0]) >= "2025-06-18"
            if tool["scope"] == "analyze" and token["scope"] != "analyze":
                log["status"] = "tool_error"
                result = _tool_result("у этого токена права только на чтение: запуск анализа выдаёт админ", is_error=True)
            elif A.calls_today(token["id"]) >= token["daily_limit"]:
                log.update(status="limited", error="суточный лимит")
                result = _tool_result(f"суточный лимит токена исчерпан: {token['daily_limit']} вызовов, сброс в полночь по Москве",
                                      is_error=True)
            else:
                try:
                    out = await run_in_threadpool(HANDLERS[name], args, token)
                    data, images = out if isinstance(out, tuple) else (out, [])
                    if isinstance(data, dict) and data.get("run_id"):
                        log["run_id"] = data["run_id"]
                    result = _tool_result(data, images, structured=structured)
                except ToolError as exc:
                    log.update(status="tool_error", error=str(exc))
                    result = _tool_result(str(exc), is_error=True)
                except (TypeError, ValueError) as exc:
                    log.update(status="tool_error", error=f"аргументы: {exc}")
                    result = _tool_result(f"неверные аргументы: {exc}", is_error=True)
        else:
            raise RpcError(-32601, f"метод {method} не поддерживается")
        response = {"jsonrpc": "2.0", "id": mid, "result": result}
    except RpcError as exc:
        log.update(status="error", error=exc.message)
        response = {"jsonrpc": "2.0", "id": mid, "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # noqa: BLE001 — внутренняя ошибка не роняет соединение клиента
        log.update(status="error", error=f"{type(exc).__name__}: {exc}")
        response = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": "внутренняя ошибка сервиса"}}
    log.setdefault("status", "ok")
    log["bytes_out"] = len(json.dumps(response, ensure_ascii=False).encode())
    log["duration_ms"] = (time.perf_counter() - t0) * 1000
    A.log_usage(**log)
    if log.get("tool"):                   # вызов инструмента — в ленту админов
        try:
            A.log_event("mcp", f"MCP: {log['tool']}", login=f"MCP · {(token or {}).get('name', '')}", ip=activity.mask_ip(log.get("ip", "")),
                        detail=log.get("status", ""), run_id=log.get("run_id", ""), device=(log.get("client") or "")[:60])
        except Exception as exc:  # noqa: BLE001
            print(f"[activity] mcp: {exc}", flush=True)
    return response, headers


def _unauthorized(request: Request, reason: str, token: dict | None):
    A.log_usage(token_id=token["id"] if token else None, method="auth", status="unauthorized", error=reason, ip=_client_ip(request))
    return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": reason}}, status_code=401,
                        headers={"WWW-Authenticate": 'Bearer realm="dxa-qc", error="invalid_token"'})


@router.post("/mcp")
async def mcp_post(request: Request):
    auth = request.headers.get("authorization", "")
    secret = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    token = A.resolve_api_token(secret)
    if not token:
        return _unauthorized(request, "нужен токен: заголовок Authorization: Bearer dxq_…, токен выдаёт админ стенда", None)
    if token["status"] != "active":
        return _unauthorized(request, "токен отозван" if token["status"] == "revoked" else "срок действия токена истёк", token)
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "запрос больше 40 МБ"}}, status_code=413)
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "запрос больше 40 МБ"}}, status_code=413)
    try:
        msg = json.loads(raw)
    except ValueError:
        A.log_usage(token_id=token["id"], method="invalid", status="bad_request", error="не JSON", ip=_client_ip(request), bytes_in=len(raw))
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "тело запроса не JSON"}}, status_code=400)
    session = A.get_session(request.headers.get("mcp-session-id", ""))
    batch = isinstance(msg, list)
    items = msg if batch else [msg]
    if batch and not items:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "пустой пакет"}}, status_code=400)
    responses, headers = [], {}
    for item in items:
        resp, h = await _handle(item, token, request, len(raw) // len(items), session)
        headers.update(h)
        if resp is not None:
            responses.append(resp)
    if not responses:
        return Response(status_code=202, headers=headers)
    return JSONResponse(responses if batch else responses[0], headers=headers)


@router.get("/mcp")
def mcp_get():
    return JSONResponse({"error": "MCP-сервер Kostik: Streamable HTTP, запросы JSON-RPC методом POST с заголовком "
                                  "Authorization: Bearer dxq_…; поток SSE не используется. Токен выдаёт админ стенда."},
                        status_code=405, headers={"Allow": "POST, DELETE"})


@router.delete("/mcp")
def mcp_delete():
    return Response(status_code=204)


# ------------------------------------------------------------------ статистика для админа

def _pct(values: list[float], q: float):
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))])


def _nice(v: float) -> int:
    if v <= 4:
        return 4
    mag = 10 ** (len(str(int(v))) - 1)
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= v:
            return int(m * mag)
    return int(10 * mag)


def _column_path(x, y, w, h, r) -> str:
    """Столбик со скруглённой верхушкой и прямым основанием."""
    r = max(0.0, min(r, h, w / 2))
    return (f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} L{x + w - r:.1f},{y:.1f} "
            f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h:.1f} Z")


def _day_chart(days: list[dict]) -> dict:
    W, H, L, R, T, B = 720, 230, 44, 12, 26, 30
    pw, ph = W - L - R, H - T - B
    top = _nice(max((d["ok"] + d["err"] for d in days), default=0))
    band = pw / len(days)
    bw = min(24.0, band * 0.62)
    base = T + ph
    peak = max(range(len(days)), key=lambda i: days[i]["ok"] + days[i]["err"])
    cols = []
    for i, d in enumerate(days):
        x = L + band * i + (band - bw) / 2
        total = d["ok"] + d["err"]
        h_ok = ph * d["ok"] / top if d["ok"] else 0
        h_err = ph * d["err"] / top if d["err"] else 0
        h_ok, h_err = (max(h_ok, 2) if d["ok"] else 0), (max(h_err, 2) if d["err"] else 0)
        segs = []
        if d["ok"]:
            segs.append(dict(kind="ok", d=_column_path(x, base - h_ok, bw, h_ok, 4 if not d["err"] else 0)))
        if d["err"]:
            y = base - h_ok - (2 if d["ok"] else 0) - h_err   # 2px фона между сегментами
            segs.append(dict(kind="err", d=_column_path(x, y, bw, h_err, 4)))
        label = (i == peak and total) or (i == len(days) - 1 and total)
        cols.append(dict(x=x, w=bw, cx=x + bw / 2, segs=segs, day=d["label"], total=total, label=bool(label),
                         label_y=base - h_ok - h_err - (2 if d["ok"] and d["err"] else 0) - 6,
                         tip=f"{d['label']}: {total} вызовов, из них ошибок {d['err']}", hit_x=L + band * i, hit_w=band))
    ticks = [dict(v=int(top * k / 4), y=base - ph * k / 4) for k in range(5)]
    return dict(W=W, H=H, L=L, R=R, T=T, B=B, base=base, cols=cols, ticks=ticks)


def build_stats(token_id: int | None = None, days: int = 14) -> dict:
    now = time.time()
    today = A._day_start(now)
    since = today - (days - 1) * 86400
    week = today - 6 * 86400
    rows = A.usage_rows(token_id, since)
    by_day = []
    for i in range(days):
        start = since + i * 86400
        day_rows = [r for r in rows if start <= r["ts"] < start + 86400 and r["method"] != "auth"]
        by_day.append(dict(label=time.strftime("%d.%m", time.gmtime(start + A.MSK)),
                           ok=sum(1 for r in day_rows if r["status"] == "ok"), err=sum(1 for r in day_rows if r["status"] != "ok")))
    wk = [r for r in rows if r["ts"] >= week and r["method"] != "auth"]
    calls = [r for r in wk if r["method"] == "tools/call"]
    tools = {}
    for r in calls:
        t = tools.setdefault(r["tool"] or "?", dict(tool=r["tool"] or "?", calls=0, errors=0, limited=0, durations=[], bytes_out=0))
        t["calls"] += 1
        t["errors"] += r["status"] not in ("ok",) and r["status"] != "limited"
        t["limited"] += r["status"] == "limited"
        t["durations"].append(r["duration_ms"])
        t["bytes_out"] += r["bytes_out"]
    top_calls = max((t["calls"] for t in tools.values()), default=0)
    tool_rows = sorted((dict(t, p50=_pct(t["durations"], 0.5), p95=_pct(t["durations"], 0.95), share=t["calls"] / top_calls * 100 if top_calls else 0)
                        for t in tools.values()), key=lambda t: -t["calls"])
    methods = Counter(r["method"] for r in wk)
    durations = [r["duration_ms"] for r in calls if r["status"] != "limited"]
    return dict(
        chart=_day_chart(by_day), by_day=by_day, tools=tool_rows, methods=dict(methods),
        week=dict(requests=len(wk), tool_calls=len(calls), errors=sum(1 for r in wk if r["status"] != "ok"),
                  error_rate=round(100 * sum(1 for r in wk if r["status"] != "ok") / len(wk), 1) if wk else 0,
                  p50=_pct(durations, 0.5), p95=_pct(durations, 0.95),
                  bytes_in=sum(r["bytes_in"] for r in wk), bytes_out=sum(r["bytes_out"] for r in wk),
                  unauthorized=sum(1 for r in rows if r["ts"] >= week and r["status"] == "unauthorized"),
                  limited=sum(1 for r in calls if r["status"] == "limited")),
        clients=Counter(r["client"] for r in rows if r["client"]).most_common(8),
        today_calls=sum(1 for r in rows if r["ts"] >= today and r["method"] == "tools/call" and r["status"] in A.OK_STATUSES),
    )


def _mcp_runs(token_id: int | None) -> list[dict]:
    out = []
    for r in ctx["list_runs"](400):
        if r.get("mcp_token") and (token_id is None or r.get("mcp_token") == token_id):
            out.append(r)
    return out


def _token_summaries(tokens: list[dict]) -> list[dict]:
    week = A._day_start() - 6 * 86400
    rows = A.usage_rows(None, week)
    today = A._day_start()
    for t in tokens:
        mine = [r for r in rows if r["token_id"] == t["id"] and r["method"] != "auth"]
        t.update(week_calls=sum(1 for r in mine if r["method"] == "tools/call"), week_errors=sum(1 for r in mine if r["status"] != "ok"),
                 today_calls=sum(1 for r in mine if r["ts"] >= today and r["method"] == "tools/call" and r["status"] in A.OK_STATUSES),
                 client=next((r["client"] for r in reversed(mine) if r["client"]), ""))
    return tokens


def _fmt_bytes(n) -> str:
    n = int(n or 0)
    return f"{n / 1024 / 1024:.1f} МБ".replace(".", ",") if n >= 1024 * 1024 else f"{n / 1024:.0f} КБ" if n >= 1024 else f"{n} Б"


def _admin(request: Request):
    user = request.state.user
    if not user:
        return None, RedirectResponse("/login?next=" + request.url.path, status_code=303)
    if not user["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    return user, None


def _page(request: Request, token: dict | None = None, new_token: dict | None = None, error: str = "", status_code: int = 200):
    tokens = _token_summaries(A.list_api_tokens())
    runs = _mcp_runs(token["id"] if token else None)
    templates = ctx["templates"]
    templates.env.filters.setdefault("bytes", _fmt_bytes)
    return templates.TemplateResponse(request, "admin_mcp.html", dict(
        user=request.state.user, csrf=request.state.csrf, trac_url=ctx["trac_url"], version=__version__,
        endpoint=_url("/mcp"), tokens=tokens, token=token, new_token=new_token, error=error, scopes=A.TOKEN_SCOPES,
        stats=build_stats(token["id"] if token else None), recent=A.usage_recent(token["id"] if token else None, 60),
        runs=runs[:30], runs_count=len(runs), runs_images=sum((r.get("summary") or {}).get("images") or 0 for r in runs),
        tools=[{k: t[k] for k in ("name", "title", "scope")} for t in TOOLS]), status_code=status_code)


@router.get("/admin/mcp", response_class=HTMLResponse)
def admin_mcp(request: Request):
    _, redirect = _admin(request)
    return redirect or _page(request)


@router.get("/admin/mcp/tokens/{tid}", response_class=HTMLResponse)
def admin_mcp_token(request: Request, tid: int):
    _, redirect = _admin(request)
    if redirect:
        return redirect
    token = A.get_api_token(tid)
    if not token:
        raise HTTPException(404, "токен не найден")
    return _page(request, token=_token_summaries([token])[0])


@router.post("/admin/mcp/tokens")
def admin_mcp_create(request: Request, name: str = Form(""), scope: str = Form("read"), days: str = Form(""),
                     daily_limit: str = Form("500"), csrf: str = Form("")):
    me, redirect = _admin(request)
    if redirect:
        return redirect
    ask._check_csrf(request, csrf)
    try:
        secret, row = A.create_api_token(me["login"], name, scope, int(days) if days else None, int(daily_limit or 500))
    except (A.AccountError, ValueError) as exc:
        return _page(request, error=str(exc), status_code=400)
    return _page(request, new_token=dict(row, secret=secret))


@router.post("/admin/mcp/tokens/{tid}/revoke")
def admin_mcp_revoke(request: Request, tid: int, csrf: str = Form("")):
    _, redirect = _admin(request)
    if redirect:
        return redirect
    ask._check_csrf(request, csrf)
    A.revoke_api_token(tid)
    return RedirectResponse(f"/admin/mcp/tokens/{tid}", status_code=303)


@router.post("/admin/mcp/tokens/{tid}/limit")
def admin_mcp_limit(request: Request, tid: int, daily_limit: str = Form(""), csrf: str = Form("")):
    _, redirect = _admin(request)
    if redirect:
        return redirect
    ask._check_csrf(request, csrf)
    try:
        A.set_token_limit(tid, int(daily_limit))
    except (A.AccountError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return RedirectResponse(f"/admin/mcp/tokens/{tid}", status_code=303)
