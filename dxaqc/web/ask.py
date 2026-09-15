# -*- coding: utf-8 -*-
"""Вопросы к Claude по рабочей папке: вход, регистрация, кабинет, страница вопросов, админка и фоновый исполнитель.

Вопросы выполняет брокер tools/ask_broker.py на хосте (отдельный инстанс Codellake). Стенд передаёт ему текст и режим
с сервера, токен брокера в браузер не попадает. Режим full — только после одобрения админом.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from markdown_it import MarkdownIt

from dxaqc import __version__
from dxaqc.web import accounts as A
from dxaqc.web import contacts as C

COOKIE = "dxaqc_sid"
COOKIE_SECURE = os.environ.get("DXAQC_COOKIE_SECURE", "1") != "0"
ASK_URL = os.environ.get("DXAQC_ASK_URL", "").rstrip("/")
ASK_TOKEN_FILE = os.environ.get("DXAQC_ASK_TOKEN_FILE", "")
POLL_SEC = float(os.environ.get("DXAQC_ASK_POLL", "3"))
ANSWER_TIMEOUT = int(os.environ.get("DXAQC_ASK_TIMEOUT", "1900"))
TRAC_URL = os.environ.get("DXAQC_TRAC_URL", "/trac/")
STATUS_RU = {"queued": "в очереди", "running": "Claude отвечает", "done": "готово", "error": "ошибка",
             "awaiting_approval": "ждёт одобрения админа", "rejected": "отклонено админом"}
USER_ACTIONS = {"grant": dict(can_ask=True), "revoke": dict(can_ask=False), "make_admin": dict(role="admin"),
                "make_user": dict(role="user"), "block": dict(blocked=True), "unblock": dict(blocked=False)}

router = APIRouter(include_in_schema=False)
templates = None
_md = MarkdownIt("commonmark", {"html": False}).enable("table")  # сырой HTML из ответа не пропускаем
_wake, _stop = threading.Event(), threading.Event()
_health = {"t": 0.0, "ok": False}


def setup(tpl):
    global templates
    templates = tpl
    tpl.env.filters["md"] = lambda text: _md.render(text or "")
    tpl.env.filters["msk"] = lambda ts: time.strftime("%d.%m %H:%M", time.gmtime((ts or 0) + A.MSK))
    tpl.env.globals["status_ru"] = STATUS_RU


def current_user(request: Request):
    return A.session_user(request.cookies.get(COOKIE))


def _page(request: Request, name: str, status_code: int = 200, **kw):
    ctx = dict(user=request.state.user, csrf=request.state.csrf, trac_url=TRAC_URL, version=__version__)
    ctx.update(kw)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _check_csrf(request: Request, token: str):
    if not request.state.user or not token or not hmac.compare_digest(token.encode(), (request.state.csrf or "").encode()):
        raise HTTPException(403, "форма устарела, обновите страницу")


def _safe_next(dest: str) -> str:
    return dest if isinstance(dest, str) and dest.startswith("/") and not dest.startswith("//") and "\\" not in dest else "/ask"


def _to_login(request: Request):
    return RedirectResponse("/login?next=" + quote(request.url.path), status_code=303)


def _signed_in(uid: int, dest: str):
    token, _ = A.create_session(uid)
    r = RedirectResponse(dest, status_code=303)
    r.set_cookie(COOKIE, token, max_age=A.SESSION_TTL, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")
    return r


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ------------------------------------------------------------------ вход, регистрация, кабинет

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/ask"):
    return _page(request, "login.html", next=_safe_next(next), error="", login="")


@router.post("/login")
def login(request: Request, login: str = Form(""), password: str = Form(""), next: str = Form("/ask")):
    try:
        user = A.authenticate(login, password, _ip(request))
    except A.AccountError as exc:
        return _page(request, "login.html", 400, next=_safe_next(next), error=str(exc), login=login)
    return _signed_in(user["id"], _safe_next(next))


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return _page(request, "register.html", error="", login="")


@router.post("/register")
def register(request: Request, login: str = Form(""), password: str = Form(""), password2: str = Form("")):
    try:
        if password != password2:
            raise A.AccountError("пароли не совпадают")
        user = A.create_user(login, password)
    except A.AccountError as exc:
        return _page(request, "register.html", 400, error=str(exc), login=login)
    return _signed_in(user["id"], "/ask")


@router.post("/logout")
def logout(request: Request, csrf: str = Form("")):
    if request.state.user:
        _check_csrf(request, csrf)
        A.drop_session(request.cookies.get(COOKIE))
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie(COOKIE, path="/")
    return r


@router.get("/account", response_class=HTMLResponse)
def account(request: Request):
    user = request.state.user
    if not user:
        return _to_login(request)
    return _page(request, "account.html", asked_today=A.asked_today(user["id"]), error="", message="")


@router.post("/account/password")
def account_password(request: Request, old: str = Form(""), new: str = Form(""), new2: str = Form(""), csrf: str = Form("")):
    user = request.state.user
    if not user:
        return _to_login(request)
    _check_csrf(request, csrf)
    try:
        A.authenticate(user["login"], old, _ip(request))
        if new != new2:
            raise A.AccountError("новые пароли не совпадают")
        A.set_password(user["id"], new)
    except A.AccountError as exc:
        return _page(request, "account.html", 400, asked_today=A.asked_today(user["id"]), error=str(exc), message="")
    return _page(request, "account.html", asked_today=A.asked_today(user["id"]), error="", message="пароль изменён")


# ------------------------------------------------------------------ вопросы

@router.get("/ask", response_class=HTMLResponse)
def ask_page(request: Request):
    user = request.state.user
    if not user:
        return _to_login(request)
    return _page(request, "ask.html", questions=A.user_questions(user["id"]), asked_today=A.asked_today(user["id"]),
                 error="", draft="", broker=bool(ASK_URL))


@router.post("/ask")
def ask_submit(request: Request, text: str = Form(""), want_exec: str = Form(""), csrf: str = Form("")):
    user = request.state.user
    if not user:
        return _to_login(request)
    _check_csrf(request, csrf)
    try:
        q = A.add_question(user, text, want_exec=bool(want_exec))
    except A.AccountError as exc:
        return _page(request, "ask.html", 400, questions=A.user_questions(user["id"]), asked_today=A.asked_today(user["id"]),
                     error=str(exc), draft=text, broker=bool(ASK_URL))
    _wake.set()
    return RedirectResponse(f"/ask#q{q['id']}", status_code=303)


@router.post("/ask/{qid}/exec")
def ask_exec(request: Request, qid: int, csrf: str = Form("")):
    user = request.state.user
    if not user:
        return _to_login(request)
    _check_csrf(request, csrf)
    q = A.get_question(qid)
    if not q or q["user_id"] != user["id"]:
        raise HTTPException(404)
    if q["mode"] != "read" or q["status"] not in ("done", "error"):
        raise HTTPException(400, "исполнение можно запросить только для завершённого вопроса на чтение")
    try:
        new = A.add_question(user, q["text"], want_exec=True, parent_id=qid)
    except A.AccountError as exc:
        return _page(request, "ask.html", 400, questions=A.user_questions(user["id"]), asked_today=A.asked_today(user["id"]),
                     error=str(exc), draft="", broker=bool(ASK_URL))
    return RedirectResponse(f"/ask#q{new['id']}", status_code=303)


@router.get("/api/ask/{qid}")
def ask_status(request: Request, qid: int):
    user, q = request.state.user, A.get_question(qid)
    if not user or not q or (q["user_id"] != user["id"] and not user["is_admin"]):
        raise HTTPException(404)
    return {"id": q["id"], "status": q["status"], "mode": q["mode"], "finished": q["finished"]}


# ------------------------------------------------------------------ админка

def _admin_page(request: Request, status_code: int = 200, error: str = "", new_invite: dict | None = None):
    return _page(request, "admin.html", status_code, users=A.list_users(), approvals=A.awaiting_approval(),
                 journal=A.journal(100), broker=bool(ASK_URL), broker_ok=broker_alive(), error=error,
                 requests=A.pending_requests(), recent_requests=A.recent_requests(20),
                 request_kinds=A.REQUEST_KINDS, request_status=A.REQUEST_STATUS,
                 invites=A.list_invites(), invite_roles=A.INVITE_ROLES, new_invite=new_invite, contacts=C.ALL)


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    user = request.state.user
    if not user:
        return _to_login(request)
    if not user["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    return _admin_page(request)


@router.post("/admin/users/{uid}")
def admin_user(request: Request, uid: int, action: str = Form(""), daily_limit: str = Form(""), csrf: str = Form("")):
    me = request.state.user
    if not me or not me["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    _check_csrf(request, csrf)
    if not A.get_user(uid):
        raise HTTPException(404)
    try:
        if action == "limit":
            try:
                limit = int(daily_limit)
            except ValueError:
                raise A.AccountError("лимит должен быть числом")
            A.update_user(uid, daily_limit=limit)
        elif action in USER_ACTIONS:
            if uid == me["id"] and action in ("make_user", "block"):
                raise A.AccountError("нельзя снять права админа или заблокировать самого себя")
            A.update_user(uid, **USER_ACTIONS[action])
        else:
            raise A.AccountError("неизвестное действие")
    except A.AccountError as exc:
        return _admin_page(request, 400, str(exc))
    return RedirectResponse(f"/admin#u{uid}", status_code=303)


@router.post("/admin/questions/{qid}")
def admin_question(request: Request, qid: int, decision: str = Form(""), csrf: str = Form("")):
    me = request.state.user
    if not me or not me["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    _check_csrf(request, csrf)
    try:
        A.decide(qid, me, decision == "approve")
    except A.AccountError as exc:
        return _admin_page(request, 400, str(exc))
    _wake.set()
    return RedirectResponse("/admin#approvals", status_code=303)


@router.post("/admin/invites")
def admin_create_invite(request: Request, role: str = Form("admin"), hours: str = Form("48"), note: str = Form(""),
                        csrf: str = Form("")):
    me = request.state.user
    if not me or not me["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    _check_csrf(request, csrf)
    try:
        token, inv = A.create_invite(me["login"], role=role, hours=float(hours), note=note)
    except (A.AccountError, ValueError) as exc:
        return _admin_page(request, 400, str(exc))
    # ссылка показывается один раз: в базе только хеш токена
    return _admin_page(request, new_invite=dict(inv, url=A.invite_url(token)))


@router.post("/admin/invites/{iid}/revoke")
def admin_revoke_invite(request: Request, iid: int, csrf: str = Form("")):
    me = request.state.user
    if not me or not me["is_admin"]:
        raise HTTPException(403, "страница только для админов")
    _check_csrf(request, csrf)
    A.revoke_invite(iid)
    return RedirectResponse("/admin#invites", status_code=303)


# ------------------------------------------------------------------ приглашения

def _invite_page(request: Request, token: str, status_code: int = 200, error: str = "", login: str = ""):
    return _page(request, "invite.html", status_code, inv=A.get_invite(token), token=token, error=error, login=login,
                 invite_errors=A.INVITE_ERRORS)


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(request: Request, token: str):
    return _invite_page(request, token, 200 if A.get_invite(token) else 404)


@router.post("/invite/{token}/accept")
def invite_accept(request: Request, token: str, csrf: str = Form("")):
    user = request.state.user
    if not user:
        return RedirectResponse("/login?next=" + quote(f"/invite/{token}"), status_code=303)
    _check_csrf(request, csrf)
    try:
        user = A.accept_invite(token, user)
    except A.AccountError as exc:
        return _invite_page(request, token, 400, str(exc))
    return RedirectResponse("/admin" if user["is_admin"] else "/ask", status_code=303)


@router.post("/invite/{token}/register")
def invite_register(request: Request, token: str, login: str = Form(""), password: str = Form(""), password2: str = Form("")):
    try:
        A.check_invite(token)
        if password != password2:
            raise A.AccountError("пароли не совпадают")
        user = A.accept_invite(token, A.create_user(login, password))
    except A.AccountError as exc:
        return _invite_page(request, token, 400, str(exc), login)
    return _signed_in(user["id"], "/admin" if user["is_admin"] else "/ask")


# ------------------------------------------------------------------ исполнитель

def _token() -> str:
    try:
        with open(ASK_TOKEN_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def _broker(method: str, path: str, body: dict | None = None, timeout: float = 15) -> dict:
    req = urllib.request.Request(ASK_URL + path, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def broker_alive() -> bool:
    if not ASK_URL:
        return False
    if time.time() - _health["t"] > 15:
        try:
            _health["ok"] = _broker("GET", "/v1/health", timeout=3).get("status") == "ok"
        except Exception:  # noqa: BLE001
            _health["ok"] = False
        _health["t"] = time.time()
    return _health["ok"]


def _run_one(q: dict):
    if not ASK_URL:
        A.finish(q["id"], error="исполнитель вопросов на этом стенде не подключён")
        return
    approver = A.get_user(q["approved_by"]) if q.get("approved_by") else None
    rid = f"ltz-q{q['id']}-{int(q.get('started') or time.time())}"
    body = {"id": rid, "text": q["text"], "mode": q["mode"], "user": q["login"], "approver": approver["login"] if approver else ""}
    if q.get("attachment"):   # снимок по одобренному запросу: PNG без метаданных DICOM
        try:
            with open(q["attachment"], "rb") as f:
                body["attachments"] = [{"name": "snimok.png", "data": base64.b64encode(f.read()).decode()}]
        except OSError:
            A.finish(q["id"], error="вложение снимка не найдено")
            return
    try:
        _broker("POST", "/v1/questions", body, timeout=60)
        t0 = time.time()
        while not _stop.is_set():
            st = _broker("GET", f"/v1/questions/{rid}")
            if st.get("status") == "done":
                A.finish(q["id"], answer=st.get("answer") or "(пустой ответ)")
                return
            if st.get("status") == "error":
                A.finish(q["id"], error=st.get("error") or "ошибка исполнителя")
                return
            if time.time() - t0 > ANSWER_TIMEOUT:
                A.finish(q["id"], error="ответ не получен за отведённое время")
                return
            _stop.wait(POLL_SEC)
    except urllib.error.HTTPError as exc:
        A.finish(q["id"], error=f"исполнитель ответил {exc.code}" + (": вопрос потерян при перезапуске" if exc.code == 404 else ""))
    except Exception as exc:  # noqa: BLE001
        A.finish(q["id"], error=f"исполнитель недоступен: {type(exc).__name__}")


def _loop():
    while not _stop.is_set():
        try:
            q = A.claim_next()
        except Exception as exc:  # noqa: BLE001
            print(f"[ask] очередь недоступна: {exc}")
            q = None
        if q:
            _run_one(q)
            continue
        _wake.wait(5)
        _wake.clear()


def start_worker():
    _stop.clear()
    threading.Thread(target=_loop, name="ask-worker", daemon=True).start()


def stop_worker():
    _stop.set()
    _wake.set()
