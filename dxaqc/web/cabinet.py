# -*- coding: utf-8 -*-
"""Личный кабинет нового интерфейса: мои проверки, профиль, пароль, Telegram, выход.

Проверки привязываются к владельцу при загрузке (owner_id в status.json) и при запуске из Telegram-бота
(started_by = tg:<логин>). Проверки, загруженные до появления кабинета, ни к кому не привязаны.
"""
from __future__ import annotations

import time
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dxaqc.web import accounts as A
from dxaqc.web import ask

router = APIRouter(include_in_schema=False)
ctx: dict = {}


def my_runs(user: dict, limit: int = 100) -> list[dict]:
    out = []
    for r in ctx["list_runs"](500):
        if r.get("owner_id") == user["id"] or r.get("started_by") == f"tg:{user['login']}":
            out.append(r)
    return out[:limit]


@router.get("/cabinet", response_class=HTMLResponse)
def cabinet(request: Request, msg: str = "", err: str = ""):
    user = request.state.user
    if not user:
        return RedirectResponse("/login?next=/cabinet", status_code=303)
    full = A.get_user(user["id"]) or user
    since = time.strftime("%d.%m.%Y", time.gmtime((full.get("created") or 0) + 3 * 3600)) if full.get("created") else ""
    return ctx["templates"].TemplateResponse(request, "cabinet.html", dict(
        user=user, csrf=request.state.csrf, runs=my_runs(user), since=since, tg=A.tg_link_for_user(user["id"]),
        message={"password": "Пароль изменён."}.get(msg, ""), error=err[:200], version=ctx.get("version", "")))


@router.post("/cabinet/password")
def cabinet_password(request: Request, old: str = Form(""), new: str = Form(""), new2: str = Form(""), csrf: str = Form("")):
    user = request.state.user
    if not user:
        return RedirectResponse("/login?next=/cabinet", status_code=303)
    ask._check_csrf(request, csrf)
    try:
        A.authenticate(user["login"], old, ask._ip(request))
        if new != new2:
            raise A.AccountError("новые пароли не совпадают")
        A.set_password(user["id"], new)
    except A.AccountError as exc:
        return RedirectResponse("/cabinet?err=" + quote(str(exc)) + "#password", status_code=303)
    return RedirectResponse("/cabinet?msg=password#password", status_code=303)
