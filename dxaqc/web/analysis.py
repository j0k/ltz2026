# -*- coding: utf-8 -*-
"""Запросы на анализ сверх обычного: принудительный анализ отклонённого файла и анализ снимка в Claude через Codellake.

Запросить может вошедший пользователь, выполняется после одобрения админом; запрос админа одобряется сразу.
Принудительный анализ — отдельный прогон с флагом force: картинки и DICOM не DXA проверяются с пометкой
«результат не гарантирован». Анализ в Claude отправляет во внешний сервис PNG снимка без метаданных DICOM,
поэтому снимки наборов организатора и прогона примера туда не уходят.
"""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dxaqc.web import accounts as A
from dxaqc.web import ask

router = APIRouter(include_in_schema=False)
ctx: dict = {}
MAX_ATTACHMENT_SIDE = 1600


def setup(**kw):
    """read, new_run, write_status, submit, runs_dir, data_dir, example_id — функции и пути приложения."""
    ctx.update(kw)


def organizer_run(run_id: str, st: dict | None) -> bool:
    """Прогон на данных организатора: пример или набор, в том числе перезапуск такого прогона."""
    seen = set()
    while st and run_id not in seen:
        if run_id == ctx["example_id"] or st.get("dataset"):
            return True
        seen.add(run_id)
        run_id = st.get("parent") or ""
        st = ctx["read"](run_id, "status.json") if run_id else None
    return False


def _row(run_id: str, target: str) -> dict:
    man = ctx["read"](run_id, os.path.join("out", "manifest.json"))
    row = next((r for r in (man or {}).get("rows", []) if r.get("path_to_study") == target), None)
    if not row:
        raise HTTPException(404, "файл не найден в результатах прогона")
    return row


def _input_path(run_id: str, target: str) -> str:
    base = os.path.realpath(os.path.join(ctx["runs_dir"], run_id, "input"))
    path = os.path.realpath(os.path.join(base, target))
    if not path.startswith(base + os.sep) or not os.path.isfile(path):
        raise HTTPException(404, "исходный файл не сохранился")
    return path


def requests_by_target(run_id: str, user: dict | None) -> dict:
    """Последний запрос каждого вида по файлу прогона; ссылку на ответ Claude видят автор и админы."""
    out: dict = {}
    for r in A.run_requests(run_id):
        visible = bool(user and (user.get("is_admin") or user["id"] == r["user_id"]))
        out.setdefault(r["target"], {})[r["kind"]] = dict(r, visible=visible)
    return out


# ------------------------------------------------------------------ выполнение одобренного запроса

