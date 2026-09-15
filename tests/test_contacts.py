# -*- coding: utf-8 -*-
"""Контакты организаторов видны только админам: в админке есть, в публичной части стенда нет."""
from __future__ import annotations

import re
import sys

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-1"


def accounts():
    return sys.modules["dxaqc.web.accounts"]


def login(app, login_name, admin=False):
    A = accounts()
    if not A.get_user_by_login(login_name):
        A.create_user(login_name, PASSWORD, role="admin" if admin else "user")
    c = TestClient(app)
    c.post("/login", data={"login": login_name, "password": PASSWORD})
    return c


def test_contacts_visible_to_admin_only(client):
    from dxaqc.web import contacts as C

    admin = login(client.app, "contacts-admin", admin=True)
    page = admin.get("/admin")
    assert page.status_code == 200
    for needle in (C.SUPPORT["tg"], C.SUPPORT["email"], C.MODERATOR["name"], C.MODERATOR["tg"]):
        assert needle in page.text, needle
    for e in C.EXPERTS:
        assert e["name"] in page.text and e["role"][:20] in page.text
    assert 'href="https://t.me/treker_antonzel"' in page.text and "mailto:" in page.text
    assert "#contacts" in page.text, "вкладка раздела"
    admin.close()

    user = login(client.app, "contacts-user")
    assert user.get("/admin").status_code == 403
    user.close()

    # публичные страницы контактов не показывают
    for path in ("/", "/runs", "/tz/"):
        r = client.get(path)
        if r.status_code == 200:
            assert C.MODERATOR["tg"] not in r.text and C.SUPPORT["email"] not in r.text, path
