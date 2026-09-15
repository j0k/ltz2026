# -*- coding: utf-8 -*-
"""Бот в командной группе: разрешение группы, приветствие с закрепом, команды, молчание, разворачивание ссылок
и тикетов, уведомления команде. Bot API подменяется записывающим транспортом."""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

from test_tgbot import FakeAPI, callback, link, mods, msg

GROUP = -1001234


def gmsg(text=None, uid=900, chat=GROUP, **extra):
    upd = msg(uid, text, **extra)
    m = upd["message"]
    m.update(message_id=55, chat={"id": chat, "type": "supergroup", "title": "Квантовый Скачок"},
             **{"from": {"id": uid, "username": f"u{uid}", "is_bot": False}})
    return upd


def member(uid, status="member", chat=GROUP):
    return {"update_id": 1, "my_chat_member": {"chat": {"id": chat, "type": "supergroup", "title": "Квантовый Скачок"},
                                               "from": {"id": uid}, "new_chat_member": {"status": status, "user": {"id": 1, "is_bot": True}}}}


def sent_to(api, chat):
    return [p for m, p in api.calls if m == "sendMessage" and p.get("chat_id") == chat]


@pytest.fixture()
def bot(client, monkeypatch):
    A, T = mods()
    api = FakeAPI()
    b = T.Bot("test-token", transport=api)
    b.api_log = api
    monkeypatch.setattr(T, "OWNERS", set())
    monkeypatch.setattr(T, "BOT", b)
    return b


def test_group_admission_welcome_commands_and_silence(client, bot):
    A, T = mods()
    api = bot.api_log
    link(bot, 811, "tg-gadmin", admin=True)
    bot.handle(member(900))
    assert A.tg_group(GROUP)["status"] == "pending"
    assert f"grp:ok:{GROUP}" in str(api.last("sendMessage", 811)["reply_markup"]), "админу — кнопки решения"
    bot.handle(gmsg("/status"))
    assert not sent_to(api, GROUP), "до разрешения группа молчит"

    bot.handle(callback(900, f"grp:ok:{GROUP}"))
    assert A.tg_group(GROUP)["status"] == "pending", "не админ группу не разрешает"
    bot.handle(callback(811, f"grp:ok:{GROUP}"))
    assert A.tg_group(GROUP)["status"] == "allowed"
    welcome = sent_to(api, GROUP)[-1]
    assert T.ctx["public_url"] + "/" in welcome["text"] and "Трекер" in welcome["text"]
    assert welcome["link_preview_options"]["url"] == T.ctx["public_url"] + "/"
    assert api.last("pinChatMessage")["chat_id"] == GROUP
    assert "разрешена" in api.last("editMessageText", 811)["text"]

    n = len(sent_to(api, GROUP))
    for text in ("привет всем", "/help@OtherBot", "/unknown", "обсуждаем #чтото"):
        bot.handle(gmsg(text))
    bot.handle(gmsg(document={"file_id": "x", "file_name": "a.dcm", "file_size": 10}))
    assert len(sent_to(api, GROUP)) == n, "на обычные сообщения, чужие команды и файлы бот молчит"
    assert not any(m == "getFile" for m, _ in api.calls)

    bot.handle(gmsg("/status@QuJump_bot"))
    assert "версия" in sent_to(api, GROUP)[-1]["text"]
    bot.handle(gmsg("@QuJump_bot что ты умеешь?"))
    last = sent_to(api, GROUP)[-1]
    assert "/site" in last["text"] and last["reply_parameters"]["message_id"] == 55
    bot.handle(gmsg("/check test"))
    assert "привязанные аккаунты" in sent_to(api, GROUP)[-1]["text"]
    bot.handle(gmsg("/site", is_topic_message=True, message_thread_id=7))
    last = sent_to(api, GROUP)[-1]
    assert last["message_thread_id"] == 7 and "Трекер" in last["text"], "ответ в ту же тему форума"

    bot.handle(member(900, "left"))
    assert A.tg_group(GROUP) is None


def test_owner_adds_group_and_admin_blocks_other(client, bot, monkeypatch):
    A, T = mods()
    api = bot.api_log
    monkeypatch.setattr(T, "OWNERS", {555})
    bot.handle(member(555, chat=-1002))
    assert A.tg_group(-1002)["status"] == "allowed" and sent_to(api, -1002), "владелец подключает сразу"
    bot.handle(gmsg("/site", uid=900, chat=-1002))
    assert "Документы ТЗ" in sent_to(api, -1002)[-1]["text"]

    bot.handle(member(901, chat=-1003))
    assert f"grp:no:-1003" in str(api.last("sendMessage", 555)["reply_markup"])
    bot.handle(callback(555, "grp:no:-1003"))
    assert A.tg_group(-1003)["status"] == "blocked" and api.last("leaveChat")["chat_id"] == -1003
    api.calls.clear()
    bot.handle(gmsg("/status", uid=901, chat=-1003))
    assert api.last("leaveChat")["chat_id"] == -1003 and not sent_to(api, -1003)


