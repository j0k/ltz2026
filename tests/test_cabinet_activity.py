# -*- coding: utf-8 -*-
"""Личный кабинет нового интерфейса и живая лента действий для админов."""
from __future__ import annotations

import io
import re
import sys
import time

from fastapi.testclient import TestClient
from PIL import Image

PASSWORD = "correct-horse-1"


def A():
    return sys.modules["dxaqc.web.accounts"]


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def register(app, login):
    c = TestClient(app)
    r = c.post("/register", data={"login": login, "password": PASSWORD, "password2": PASSWORD}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/cabinet", "после регистрации — кабинет"
    return c


def jpg():
    buf = io.BytesIO(); Image.new("L", (40, 30), 90).save(buf, "JPEG")
    return buf.getvalue()


def events(**kw):
    return [e for e in A().events_recent(500) if all(e.get(k) == v for k, v in kw.items())]


def test_helpers_mask_ip_and_device(client):
    act = sys.modules["dxaqc.web.activity"]
    assert act.mask_ip("194.87.26.51") == "194.87.*.*" and act.mask_ip("2a02:6b8:0:1::1") == "2a02:6b8:*"
    assert act.device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit Version/17.0 Mobile Safari/604.1") == "Safari · iPhone"
    assert act.device("Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/128.0 Safari/537.36") == "Chrome · Windows"


def test_cabinet_register_and_my_runs(client):
    guest = TestClient(client.app)
    assert guest.get("/cabinet", follow_redirects=False).headers["location"] == "/login?next=/cabinet"
    head = guest.get("/").text
    assert 'href="/register"' in head and 'href="/login">Войти' in head

    alice = register(client.app, "cab-alice")
    home = alice.get("/").text
    assert 'href="/cabinet">Кабинет · cab-alice' in home and 'href="/register"' not in home
    page = alice.get("/cabinet").text
    assert "Личный кабинет" in page and "Мои проверки" in page and "Здесь появятся ваши проверки" in page

    r = alice.post("/runs", files=[("files", ("photo.jpg", jpg(), "image/jpeg"))], data={"ui": "v2"}, follow_redirects=False)
    rid = r.headers["location"].rsplit("/", 1)[1]
    assert f'href="/check/{rid}"' in alice.get("/cabinet").text, "загрузка попала в «Мои проверки»"
    bob = register(client.app, "cab-bob")
    assert f'href="/check/{rid}"' not in bob.get("/cabinet").text, "чужие проверки не видны"

    token = csrf(alice.get("/cabinet").text)
    bad = alice.post("/cabinet/password", data={"old": "wrong-password", "new": "another-pass-9", "new2": "another-pass-9", "csrf": token},
                     follow_redirects=False)
    assert "err=" in bad.headers["location"]
    ok = alice.post("/cabinet/password", data={"old": PASSWORD, "new": "another-pass-9", "new2": "another-pass-9", "csrf": token},
                    follow_redirects=False)
    assert ok.headers["location"].startswith("/cabinet?msg=password")
    assert "Пароль изменён" in alice.get("/cabinet?msg=password").text
    A().set_password(A().get_user_by_login("cab-alice")["id"], PASSWORD)


def test_activity_feed_records_and_is_admin_only(client):
    before = (A().events_recent(1) or [{"id": 0}])[0]["id"]
    guest = TestClient(client.app, headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/128.0 Safari/537.36"})
    guest.get("/")
    guest.get("/api/health"); guest.get("/static/v2.css")
    guest.post("/login", data={"login": "nobody-here", "password": "wrong-password-1"})
    carol = register(client.app, "act-carol")
    r = carol.post("/runs", files=[("files", ("photo.jpg", jpg(), "image/jpeg"))], data={"ui": "v2"}, follow_redirects=False)
    rid = r.headers["location"].rsplit("/", 1)[1]
    t0 = time.time()
    while time.time() - t0 < 60 and carol.get(f"/api/runs/{rid}/progress").json()["state"] not in ("done", "error"):
        time.sleep(0.3)
    new = [e for e in A().events_after(before, 500)]
    actions = [(e["kind"], e["action"], e["login"]) for e in new]
    assert ("view", "открыл главную", "") in actions
    assert ("auth", "неудачная попытка входа", "nobody-here") in actions
    assert ("auth", "зарегистрировался", "act-carol") in actions
    assert ("action", "загрузил файлы на проверку", "act-carol") in actions
    assert any(k == "system" and a.startswith("проверка завершена") and who == "act-carol" for k, a, who in actions), actions
    assert not any("/api/health" in e["path"] or "/static/" in e["path"] for e in new), "служебное не пишется"
    upload = next(e for e in new if e["action"] == "загрузил файлы на проверку")
    assert upload["run_id"] == rid and upload["ip"] in ("testclient", "") or upload["ip"].endswith("*"), upload

    assert carol.get("/admin/activity").status_code == 403 and carol.get("/admin/api/activity").status_code == 403
    assert TestClient(client.app).get("/admin/activity", follow_redirects=False).status_code == 303
    A().get_user_by_login("act-admin") or A().create_user("act-admin", PASSWORD, role="admin")
    admin = TestClient(client.app)
    admin.post("/login", data={"login": "act-admin", "password": PASSWORD})
    page = admin.get("/admin/activity").text
    assert "Активность на стенде" in page and "act-carol" in page and "зарегистрировался" in page
    data = admin.get(f"/admin/api/activity?after={before}").json()
    assert any(e["action"] == "зарегистрировался" and e["who"] == "act-carol" for e in data["events"]) and "online" in data
    with admin.stream("GET", f"/admin/api/activity/stream?after={before}&once=1") as s:
        body = "".join(s.iter_text())
    assert "event: activity" in body and "act-carol" in body
    assert 'href="/admin/activity">Активность' in admin.get("/").text, "ссылка в шапке для админа"
