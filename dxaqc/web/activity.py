# -*- coding: utf-8 -*-
"""Журнал действий на стенде и живая лента для админов.

Каждый запрос проходит через middleware: просмотры страниц и действия (загрузки, запуски, правки) превращаются
в события с понятной подписью; служебные опросы, картинки и статика не пишутся. Входы, регистрации, завершение
проверок, команды Telegram-бота и вызовы MCP пишутся явно там, где случаются. IP сохраняется только началом адреса,
устройство — как «браузер · система». Лента /admin/activity получает события потоком (Server-Sent Events) и
показывает, кто сейчас на сайте.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from dxaqc.web import accounts as A

router = APIRouter(include_in_schema=False)
ctx: dict = {}
MSK = 3 * 3600
KINDS = {"view": "просмотр", "action": "действие", "auth": "вход", "system": "проверка", "bot": "Telegram", "mcp": "MCP", "admin": "админ"}

SKIP = re.compile(r"^/(static|favicon|apple-touch|og/|showcase/|gallery/(img|thumb|atlas)/|api/health|api/tts|api/voice|api/ask/|api/control/queue|"
                  r"admin/api/|docs|openapi\.json|robots)|/og\.jpg$|\.(png|jpe?g|webp|svg|ico|css|js|map|woff2?|wav|mp3)(\?|$)|"
                  r"^/api/runs/[^/]+/(progress|events|live-rows)")
EXPLICIT_POST = {"/login", "/register", "/logout", "/mcp"}      # пишутся в обработчиках с логином и итогом
VIEWS = [
    (r"^/$", "открыл главную"), (r"^/v1/?$", "открыл полную версию v1"), (r"^/check/example$", "смотрит демо"),
    (r"^/check/([\w-]+)$", "смотрит результат проверки"), (r"^/runs/([\w-]+)/images/\w+$", "смотрит карточку снимка"),
    (r"^/runs/([\w-]+)$", "смотрит прогон"), (r"^/gallery$", "открыл галерею"), (r"^/cabinet$", "открыл личный кабинет"),
    (r"^/account$", "открыл кабинет v1"), (r"^/tz/?$", "открыл документы"), (r"^/tz/(.+)$", "читает документ"),
    (r"^/control$", "открыл пульт анализа"), (r"^/ask$", "открыл вопросы Claude"), (r"^/admin", "в админке"),
    (r"^/login$", "открыл вход"), (r"^/register$", "открыл регистрацию"), (r"^/cookies$", "читает про cookie"),
    (r"^/invite/", "открыл приглашение"),
]
DOWNLOADS = [(r"^/runs/([\w-]+)/files/results\.csv$", "скачал таблицу CSV"), (r"^/runs/([\w-]+)/files/results\.xlsx$", "скачал таблицу XLSX"),
             (r"^/runs/([\w-]+)/files/overlays\.zip$", "скачал архив разметки")]
ACTIONS = [
    (r"^/runs$", "загрузил файлы на проверку"), (r"^/runs/dataset$", "запустил проверку набора организатора"),
    (r"^/api/batch$", "пакетная проверка через API"), (r"^/api/gallery/\w+/analyze$", "запустил анализ снимка в галерее"),
    (r"^/runs/([\w-]+)/requests$", "запросил анализ сверх обычного"), (r"^/ask$", "задал вопрос Claude"),
    (r"^/api/stt$", "задал вопрос голосом"), (r"^/account/password$", "сменил пароль"), (r"^/cabinet/password$", "сменил пароль"),
    (r"^/account/telegram", "настраивает Telegram"),
    (r"^/control/runs/([\w-]+)/rerun$", "пульт: перезапустил прогон"), (r"^/control/runs/([\w-]+)/cancel$", "пульт: отменил прогон"),
    (r"^/control/runs/([\w-]+)/delete$", "пульт: удалил прогон"),
    (r"^/control/runs/([\w-]+)/images/\w+/override$", "пульт: поправил вердикт снимка"),
    (r"^/control/runs/([\w-]+)/images/\w+/preview$", "пульт: пробный анализ снимка"),
    (r"^/admin/users/", "админ: изменил пользователя"), (r"^/admin/invites", "админ: приглашения"),
    (r"^/admin/requests/", "админ: решение по запросу анализа"), (r"^/admin/mcp", "админ: токены MCP"),
    (r"^/admin/approve|^/admin/questions", "админ: одобрение вопроса"), (r"^/invite/", "принял приглашение"),
]


def mask_ip(ip: str) -> str:
    """Только начало адреса: 194.87.*.* — достаточно, чтобы различать гостей, но не хранить адрес целиком."""
    ip = (ip or "").strip()
    if ":" in ip and "." not in ip:
        parts = ip.split(":")
        return ":".join(parts[:2]) + ":*" if len(parts) > 2 else ip
    parts = ip.split(".")
    return ".".join(parts[:2]) + ".*.*" if len(parts) == 4 else ip


def device(ua: str) -> str:
    ua = ua or ""
    browser = ("Telegram" if "Telegram" in ua else "Яндекс" if "YaBrowser" in ua else "Edge" if "Edg/" in ua else
               "Opera" if "OPR/" in ua else "Chrome" if "Chrome/" in ua else "Firefox" if "Firefox/" in ua else
               "Safari" if "Safari/" in ua else "curl" if ua.startswith("curl") else "бот" if re.search(r"bot|crawl|spider", ua, re.I) else "")
    system = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua else "Windows" if "Windows" in ua else
              "macOS" if "Mac OS" in ua else "Linux" if "Linux" in ua else "")
    return " · ".join(x for x in (browser, system) if x) or "—"


def client_ip(request: Request) -> str:
    return (request.headers.get("x-real-ip") or (request.client.host if request.client else "") or "").strip()


def _match(rules, path):
    for pattern, label in rules:
        m = re.match(pattern, path)
        if m:
            return label, (m.group(1) if m.groups() else "")
    return None, ""


def event(request: Request, kind: str, action: str, *, user: dict | None = None, login: str = "", detail: str = "",
          run_id: str = "", status: int | None = None):
    """Явное событие из обработчика: вход, регистрация, выход и т. п."""
    try:
        A.log_event(kind, action, user=user if user is not None else getattr(request.state, "user", None), login=login,
                    ip=mask_ip(client_ip(request)), detail=detail, path=request.url.path, run_id=run_id, status=status,
                    device=device(request.headers.get("user-agent", "")))
    except Exception as exc:  # noqa: BLE001 — журнал не должен ронять запрос
        print(f"[activity] {type(exc).__name__}: {exc}", flush=True)


def record(request: Request, status: int, ctype: str, location: str = ""):
    """Запрос → событие ленты, если это просмотр страницы или действие; служебное пропускаем."""
    path, method = request.url.path, request.method
    if SKIP.search(path) or status >= 500 and method == "GET":
        return
    run_id = ""
    if method == "GET":
        label, run_id = _match(DOWNLOADS, path)
        kind = "action"
        if not label:
            if "text/html" not in ctype or status >= 400:
                return
            label, run_id = _match(VIEWS, path)
            kind = "admin" if path.startswith("/admin") else "view"
            label = label or f"открыл {path}"
    else:
        if path in EXPLICIT_POST:
            return
        label, run_id = _match(ACTIONS, path)
        kind = "admin" if path.startswith("/admin") else "action"
        label = label or f"действие {method} {path}"
        m = re.search(r"/(?:runs|check)/([\w-]+)", location or "")
        run_id = run_id or (m.group(1) if m else "")
        if status >= 400:
            label += " — отказ"
    detail = path if kind == "view" and path.startswith("/tz/") else ""
    event(request, kind, label, detail=detail, run_id=run_id, status=status)


def present(r: dict) -> dict:
    t = time.gmtime(r["ts"] + MSK)
    link = f"/runs/{r['run_id']}" if r.get("run_id") else (r["path"] if r["kind"] == "view" and r.get("path") else "")
    return dict(id=r["id"], time=time.strftime("%H:%M:%S", t), date=time.strftime("%d.%m", t), who=r["login"] or "гость",
                user=bool(r["login"]), ip=r["ip"], kind=r["kind"], kind_ru=KINDS.get(r["kind"], r["kind"]), action=r["action"],
                detail=r["detail"], link=link, device=r["device"], status=r["status"])


def _online():
    return [dict(who=o["login"] or f"гость · {o['ip']}", user=bool(o["login"]), device=o["device"], n=o["n"],
                 ago=max(0, int(time.time() - o["last"]))) for o in A.online(5)]


def _admin(request: Request):
    user = request.state.user
    if not user:
        return None
    if not user["is_admin"]:
        raise HTTPException(403, "лента действий только для админов")
    return user


@router.get("/admin/activity", response_class=HTMLResponse)
def activity_page(request: Request):
    if not _admin(request):
        return RedirectResponse("/login?next=/admin/activity", status_code=303)
    rows = [present(r) for r in A.events_recent(150)]
    return ctx["templates"].TemplateResponse(request, "admin_activity.html", dict(
        user=request.state.user, csrf=request.state.csrf, rows=rows, last_id=rows[0]["id"] if rows else 0, online=_online(),
        stats=A.events_stats(), kinds=KINDS, version=ctx.get("version", "")))


@router.get("/admin/api/activity")
def activity_json(request: Request, after: int = 0):
    if not _admin(request):
        raise HTTPException(403, "лента действий только для админов")
    return JSONResponse(dict(events=[present(r) for r in A.events_after(after, 200)], online=_online(), stats=A.events_stats()),
                        headers={"Cache-Control": "no-store"})


@router.get("/admin/api/activity/stream")
async def activity_stream(request: Request, after: int = 0, once: bool = False):
    """Поток событий: новые строки приходят сразу, раз в 15 с — пинг и обновление «кто на сайте»."""
    if not _admin(request):
        raise HTTPException(403, "лента действий только для админов")
    last = int(request.headers.get("last-event-id") or after or 0)

    async def gen():
        nonlocal last
        tick = 0
        while True:
            rows = await run_in_threadpool(A.events_after, last, 100)
            for r in rows:
                last = r["id"]
                yield f"id: {r['id']}\nevent: activity\ndata: {json.dumps(present(r), ensure_ascii=False)}\n\n"
            if once:
                return
            if tick % 15 == 0:
                payload = dict(online=await run_in_threadpool(_online), stats=await run_in_threadpool(A.events_stats))
                yield f"event: online\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            tick += 1
            if await request.is_disconnected():
                return
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
