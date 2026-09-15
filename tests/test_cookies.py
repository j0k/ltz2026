# -*- coding: utf-8 -*-
"""Уведомление о cookie и страница с подробностями: честный список того, что стенд хранит в браузере."""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-1"


def test_cookie_notice_and_page(client):
    ask = sys.modules["dxaqc.web.ask"]
    A = sys.modules["dxaqc.web.accounts"]

    home = client.get("/")
    assert home.status_code == 200
    assert 'id="cookieBar"' in home.text and 'hidden' in home.text, "плашка в разметке и скрыта по умолчанию"
    assert 'href="/cookies"' in home.text, "ссылки на подробности"
    assert not home.headers.get("set-cookie"), "гостю cookie не ставим"

    page = client.get("/cookies")
    assert page.status_code == 200
    for needle in (ask.COOKIE, "dxaqc-sound", "dxaqc-cookie-ok", "localStorage",
                   f"{round(A.SESSION_TTL / 86400)} дней", "аналитики"):
        assert needle in page.text, needle
    assert 'id="cookieBar"' in page.text

    # cookie входа появляется только после входа и закрыта от скриптов
    A.get_user_by_login("cookie-user") or A.create_user("cookie-user", PASSWORD)
    c = TestClient(client.app)
    assert not c.get("/").headers.get("set-cookie")
    r = c.post("/login", data={"login": "cookie-user", "password": PASSWORD}, follow_redirects=False)
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert ask.COOKIE in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie, set_cookie
    c.close()
