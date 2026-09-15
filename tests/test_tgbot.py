# -*- coding: utf-8 -*-
"""Telegram-бот: привязка аккаунта, команды, проверки наборов и файлов с прогрессом, атласы, запросы админам.
Bot API подменяется записывающим транспортом — в Telegram ничего не уходит."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SEED_ZIP = ROOT / "Для теста.zip"
PASSWORD = "correct-horse-1"
needs_data = pytest.mark.skipif(not (SEED_ZIP.exists() and (ROOT / "data" / "Для теста").exists()), reason="нет данных организатора")


def mods():
    return sys.modules["dxaqc.web.accounts"], sys.modules["dxaqc.web.tgbot"]


class FakeAPI:
    def __init__(self):
        self.calls, self.mid, self.files = [], 100, {}

    def __call__(self, method, params, timeout):
        self.calls.append((method, params))
        if method in ("sendMessage", "editMessageText", "sendPhoto"):
            self.mid += 1
            return {"ok": True, "result": {"message_id": self.mid, "chat": {"id": params.get("chat_id")}}}
        if method == "getFile":
            return {"ok": True, "result": {"file_path": params["file_id"]}}
        return {"ok": True, "result": True}

    def last(self, method, chat=None):
        for m, p in reversed(self.calls):
            if m == method and (chat is None or p.get("chat_id") == chat):
                return p
        return None

    def texts(self, chat):
        return [p["text"] for m, p in self.calls if m in ("sendMessage", "editMessageText") and p.get("chat_id") == chat]


def msg(chat, text=None, **extra):
    m = {"message_id": 1, "chat": {"id": chat, "type": "private"}, "from": {"id": chat, "username": f"u{chat}"}}
    if text is not None:
        m["text"] = text
    m.update(extra)
    return {"update_id": chat, "message": m}


def callback(chat, data):
    return {"update_id": chat, "callback_query": {"id": "cq", "data": data, "from": {"id": chat},
                                                   "message": {"message_id": 77, "chat": {"id": chat, "type": "private"}}}}


@pytest.fixture()
def bot(client):
    A, T = mods()
    api = FakeAPI()
    b = T.Bot("test-token", transport=api)
    b.fetch_file = lambda path: api.files[path]
    b.api_log = api
    old = T.BOT
    T.BOT = b
    yield b
    T.BOT = old


def link(bot, chat, login, admin=False):
    A, _ = mods()
    user = A.get_user_by_login(login) or A.create_user(login, PASSWORD, role="admin" if admin else "user", can_ask=admin)
    bot.handle(msg(chat, f"/start link_{A.create_tg_code(user)}"))
    return A.get_user_by_login(login)


def wait_final(bot, run_id, timeout=150):
    A, _ = mods()
    t0 = time.time()
    while time.time() - t0 < timeout:
        bot.tick()
        if not any(w["run_id"] == run_id for w in A.tg_active_runs()):
            return
        time.sleep(0.4)
    raise AssertionError("прогон из бота не завершился")


def run_of(bot, chat):
    text = bot.api_log.last("sendMessage", chat)["reply_markup"]["inline_keyboard"][0][0]["url"]
    return text.rsplit("/runs/", 1)[1]


def test_linking_commands_and_account_page(client, bot):
    A, T = mods()
    api = bot.api_log
    bot.handle(msg(501, "/start"))
    assert "Привязать аккаунт" in str(api.last("sendMessage", 501)["reply_markup"])
    bot.handle(msg(501, "/check test"))
    assert "привязанные аккаунты" in api.last("sendMessage", 501)["text"]
    bot.handle(msg(501, "/start link_wrongcode"))
    assert "не найден или устарел" in api.last("sendMessage", 501)["text"]

    user = link(bot, 501, "tg-user")
    assert A.tg_user(501)["login"] == "tg-user" and "привязан к аккаунту <b>tg-user</b>" in api.last("sendMessage", 501)["text"]
    bot.handle(msg(501, "/me"))
    assert "tg-user" in api.last("sendMessage", 501)["text"]
    bot.handle(msg(501, "/datasets"))
    assert "test" in api.last("sendMessage", 501)["text"]
    bot.handle(msg(501, "/nope"))
    assert "Такой команды нет" in api.last("sendMessage", 501)["text"]
    bot.handle({"update_id": 9, "message": {"chat": {"id": -100, "type": "group"}, "text": "/help"}})
    assert api.last("sendMessage", -100) is None, "в группах бот молчит"

    web = TestClient(client.app)
    web.post("/login", data={"login": "tg-user", "password": PASSWORD})
    page = web.get("/account").text
    assert "Подключён" in page and "отключить Telegram" in page
    token = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    web.post("/account/telegram/unlink", data={"csrf": token})
    assert A.tg_user(501) is None
    r = web.post("/account/telegram", data={"csrf": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://t.me/QuJump_bot?start=link_")
    code = r.headers["location"].split("link_", 1)[1]
    bot.handle(msg(502, f"/start link_{code}"))
    assert A.tg_user(502)["login"] == "tg-user"
    bot.handle(msg(503, f"/start link_{code}"))
    assert A.tg_user(503) is None, "код одноразовый"
    web.close()


@needs_data
def test_dataset_check_progress_and_summary(client, bot):
    A, _ = mods()
    api = bot.api_log
    link(bot, 601, "tg-runner")
    bot.handle(msg(601, "/check test"))
    run_id = run_of(bot, 601)
    assert "▱" in api.last("sendMessage", 601)["text"] or "▰" in api.last("sendMessage", 601)["text"]
    wait_final(bot, run_id)
    final = api.last("editMessageText", 601)
    assert final["text"].startswith("<b>Готово") and "Снимков 3" in final["text"]
    buttons = str(final["reply_markup"])
    assert "Открыть прогон" in buttons and f"bad:{run_id}" in buttons and "atlas:" not in buttons, "атласы организатора не предлагаются"
    bot.handle(callback(601, f"bad:{run_id}"))
    assert api.last("sendMessage", 601)["text"]
    bot.handle(callback(601, f"atlas:{run_id}"))
    assert not any(m == "sendPhoto" for m, _ in api.calls)
    assert "организатора" in api.last("answerCallbackQuery")["text"]
    bot.handle(callback(601, f"run:{run_id}"))
    assert "Готово" in api.last("sendMessage", 601)["text"]
    bot.handle(msg(601, "/runs"))
    assert "Последние прогоны" in api.last("sendMessage", 601)["text"]


@needs_data
def test_upload_atlases_and_admin_request_buttons(client, bot):
    A, T = mods()
    api = bot.api_log
    user = link(bot, 701, "tg-uploader")
    api.files["doc-seed"] = SEED_ZIP.read_bytes()
    bot.handle(msg(701, document={"file_id": "doc-seed", "file_name": "Для теста.zip", "file_size": SEED_ZIP.stat().st_size}))
    assert any("серверы Telegram" in t for t in api.texts(701))
    run_id = run_of(bot, 701)
    wait_final(bot, run_id)
    assert f"atlas:{run_id}" in str(api.last("editMessageText", 701)["reply_markup"])
    bot.handle(callback(701, f"atlas:{run_id}"))
    photos = [p for m, p in api.calls if m == "sendPhoto"]
    assert photos and all(f"/runs/{run_id}/files/" in p["photo"] for p in photos)
    bot.handle(msg(701, document={"file_id": "big", "file_name": "x.zip", "file_size": 30 * 1024 * 1024}))
    assert "больше 20 МБ" in api.last("sendMessage", 701)["text"]

    # запрос на анализ приходит админу с кнопками, решение из Telegram применяется
    admin = link(bot, 801, "tg-admin", admin=True)
    man = client.get(f"/api/runs/{run_id}").json()
    row = next(r for r in man["rows"] if r["processing_status"] == "Success")
    req = A.add_request(user, "claude", run_id, row["path_to_study"], "snimok.dcm", "проверка")
    T.notify_request(req)
    note = api.last("sendMessage", 801)
    assert f"req:ok:{req['id']}" in str(note["reply_markup"]) and "внешний сервис" in note["text"]
    bot.handle(callback(701, f"req:ok:{req['id']}"))
    assert A.get_request(req["id"])["status"] == "pending", "не админ не решает"
    bot.handle(callback(801, f"req:ok:{req['id']}"))
    done = A.get_request(req["id"])
    assert done["status"] == "approved" and done["question_id"]
    assert "одобрен" in api.last("editMessageText", 801)["text"]
