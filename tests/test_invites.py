# -*- coding: utf-8 -*-
"""Тесты инвайт-ссылок: выдача админом и командой, регистрация и вход по ссылке, одноразовость, срок, отзыв, доступ."""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-1"


def accounts():
    return sys.modules["dxaqc.web.accounts"]


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


@pytest.fixture()
def browsers(client):
    made = []

    def make():
        c = TestClient(client.app)
        made.append(c)
        return c
    yield make
    for c in made:
        c.close()


def admin_browser(browsers, login="inv-admin"):
    A = accounts()
    if not A.get_user_by_login(login):
        A.create_user(login, PASSWORD, role="admin", can_ask=True)
    c = browsers()
    assert c.post("/login", data={"login": login, "password": PASSWORD}, follow_redirects=False).status_code == 303
    return c


def create_via_admin(admin, role="admin", hours="48", note="тест"):
    page = admin.post("/admin/invites", data={"role": role, "hours": hours, "note": note, "csrf": csrf_of(admin.get("/admin").text)})
    assert page.status_code == 200, page.text[:300]
    url = re.search(r'id="inviteUrl" type="text" value="([^"]+)"', page.text).group(1)
    return url.split("/invite/")[1], page.text


def test_admin_creates_invite_and_newcomer_registers_as_admin(browsers):
    admin = admin_browser(browsers)
    token, page = create_via_admin(admin, note="Алексей — пульт")
    assert "Ссылка создана" in page and "Алексей — пульт" in page

    newcomer = browsers()
    landing = newcomer.get(f"/invite/{token}")
    assert landing.status_code == 200 and "Доступ админа" in landing.text and "inv-admin" in landing.text
    assert f'action="/invite/{token}/register"' in landing.text

    r = newcomer.post(f"/invite/{token}/register", data={"login": "newadmin", "password": PASSWORD, "password2": PASSWORD},
                      follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    u = accounts().get_user_by_login("newadmin")
    assert u["is_admin"] and u["can_ask"]
    assert newcomer.get("/admin").status_code == 200

    again = browsers().get(f"/invite/{token}")
    assert "уже использовано" in again.text
    reuse = browsers().post(f"/invite/{token}/register", data={"login": "second", "password": PASSWORD, "password2": PASSWORD})
    assert reuse.status_code == 400 and "уже использовано" in reuse.text
    assert accounts().get_user_by_login("second") is None, "по использованной ссылке учётная запись не создаётся"
    listing = admin.get("/admin").text
    assert "использована" in listing and "newadmin" in listing


def test_logged_in_user_accepts_ask_invite(browsers):
    admin = admin_browser(browsers)
    token, _ = create_via_admin(admin, role="ask")
    accounts().create_user("plainperson", PASSWORD)
    user = browsers()
    user.post("/login", data={"login": "plainperson", "password": PASSWORD})
    landing = user.get(f"/invite/{token}").text
    assert "Доступ к вопросам Claude" in landing and f'action="/invite/{token}/accept"' in landing
    assert user.post(f"/invite/{token}/accept", data={"csrf": "wrong"}).status_code == 403
    r = user.post(f"/invite/{token}/accept", data={"csrf": csrf_of(landing)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ask"
    u = accounts().get_user_by_login("plainperson")
    assert u["can_ask"] and not u["is_admin"]


def test_login_flow_returns_to_invite(browsers):
    admin = admin_browser(browsers)
    token, _ = create_via_admin(admin)
    anon = browsers()
    r = anon.post(f"/invite/{token}/accept", data={"csrf": "x"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/login?next=/invite/{token}"
    assert f'name="next" value="/invite/{token}"' in anon.get(r.headers["location"]).text


def test_expired_revoked_and_unknown_invites(browsers):
    A = accounts()
    token, _ = A.create_invite("claude", hours=0.0002)
    time.sleep(1)
    assert "срок действия приглашения истёк" in browsers().get(f"/invite/{token}").text.lower()

    admin = admin_browser(browsers)
    token2, _ = create_via_admin(admin)
    iid = A.get_invite(token2)["id"]
    assert admin.post(f"/admin/invites/{iid}/revoke", data={"csrf": csrf_of(admin.get("/admin").text)}, follow_redirects=False).status_code == 303
    assert "отозвано" in browsers().get(f"/invite/{token2}").text
    bad = browsers().post(f"/invite/{token2}/register", data={"login": "latecomer", "password": PASSWORD, "password2": PASSWORD})
    assert bad.status_code == 400 and A.get_user_by_login("latecomer") is None

    unknown = browsers().get("/invite/not-a-real-token")
    assert unknown.status_code == 404 and "не найдено" in unknown.text


def test_only_admins_issue_invites_and_tokens_are_hashed(browsers):
    A = accounts()
    A.create_user("notadmin", PASSWORD)
    user = browsers()
    user.post("/login", data={"login": "notadmin", "password": PASSWORD})
    assert user.post("/admin/invites", data={"role": "admin", "csrf": csrf_of(user.get("/account").text)}).status_code == 403
    assert browsers().post("/admin/invites", data={"role": "admin"}).status_code == 403
    admin = admin_browser(browsers)
    bad = admin.post("/admin/invites", data={"role": "king", "hours": "48", "csrf": csrf_of(admin.get("/admin").text)})
    assert bad.status_code == 400 and "неизвестная роль" in bad.text

    token, inv = A.create_invite("claude")
    with sqlite3.connect(A.DB_PATH) as c:
        stored = [r[0] for r in c.execute("SELECT token_hash FROM invites")]
    assert token not in stored and A._token_hash(token) in stored


def test_cli_prints_working_link(client, tmp_path):
    env = dict(os.environ, DXAQC_PUBLIC_URL="https://stand.example")
    out = subprocess.run([sys.executable, "-m", "dxaqc.web.accounts", "invite", "--role", "admin", "--hours", "2", "--note", "cli"],
                         cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout
    m = re.search(r"https://stand\.example/invite/(\S+)", out)
    assert m and "одноразовая" in out
    inv = accounts().get_invite(m.group(1))
    assert inv and inv["status"] == "active" and inv["created_by"] == "claude" and inv["note"] == "cli"