def fake_train_run(run_id):
    app = sys.modules["dxaqc.web.app"]
    out = os.path.join(app.RUNS, run_id, "out")
    os.makedirs(out, exist_ok=True)
    now = time.time()
    with open(os.path.join(app.RUNS, run_id, "status.json"), "w") as f:
        json.dump(dict(state="done", title="Тестовый прогон всего набора", created=now, finished=now, dataset="train", studies=100), f)
    rows = [dict(key="abc123", path_to_study="s1/img.dcm", anatomical_region="lumbar_spine", quality_class=1,
                 violation_list=["spine_axis_tilt"], processing_status="Success", explanations=[])]
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(dict(summary=dict(images=4, good=2, bad=1, not_evaluated=1, failures=0, studies=100, mean_time=0.5),
                       rows=rows, evaluation=dict(spine_overall=dict(f1=0.81, n=100))), f)


def test_unfurl_links_tickets_and_team_announcements(client, bot, monkeypatch):
    A, T = mods()
    api = bot.api_log
    chat, run_id, u = -1004, "20260916-010203-abc123", T.ctx["public_url"]
    A.tg_group_save(chat, "Команда", "allowed", "test")
    A.tg_state("announce_since", str(time.time() - 60))
    A.tg_state("announced_version", "0.0.0")
    fake_train_run(run_id)
    monkeypatch.setattr(T, "TRAC_INTERNAL", "http://trac.local")
    monkeypatch.setattr(T, "fetch_ticket", lambda n: {"summary": "Группа: уведомления команде", "status": "new",
                                                      "milestone": "Бот"} if n == 103 else None)

    bot.handle(gmsg(f"глянь {u}/runs/{run_id} и {u}/runs/{run_id}/images/abc123 по тикету #103 и #9999", chat=chat))
    reply = sent_to(api, chat)[-1]
    assert reply["reply_parameters"]["message_id"] == 55
    assert "Тестовый прогон всего набора" in reply["text"] and "img.dcm" in reply["text"] and "✕ нарушение" in reply["text"]
    assert "#103</a> Группа: уведомления команде · новый" in reply["text"] and "9999" not in reply["text"]

    bot.handle(gmsg(f"/run {run_id}", chat=chat))
    assert "atlas:" not in str(sent_to(api, chat)[-1]["reply_markup"]), "в группе без атласов"

    bot.announce()
    texts = [p["text"] for p in sent_to(api, chat)]
    assert any("обновлён до версии" in t for t in texts)
    assert any("обучающего набора" in t and "F1 0,81" in t for t in texts)
    n = len(sent_to(api, chat))
    bot.announce()
    assert len(sent_to(api, chat)) == n, "каждое событие — один раз"


def test_pending_group_of_owner_is_admitted_on_start(client, bot, monkeypatch):
    """Владелец команды добавил бота, но в личку боту не писал: уведомление ему уйти не может,
    поэтому группа разрешается при старте по сохранённому id того, кто её подключил."""
    A, T = mods()
    api, chat = bot.api_log, -1005
    monkeypatch.setattr(T, "OWNERS", {777})
    bot.handle(member(777, chat=chat))
    assert A.tg_group(chat)["status"] == "allowed" and A.tg_group(chat)["added_by_id"] == 777, "id подключившего сохранён"

    A.tg_group_set(chat, status="pending")          # как будто владельца не узнали при добавлении
    api.calls.clear()
    bot.admit_pending()
    assert A.tg_group(chat)["status"] == "allowed"
    assert any("Привет, команда" in p["text"] for p in sent_to(api, chat)), "приветствие отправлено"

    A.tg_group_save(-1006, "Чужая", "pending", "кто-то", 999)
    bot.admit_pending()
    assert A.tg_group(-1006)["status"] == "pending", "чужую группу сама собой не разрешаем"


def test_pending_group_explains_itself_once(client, bot, monkeypatch):
    """В неразрешённой группе бот молчит, но на прямое обращение один раз объясняет причину."""
    A, T = mods()
    api, chat = bot.api_log, -1007
    monkeypatch.setattr(T, "OWNERS", set())
    bot.handle(gmsg("/status", chat=chat))                    # регистрирует группу как ожидающую
    assert A.tg_group(chat)["status"] == "pending" and not sent_to(api, chat)
    bot.handle(gmsg("привет всем", chat=chat))
    assert not sent_to(api, chat), "на обычные сообщения по-прежнему молчит"

    bot.handle(gmsg("/help@QuJump_bot", chat=chat))
    note = sent_to(api, chat)[-1]
    assert "ещё не подключили" in note["text"] and note["reply_parameters"]["message_id"] == 55
    bot.handle(gmsg("@QuJump_bot ау", chat=chat))
    assert len(sent_to(api, chat)) == 1, "объясняет один раз, а не на каждое сообщение"
