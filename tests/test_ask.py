# -*- coding: utf-8 -*-
"""Тесты вопросов к Claude: регистрация, вход, роли, CSRF, лимиты, одобрение исполнения, журнал, очистка ответа.

Брокер поддельный (tests/conftest.py): отвечает сразу и запоминает, в каком режиме пришёл вопрос.
"""
from __future__ import annotations

import re
import sys
import time

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-1"


def accounts():
    return sys.modules["dxaqc.web.accounts"]


def csrf_of(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, "на странице нет CSRF-токена"
    return m.group(1)


@pytest.fixture()
def new_client(client):
    """Отдельный браузер со своими cookie на том же приложении (исполнитель уже запущен основным клиентом)."""
    made = []

    def make():
        c = TestClient(client.app)
        made.append(c)
        return c
    yield make
    for c in made:
        c.close()


def register(c: TestClient, login: str, password: str = PASSWORD) -> TestClient:
    r = c.post("/register", data={"login": login, "password": password, "password2": password}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/cabinet", r.text[:300]   # с 21.09 после регистрации — кабинет
    return c


def make_admin(new_client, login: str) -> TestClient:
    accounts().create_user(login, PASSWORD, role="admin", can_ask=True, daily_limit=1000)
    c = new_client()
    r = c.post("/login", data={"login": login, "password": PASSWORD, "next": "/admin"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    return c


def admin_action(admin: TestClient, login: str, action: str, **extra):
    uid = accounts().get_user_by_login(login)["id"]
    r = admin.post(f"/admin/users/{uid}", data={"action": action, "csrf": csrf_of(admin.get("/admin").text), **extra},
                   follow_redirects=False)
    return r


def ask(c: TestClient, text: str, want_exec: bool = False):
    data = {"text": text, "csrf": csrf_of(c.get("/account").text)}
    if want_exec:
        data["want_exec"] = "1"
    return c.post("/ask", data=data, follow_redirects=False)


def last_question(login: str) -> dict:
    return accounts().user_questions(accounts().get_user_by_login(login)["id"], 1)[0]


def wait_status(c: TestClient, qid: int, final=("done", "error", "rejected", "awaiting_approval"), timeout=10) -> str:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get(f"/api/ask/{qid}").json()["status"]
        if st in final:
            return st
        time.sleep(0.05)
    pytest.fail(f"вопрос {qid} не дошёл до {final}")


# ------------------------------------------------------------------ доступ без входа

def test_pages_require_login(new_client):
    c = new_client()
    for path in ("/ask", "/account", "/admin"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login?next=" + path
    assert c.get("/api/ask/1").status_code == 404
    assert c.post("/ask", data={"text": "x"}, follow_redirects=False).status_code == 303
    header = c.get("/v1").text
    assert 'href="/login">Войти</a>' in header and 'href="/admin"' not in header


def test_login_next_cannot_redirect_away(new_client):
    c = new_client()
    assert 'name="next" value="/cabinet"' in c.get("/login", params={"next": "//evil.example/x"}).text
    register(c, "nexttest")
    c.cookies.clear()
    r = c.post("/login", data={"login": "nexttest", "password": PASSWORD, "next": "https://evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/cabinet"   # вход без next — в кабинет


# ------------------------------------------------------------------ регистрация и вход

@pytest.mark.parametrize("login, password, password2, message", [
    ("ab", PASSWORD, PASSWORD, "логин: 3–32 символа"),
    ("имя", PASSWORD, PASSWORD, "логин: 3–32 символа"),
    ("shortpw", "short", "short", "пароль не короче 10 символов"),
    ("mismatch", PASSWORD, PASSWORD + "x", "пароли не совпадают"),
])
def test_registration_validation(new_client, login, password, password2, message):
    r = new_client().post("/register", data={"login": login, "password": password, "password2": password2})
    assert r.status_code == 400 and message in r.text


def test_register_login_logout_and_cookie_flags(new_client):
    c = new_client()
    r = c.post("/register", data={"login": "alice", "password": PASSWORD, "password2": PASSWORD}, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "dxaqc_sid=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "Логин уже занят" not in r.text
    dup = new_client().post("/register", data={"login": "ALICE", "password": PASSWORD, "password2": PASSWORD})
    assert dup.status_code == 400 and "такой логин уже занят" in dup.text

    page = c.get("/ask").text
    assert "Доступ к вопросам ещё не выдан" in page and 'href="/account">alice</a>' in page
    denied = ask(c, "можно?")
    # без доступа страница показывает уведомление вместо формы, вопрос не создаётся
    assert denied.status_code == 400 and "ещё не выдан" in denied.text
    assert accounts().user_questions(accounts().get_user_by_login("alice")["id"]) == []

    assert c.post("/logout", data={"csrf": "wrong"}, follow_redirects=False).status_code == 403
    assert c.post("/logout", data={"csrf": csrf_of(c.get("/account").text)}, follow_redirects=False).status_code == 303
    assert c.get("/ask", follow_redirects=False).status_code == 303

    again = c.post("/login", data={"login": "alice", "password": PASSWORD}, follow_redirects=False)
    assert again.status_code == 303 and c.get("/ask").status_code == 200


def test_login_throttling(new_client):
    c = register(new_client(), "bruteforce")
    c.cookies.clear()
    for _ in range(5):
        assert "неверный логин или пароль" in c.post("/login", data={"login": "bruteforce", "password": "wrong-password"}).text
    r = c.post("/login", data={"login": "bruteforce", "password": PASSWORD})
    assert r.status_code == 400 and "слишком много попыток" in r.text


def test_change_password(new_client):
    c = register(new_client(), "changer")
    token = csrf_of(c.get("/account").text)
    bad = c.post("/account/password", data={"old": "not-my-password", "new": "new-password-2", "new2": "new-password-2", "csrf": token})
    assert bad.status_code == 400
    ok = c.post("/account/password", data={"old": PASSWORD, "new": "new-password-2", "new2": "new-password-2", "csrf": token})
    assert ok.status_code == 200 and "пароль изменён" in ok.text
    c2 = new_client()
    assert c2.post("/login", data={"login": "changer", "password": "new-password-2"}, follow_redirects=False).status_code == 303


# ------------------------------------------------------------------ админка и вопросы

def test_non_admin_cannot_use_admin(new_client):
    c = register(new_client(), "mallory")
    token = csrf_of(c.get("/account").text)
    assert c.get("/admin").status_code == 403
    uid = accounts().get_user_by_login("mallory")["id"]
    assert c.post(f"/admin/users/{uid}", data={"action": "grant", "csrf": token}).status_code == 403
    assert c.post("/admin/questions/1", data={"decision": "approve", "csrf": token}).status_code == 403


def test_read_question_flow_and_limit(new_client, broker):
    admin = make_admin(new_client, "root1")
    user = register(new_client(), "bob")
    assert admin_action(admin, "bob", "grant").status_code == 303
    assert admin_action(admin, "bob", "limit", daily_limit="2").status_code == 303

    r = ask(user, "Где считается угол оси?")
    assert r.status_code == 303 and r.headers["location"].startswith("/ask#q")
    q = last_question("bob")
    assert q["mode"] == "read" and wait_status(user, q["id"]) == "done"
    assert broker.calls[-1]["mode"] == "read" and broker.calls[-1]["user"] == "bob"
    assert "Ответ (read) на: Где считается угол оси?" in user.get("/ask").text

    ask(user, "второй вопрос")
    over = ask(user, "третий вопрос")
    assert over.status_code == 400 and "лимит на сегодня исчерпан: 2" in over.text

    other = register(new_client(), "eve")
    assert other.get(f"/api/ask/{q['id']}").status_code == 404, "чужой вопрос не должен быть виден"
    assert admin.get(f"/api/ask/{q['id']}").status_code == 200


def test_exec_needs_admin_approval(new_client, broker):
    admin = make_admin(new_client, "root2")
    user = register(new_client(), "carol")
    admin_action(admin, "carol", "grant")

    calls_before = len(broker.calls)
    ask(user, "Запусти тесты", want_exec=True)
    q = last_question("carol")
    assert q["mode"] == "full" and q["status"] == "awaiting_approval"
    time.sleep(0.3)
    assert len(broker.calls) == calls_before, "до одобрения вопрос не должен уйти в брокер"
    assert "Запусти тесты" in admin.get("/admin").text

    assert user.post(f"/admin/questions/{q['id']}", data={"decision": "approve", "csrf": csrf_of(user.get("/account").text)}).status_code == 403
    r = admin.post(f"/admin/questions/{q['id']}", data={"decision": "approve", "csrf": csrf_of(admin.get("/admin").text)}, follow_redirects=False)
    assert r.status_code == 303
    assert wait_status(user, q["id"], final=("done", "error")) == "done"
    call = broker.calls[-1]
    assert call["mode"] == "full" and call["approver"] == "root2"
    assert "root2" in admin.get("/admin").text

    ask(user, "Удали всё", want_exec=True)
    q2 = last_question("carol")
    admin.post(f"/admin/questions/{q2['id']}", data={"decision": "reject", "csrf": csrf_of(admin.get("/admin").text)})
    assert accounts().get_question(q2["id"])["status"] == "rejected"
    again = admin.post(f"/admin/questions/{q2['id']}", data={"decision": "approve", "csrf": csrf_of(admin.get("/admin").text)})
    assert again.status_code == 400 and "не ждёт одобрения" in again.text


def test_request_exec_after_read_answer(new_client):
    admin = make_admin(new_client, "root3")
    user = register(new_client(), "dave")
    admin_action(admin, "dave", "grant")
    ask(user, "Посчитай строки кода")
    q = last_question("dave")
    wait_status(user, q["id"])
    page = user.get("/ask").text
    assert f'action="/ask/{q["id"]}/exec"' in page
    r = user.post(f"/ask/{q['id']}/exec", data={"csrf": csrf_of(page)}, follow_redirects=False)
    assert r.status_code == 303
    new = last_question("dave")
    assert new["mode"] == "full" and new["status"] == "awaiting_approval" and new["parent_id"] == q["id"]


def test_broker_error_is_shown(new_client):
    admin = make_admin(new_client, "root4")
    user = register(new_client(), "frank")
    admin_action(admin, "frank", "grant")
    ask(user, "FAIL please")
    q = last_question("frank")
    assert wait_status(user, q["id"]) == "error"
    assert "сломалось в брокере" in user.get("/ask").text


def test_answer_markdown_is_rendered_safely(new_client):
    admin = make_admin(new_client, "root5")
    user = register(new_client(), "grace")
    admin_action(admin, "grace", "grant")
    ask(user, "**жирный** и <script>alert(1)</script> и [ссылка](javascript:alert(1))")
    q = last_question("grace")
    wait_status(user, q["id"])
    page = user.get("/ask").text
    answer = re.search(r'<div class="answer">(.*?)</div>', page, re.S).group(1)
    assert "<strong>жирный</strong>" in answer
    assert "<script>" not in answer and "&lt;script&gt;" in answer
    assert 'href="javascript:' not in answer


def test_admin_safety_and_blocking(new_client):
    admin = make_admin(new_client, "root6")
    me = accounts().get_user_by_login("root6")["id"]
    token = csrf_of(admin.get("/admin").text)
    for action in ("make_user", "block"):
        r = admin.post(f"/admin/users/{me}", data={"action": action, "csrf": token})
        assert r.status_code == 400 and "самого себя" in r.text
    bad = admin_action(admin, "root6", "limit", daily_limit="много")
    assert bad.status_code == 400 and "числом" in bad.text

    victim = register(new_client(), "henry")
    assert victim.get("/ask").status_code == 200
    admin_action(admin, "henry", "block")
    assert victim.get("/ask", follow_redirects=False).status_code == 303, "сессии заблокированного сбрасываются"
    r = new_client().post("/login", data={"login": "henry", "password": PASSWORD})
    assert r.status_code == 400 and "заблокирована" in r.text

    admin_action(admin, "henry", "make_admin")
    assert accounts().get_user_by_login("henry")["role"] == "admin"
    assert 'href="/admin">Админка</a>' in admin.get("/v1").text