def _execute(req: dict, approver: dict):
    try:
        if req["kind"] == "force":
            src = _input_path(req["run_id"], req["target"])
            new_id = ctx["new_run"](f"Принудительный анализ: {req['label']}")
            dst = os.path.join(ctx["runs_dir"], new_id, "input", req["target"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            ctx["write_status"](new_id, force=True, parent=req["run_id"], started_by=req["login"], request_id=req["id"])
            ctx["submit"](new_id)
            A.update_request(req["id"], result_run=new_id)
        else:
            attachment = _attachment(req)
            q = A.add_image_question(req["user_id"], _claude_text(req), attachment, approver["id"])
            A.update_request(req["id"], question_id=q["id"])
            ask._wake.set()
    except HTTPException as exc:
        A.update_request(req["id"], status="error", error=str(exc.detail))
    except Exception as exc:  # noqa: BLE001 — запрос помечается ошибкой, страница не падает
        A.update_request(req["id"], status="error", error=f"{type(exc).__name__}: {exc}"[:300])


def _attachment(req: dict) -> str:
    """PNG снимка без метаданных DICOM: у проанализированного — исходный кадр стенда, у отказа — сам файл."""
    from PIL import Image
    from dxaqc.io import load_image
    row = _row(req["run_id"], req["target"])
    out = os.path.join(ctx["runs_dir"], req["run_id"], "out")
    if row.get("original_png") and os.path.isfile(os.path.join(out, row["original_png"])):
        im = Image.open(os.path.join(out, row["original_png"])).convert("L")
    else:
        src = _input_path(req["run_id"], req["target"])
        loaded = load_image(src, os.path.dirname(src), force=True)
        if not hasattr(loaded, "pixels"):
            try:
                im = Image.open(src).convert("L")
            except Exception:
                raise HTTPException(400, "файл не открывается как изображение")
        else:
            im = Image.fromarray(loaded.pixels)
            if src.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif")):
                im = Image.open(src).convert("L")   # картинку отдаём в исходном разрешении, а не в масштабе DXA
    im.thumbnail((MAX_ATTACHMENT_SIDE, MAX_ATTACHMENT_SIDE))
    folder = os.path.join(ctx["data_dir"], "attachments")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"request_{req['id']}.png")
    im.save(path, "PNG", optimize=True)
    return path


def _claude_text(req: dict) -> str:
    return (f"Посмотри приложенное изображение: файл «{req['label']}» из прогона {req['run_id']} стенда DXA QC. "
            f"Что сказал сервис: {req['reason'] or 'нет данных'}.\n"
            "Ответь: 1) что это за исследование — денситометрия DXA или другое, какая область и проекция; "
            "2) пригодно ли оно для контроля качества денситометрии по ТЗ задачи 04 (поясничный отдел: охват от гребней "
            "подвздошных костей до половины Th12, наклон оси не больше 5°, посторонние предметы; бедро: большой вертел, "
            "шейка и седалищная кость в кадре, ротация по малому вертелу); 3) какие нарушения видны и что сделать. "
            "Изображение без метаданных DICOM. Не придумывай то, чего на снимке не видно.")


# ------------------------------------------------------------------ маршруты

@router.post("/runs/{run_id}/requests")
def create_request(request: Request, run_id: str, kind: str = Form(""), target: str = Form(""), csrf: str = Form("")):
    user = request.state.user
    if not user:
        return RedirectResponse(f"/login?next=/runs/{run_id}", status_code=303)
    ask._check_csrf(request, csrf)
    st = ctx["read"](run_id, "status.json")
    if not st:
        raise HTTPException(404, "прогон не найден")
    if kind not in A.REQUEST_KINDS:
        raise HTTPException(400, "неизвестный вид запроса")
    row = _row(run_id, target)
    if kind == "force":
        if not row.get("forceable"):
            raise HTTPException(400, "принудительный анализ доступен только для отклонённых файлов")
        if st.get("force"):
            raise HTTPException(400, "этот прогон уже принудительный")
        _input_path(run_id, target)
    if kind == "claude" and organizer_run(run_id, st):
        raise HTTPException(400, "снимки организатора во внешний сервис Claude не отправляются")
    reason = " ".join(row.get("explanations") or [])[:400] if row.get("processing_status") != "Success" else \
        f"{row.get('anatomical_region')}, класс качества {row.get('quality_class')}; " + " ".join((row.get("explanations") or [])[:3])
    req = A.add_request(user, kind, run_id, target, os.path.basename(target), reason)
    if req["status"] == "pending" and user.get("is_admin"):   # запрос админа — сам себе одобрение
        req = A.decide_request(req["id"], user, True)
        _execute(req, user)
    elif req["status"] == "pending" and ctx.get("notify"):    # админам в Telegram с кнопками решения
        import threading
        threading.Thread(target=ctx["notify"], args=(req,), daemon=True).start()
    back = request.headers.get("referer") or ""
    dest = back if back.startswith(str(request.base_url)) and "/images/" in back else f"/runs/{run_id}"
    return RedirectResponse(f"{dest.split('#')[0]}#req-{req['id']}", status_code=303)


@router.post("/admin/requests/{rid}")
def decide(request: Request, rid: int, decision: str = Form(""), csrf: str = Form("")):
    me = request.state.user
    if not me or not me["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    ask._check_csrf(request, csrf)
    try:
        req = A.decide_request(rid, me, decision == "approve")
    except A.AccountError as exc:
        raise HTTPException(400, str(exc))
    if req["status"] == "approved":
        _execute(req, me)
    return RedirectResponse("/admin#requests", status_code=303)
