# -*- coding: utf-8 -*-
"""Telegram-бот стенда (@QuJump_bot): работа с сервисом из Telegram — в личке и в командной группе.

Бот живёт внутри сервиса: фоновый поток опрашивает Bot API методом getUpdates (вебхук и входящий адрес не нужны),
второй поток ведёт живой прогресс прогонов, запущенных из бота, и уведомления команде. Токен — файл
DXAQC_TG_TOKEN_FILE (в контейнере только на чтение); без токена бот не запускается, остальной сервис работает как обычно.

Личка: привязка к аккаунту стенда одноразовой ссылкой из кабинета; /check test|train [n|all] и приём DICOM или zip
(только привязанным, с суточным лимитом); одно сообщение с прогрессом, которое обновляется до итога с кнопками;
нарушения и атласы своих загрузок по кнопкам; /runs, /run, /datasets, /me, /unlink; админам — запросы на анализ
с кнопками «Одобрить» и «Отклонить».

Группа: работает только в разрешённых группах — разрешает владелец команды (DXAQC_TG_OWNERS) или привязанный админ
стенда, остальные группы ждут решения админа и бот в них молчит. После разрешения — приветствие со ссылками
и закреп; команды /site /status /runs /run /datasets /check /help; ссылки на прогоны и снимки стенда и номера
тикетов #NN разворачиваются в короткий итог; обычные сообщения бот не комментирует. Файлы в группе не обрабатываются,
атласы в группу не отправляются. Команде приходят «стенд обновлён» и итоги прогонов всего обучающего набора.

Файлы, присланные боту, проходят через серверы Telegram, поэтому бот предупреждает об обезличенных данных, а атласы
снимков организатора в Telegram не пересылает.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import Counter

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from dxaqc import __version__
from dxaqc.web import accounts as A
from dxaqc.web import analysis, ask

API = os.environ.get("DXAQC_TG_API", "https://api.telegram.org")
TOKEN_FILE = os.environ.get("DXAQC_TG_TOKEN_FILE", "")
BOT_USERNAME = os.environ.get("DXAQC_TG_BOT", "QuJump_bot")
# Telegram-id владельцев команды: подключают бота к группам без привязки аккаунта стенда
OWNERS = {int(x) for x in re.split(r"[,\s]+", os.environ.get("DXAQC_TG_OWNERS", "")) if re.fullmatch(r"-?\d+", x)}
# Trac изнутри сети контейнеров (снаружи он за паролем) и публичный адрес для ссылок
TRAC_INTERNAL = os.environ.get("DXAQC_TG_TRAC", "").rstrip("/")
TRAC_PUBLIC = os.environ.get("DXAQC_TRAC_URL", "https://ltz2026.juri-konoplev.pro/trac/").rstrip("/") + "/"
MAX_FILE = 20 * 1024 * 1024       # предел скачивания файла ботом в Bot API
DAILY_RUNS = 20
WATCH_EVERY = 3.0
ANNOUNCE_EVERY = 30.0
MAX_UNFURL = 3
ctx: dict = {}
BOT: "Bot | None" = None
router = APIRouter(include_in_schema=False)
esc = lambda s: html.escape(str(s or ""), quote=False)
num = lambda x: str(round(x or 0, 2)).replace(".", ",")
is_group = lambda chat_id: int(chat_id or 0) < 0
TICKET_RE = re.compile(r"(?<![\w/&#])#(\d{1,4})(?!\w)")

COMMANDS = [
    ("check", "проверить набор: /check test, /check train 10, /check train all"),
    ("runs", "последние прогоны стенда"),
    ("run", "итоги прогона: /run <id>"),
    ("datasets", "наборы организатора"),
    ("me", "мой аккаунт и лимит"),
    ("help", "что умеет бот"),
    ("unlink", "отвязать Telegram от аккаунта"),
]
GROUP_COMMANDS = [
    ("site", "ссылки на стенд, трекер и документы"),
    ("status", "версия стенда, очередь, последний прогон всего набора"),
    ("runs", "последние прогоны стенда"),
    ("run", "итоги прогона: /run <id>"),
    ("datasets", "наборы организатора"),
    ("check", "проверка набора с прогрессом в группе (привязанным)"),
    ("help", "что умеет бот в группе"),
]
GROUP_HANDLERS = {"site": "cmd_site", "start": "cmd_site", "status": "cmd_status", "runs": "cmd_runs", "run": "cmd_run",
                  "datasets": "cmd_datasets", "check": "cmd_check", "me": "cmd_me", "help": "cmd_group_help"}
HELP = ("<b>DXA QC · контроль качества денситометрии</b>\n"
        "/check test — фрагмент «Для теста» (3 снимка)\n"
        "/check train 10 — 10 случайных исследований обучающего набора, /check train all — весь набор\n"
        "Пришлите файл DICOM или zip с папками исследований — бот проверит его и пришлёт итог.\n"
        "/runs — последние прогоны, /run &lt;id&gt; — итоги, /datasets — наборы, /me — аккаунт, /unlink — отвязать.\n"
        "Проверки запускают привязанные аккаунты: кабинет стенда → «подключить Telegram».")
GROUP_HELP = ("<b>Бот стенда в группе</b>\n"
              "/site — ссылки на стенд, трекер и документы\n"
              "/status — версия, очередь и последний прогон всего обучающего набора\n"
              "/runs, /run &lt;id&gt; — прогоны и итоги, /datasets — наборы\n"
              "/check test, /check train 10 — проверка с прогрессом прямо здесь (для привязанных аккаунтов)\n"
              "Ссылки на прогоны и снимки стенда и номера тикетов #NN разворачиваю сам, на остальные сообщения молчу. "
              "Файлы с исследованиями в группу не присылайте — свои файлы проверяйте в личке с ботом.")
UPLOAD_WARNING = ("Файл прошёл через серверы Telegram. Присылайте только обезличенные исследования — снимки реальных "
                  "пациентов проверяйте на стенде внутри контура медорганизации.")
STATUS_RU = {"new": "новый", "assigned": "в работе", "accepted": "в работе", "reopened": "переоткрыт", "closed": "закрыт"}


def setup(**kw):
    """read, new_run, write_status, submit, runs_dir, list_runs, has_archives, progress_payload, datasets, region_ru,
    violation_ru, public_url, templates — функции и настройки приложения."""
    ctx.update(kw)
    tpl = kw.get("templates")
    if tpl is not None:
        tpl.env.globals["tg_link_for"] = A.tg_link_for_user
        tpl.env.globals["tg_bot_username"] = BOT_USERNAME
        tpl.env.globals["tg_enabled"] = lambda: BOT is not None


def _url(path: str) -> str:
    return ctx["public_url"] + path


_tickets: dict = {}


def fetch_ticket(n: int) -> dict | None:
    """Тикет Trac из CSV-выгрузки: summary, status, resolution, milestone. Кеш на минуту."""
    if not TRAC_INTERNAL:
        return None
    hit = _tickets.get(n)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        with urllib.request.urlopen(f"{TRAC_INTERNAL}/ticket/{n}?format=csv", timeout=5) as r:
            row = next(csv.DictReader(io.StringIO(r.read(300_000).decode("utf-8-sig", "replace"))), None)
    except Exception:  # noqa: BLE001 — нет тикета или Trac недоступен: просто не разворачиваем
        row = None
    _tickets[n] = (time.time(), row)
    return row


# ------------------------------------------------------------------ клиент Bot API

class Bot:
    def __init__(self, token: str, api: str = API, transport=None):
        self.token, self.api = token, api.rstrip("/")
        self.transport = transport or self._http
        self.username = BOT_USERNAME
        self.stopped = threading.Event()
        self.local = threading.local()      # чат и тема форума обрабатываемого сообщения
        self._last_announce = 0.0

    def _http(self, method: str, params: dict, timeout: float) -> dict:
        req = urllib.request.Request(f"{self.api}/bot{self.token}/{method}", data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def call(self, method: str, timeout: float = 20, **params):
        try:
            res = self.transport(method, params, timeout)
        except urllib.error.HTTPError as exc:
            try:
                res = json.loads(exc.read())
            except Exception:  # noqa: BLE001
                res = {"ok": False, "description": f"HTTP {exc.code}"}
        except Exception as exc:  # noqa: BLE001 — сеть до Telegram могла моргнуть, бот продолжает
            print(f"[tg] {method}: {type(exc).__name__}", flush=True)
            return None
        if not res.get("ok"):
            desc = str(res.get("description", ""))
            if "message is not modified" not in desc:
                print(f"[tg] {method}: {desc[:200]}", flush=True)
            return None
        return res.get("result")

    def fetch_file(self, file_path: str) -> bytes:
        with urllib.request.urlopen(f"{self.api}/file/bot{self.token}/{file_path}", timeout=90) as r:
            return r.read(MAX_FILE + 1)

    @staticmethod
    def markup(buttons):
        if not buttons:
            return None
        rows = []
        for row in buttons:
            rows.append([{"text": t, **({"url": v} if v.startswith("http") else {"callback_data": v})} for t, v in row])
        return {"inline_keyboard": rows}

    @staticmethod
    def _preview(preview: str | None) -> dict:
        return {"url": preview, "prefer_large_media": True} if preview else {"is_disabled": True}

    def send(self, chat_id: int, text: str, buttons=None, reply_to: int | None = None, preview: str | None = None):
        params = dict(chat_id=chat_id, text=text[:4096], parse_mode="HTML", link_preview_options=self._preview(preview))
        if buttons:
            params["reply_markup"] = self.markup(buttons)
        if reply_to:
            params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        thread = getattr(self.local, "thread", None)
        if thread and getattr(self.local, "chat", None) == chat_id:
            params["message_thread_id"] = thread
        return self.call("sendMessage", **params)

    def edit(self, chat_id: int, message_id: int, text: str, buttons=None):
        params = dict(chat_id=chat_id, message_id=message_id, text=text[:4096], parse_mode="HTML",
                      link_preview_options=self._preview(None))
        if buttons:
            params["reply_markup"] = self.markup(buttons)
        return self.call("editMessageText", **params)

    # ---------------------------------------------------------------- обработка обновлений

    def handle(self, update: dict):
        cq = update.get("callback_query") or {}
        msg = update.get("message") or cq.get("message") or {}
        chat = msg.get("chat") or {}
        self.local.chat = chat.get("id")
        self.local.thread = msg.get("message_thread_id") if msg.get("is_topic_message") else None
        try:
            if "my_chat_member" in update:
                return self.on_member(update["my_chat_member"])
            if cq:
                return self.on_callback(cq)
            if chat.get("type") in ("group", "supergroup"):
                return self.on_group(msg)
            if chat.get("type") != "private":
                return None
            cid = chat["id"]
            user = A.tg_user(cid)
            if msg.get("document"):
                return self.on_document(cid, user, msg)
            text = (msg.get("text") or "").strip()
            if not text.startswith("/"):
                return self.send(cid, "Команды — /help. Чтобы проверить исследование, пришлите файл DICOM или zip.")
            cmd, *args = text.split()
            handler = getattr(self, "cmd_" + cmd[1:].split("@")[0].lower(), None)
            if not handler:
                return self.send(cid, "Такой команды нет — список в /help.")
            return handler(cid, user, args, msg)
        except Exception as exc:  # noqa: BLE001 — одно сломанное обновление не останавливает бота
            print(f"[tg] обработка: {type(exc).__name__}: {exc}\n{traceback.format_exc(limit=6)}", flush=True)
            if chat.get("id") and not cq and (chat.get("type") == "private" or (msg.get("text") or "").startswith("/")):
                self.send(chat["id"], "Не получилось выполнить команду, попробуйте ещё раз или откройте стенд.")
            return None
        finally:
            self.local.chat = self.local.thread = None

    def _need_link(self, cid: int):
        return self.send(cid, "Проверки запускают привязанные аккаунты стенда. Войдите на стенде, откройте кабинет и нажмите "
                              "«подключить Telegram».", [[("Открыть кабинет", _url("/account"))]])

    def cmd_start(self, cid, user, args, msg):
        if args and args[0].startswith("link_"):
            try:
                user = A.consume_tg_code(args[0][5:], cid, (msg.get("from") or {}).get("username", ""))
            except A.AccountError as exc:
                return self.send(cid, esc(exc))
            return self.send(cid, f"Готово: Telegram привязан к аккаунту <b>{esc(user['login'])}</b>"
                                  f"{' (админ)' if user['is_admin'] else ''}.\n\n{HELP}")
        hello = "Привет! Я бот стенда контроля качества денситометрии DXA.\n\n" + HELP
        if not user:
            return self.send(cid, hello, [[("Привязать аккаунт", _url("/account"))], [("Открыть стенд", _url("/"))]])
        return self.send(cid, hello, [[("Открыть стенд", _url("/"))]])

    def cmd_help(self, cid, user, args, msg):
        return self.send(cid, HELP)

    def cmd_me(self, cid, user, args, msg):
        if not user:
            return self._need_link(cid)
        return self.send(cid, f"Аккаунт <b>{esc(user['login'])}</b> · {'админ' if user['is_admin'] else 'пользователь'}\n"
                              f"Проверок из Telegram сегодня: {A.tg_runs_today(user['id'])} из {DAILY_RUNS}.")

    def cmd_unlink(self, cid, user, args, msg):
        if not user:
            return self.send(cid, "Этот чат и так не привязан.")
        A.unlink_tg(chat_id=cid)
        return self.send(cid, f"Telegram отвязан от аккаунта {esc(user['login'])}.")

    def cmd_datasets(self, cid, user, args, msg):
        lines = ["<b>Наборы организатора</b>"]
        for d in ctx["datasets"].available():
            lines.append(f"• <b>{esc(d['id'])}</b> — {esc(d['title'])}: {d['n_studies']} исследований"
                         f"{', экспертная разметка' if d['has_labels'] else ''}")
        lines.append("\nЗапуск: /check test или /check train 10")
        return self.send(cid, "\n".join(lines))

    def cmd_runs(self, cid, user, args, msg):
        runs = ctx["list_runs"](6)
        if not runs:
            return self.send(cid, "Прогонов пока нет.")
        lines, buttons = ["<b>Последние прогоны</b>"], []
        for r in runs[:6]:
            s = r.get("summary") or {}
            state = {"done": "✓", "running": "…", "queued": "в очереди", "error": "ошибка", "cancelled": "отменён"}.get(r.get("state"), r.get("state"))
            lines.append(f"• {esc(r.get('created_str'))} · {esc((r.get('title') or r['id'])[:60])} · {state}"
                         + (f" · снимков {s.get('images', 0)}" if s else ""))
            if r.get("state") == "done":
                buttons.append([(f"{(r.get('title') or r['id'])[:40]}", f"run:{r['id']}")])
        return self.send(cid, "\n".join(lines), buttons[:6])

    def cmd_run(self, cid, user, args, msg):
        if not args:
            return self.send(cid, "Укажите прогон: /run &lt;id&gt; — id есть в /runs и в адресе страницы прогона.")
        return self.send_summary(cid, args[0])

    def cmd_check(self, cid, user, args, msg):
        if not user:
            return self._need_link(cid)
        ds = (args[0] if args else "").lower()
        meta = ctx["datasets"].REGISTRY.get(ds)
        if not meta:
            return self.send(cid, "Какой набор проверить? /check test или /check train 10 (или all). Список — /datasets.")
        if A.tg_runs_today(user["id"]) >= DAILY_RUNS:
            return self.send(cid, f"Лимит на сегодня: {DAILY_RUNS} проверок из Telegram. Продолжить можно на стенде.")
        arg = args[1].lower() if len(args) > 1 else ("all" if ds == "test" else "10")
        mode, n = ("all", 0) if arg == "all" or not meta.get("per_study") else ("sample", max(1, min(100, int(arg) if arg.isdigit() else 10)))
        what = "весь набор" if mode == "all" else f"случайные {n}"
        run_id = ctx["new_run"](f"Telegram · {user['login']}: {meta['title']}: {what}")
        try:
            chosen = ctx["datasets"].link_selection(ds, mode, os.path.join(ctx["runs_dir"], run_id, "input"), n=n or 10)
        except Exception as exc:  # noqa: BLE001
            ctx["write_status"](run_id, state="error", error=str(exc)[:300])
            return self.send(cid, f"Набор не подключён: {esc(exc)}")
        ctx["write_status"](run_id, dataset=ds, studies=len(chosen), has_labels=bool(meta.get("labels")), started_by=f"tg:{user['login']}")
        ctx["submit"](run_id)
        return self._watch(cid, user, run_id, "dataset")

    def on_document(self, cid, user, msg):
        if not user:
            return self._need_link(cid)
        doc = msg["document"]
        if A.tg_runs_today(user["id"]) >= DAILY_RUNS:
            return self.send(cid, f"Лимит на сегодня: {DAILY_RUNS} проверок из Telegram.")
        if (doc.get("file_size") or 0) > MAX_FILE:
            return self.send(cid, "Файл больше 20 МБ — Telegram не отдаёт боту такие файлы. Загрузите его на стенде.",
                             [[("Открыть стенд", _url("/"))]])
        info = self.call("getFile", file_id=doc["file_id"])
        if not info or not info.get("file_path"):
            return self.send(cid, "Не получилось скачать файл из Telegram, попробуйте ещё раз.")
        data = self.fetch_file(info["file_path"])
        if len(data) > MAX_FILE:
            return self.send(cid, "Файл больше 20 МБ.")
        name = re.sub(r"[\x00-\x1f\\/]", "_", os.path.basename(doc.get("file_name") or "file.dcm"))[:120] or "file.dcm"
        run_id = ctx["new_run"](f"Telegram · {user['login']}: {name}")
        with open(os.path.join(ctx["runs_dir"], run_id, "input", name), "wb") as f:
            f.write(data)
        ctx["write_status"](run_id, has_archives=ctx["has_archives"](run_id), started_by=f"tg:{user['login']}")
        ctx["submit"](run_id)
        self.send(cid, esc(UPLOAD_WARNING))
        return self._watch(cid, user, run_id, "upload")

    # ---------------------------------------------------------------- группа

    def trusted(self, uid) -> bool:
        """Может разрешить группу: владелец команды или привязанный админ стенда (id лички совпадает с id пользователя)."""
        if not uid:
            return False
        if uid in OWNERS:
            return True
        user = A.tg_user(uid)
        return bool(user and user["is_admin"])

    def admit(self, chat: dict, actor: dict | None) -> dict | None:
        """Разрешённая группа или None. Незнакомую группу от доверенного — разрешить, от прочих — спросить админов."""
        cid, title = chat["id"], (chat.get("title") or "")[:120]
        actor = actor or {}
        who = actor.get("username") or str(actor.get("id") or "")
        g = A.tg_group(cid)
        if g and g["status"] == "allowed":
            if title and title != g["title"]:
                A.tg_group_set(cid, title=title)
            return g
        if g and g["status"] == "blocked":
            self.call("leaveChat", chat_id=cid)
            return None
        if self.trusted(actor.get("id")):
            A.tg_group_save(cid, title, "allowed", who)
            self.welcome(cid)
            return A.tg_group(cid)
        if not g:
            A.tg_group_save(cid, title, "pending", who)
            text = (f"Бота добавили в группу <b>{esc(title or cid)}</b>{f' (участник {esc(who)})' if who else ''}. "
                    "Пока группа не разрешена, бот в ней молчит.")
            for chat_id in sorted(set(A.admin_tg_chats()) | OWNERS):
                self.send(chat_id, text, [[("✓ Разрешить", f"grp:ok:{cid}"), ("✕ Выйти из группы", f"grp:no:{cid}")]])
        return None

    def on_member(self, m: dict):
        chat = m.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup"):
            return None
        if (m.get("new_chat_member") or {}).get("status") in ("left", "kicked"):
            A.tg_group_delete(chat["id"])
            return None
        return self.admit(chat, m.get("from"))

    def on_group(self, msg: dict):
        chat = msg["chat"]
        cid = chat["id"]
        if msg.get("migrate_to_chat_id"):
            A.tg_group_migrate(cid, msg["migrate_to_chat_id"])
            return None
        frm = msg.get("from") or {}
        if frm.get("is_bot") or not self.admit(chat, frm):
            return None
        if msg.get("document") or msg.get("photo") or msg.get("video"):
            return None                              # файлы с исследованиями в группе не обрабатываем
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if text.startswith("/"):
            cmd, *args = text.split()
            name, _, target = cmd[1:].partition("@")
            if target and target.lower() != self.username.lower():
                return None                          # команда другому боту
            handler = GROUP_HANDLERS.get(name.lower())
            if not handler:
                return self.send(cid, "Такой команды нет — список в /help.", reply_to=msg.get("message_id")) if target else None
            return getattr(self, handler)(cid, A.tg_user(frm.get("id")), args, msg)
        entities = (msg.get("entities") or []) + (msg.get("caption_entities") or [])
        links = " ".join([text] + [e.get("url", "") for e in entities if e.get("type") == "text_link"])
        sent = self.unfurl(cid, msg, links)
        if sent:
            return sent
        replied = (msg.get("reply_to_message") or {}).get("from") or {}
        if f"@{self.username.lower()}" in text.lower() or (replied.get("is_bot") and (replied.get("username") or "").lower() == self.username.lower()):
            return self.send(cid, GROUP_HELP, reply_to=msg.get("message_id"))
        return None

    def links_text(self) -> str:
        return (f"Стенд: {_url('/')}\nТрекер: {TRAC_PUBLIC}\nДокументы ТЗ: {_url('/tz/')}\n"
                f"Mind map ТЗ: {_url('/tz/mindmap.html')}\nВерсия стенда {__version__}")

    def links_buttons(self):
        return [[("Стенд", _url("/")), ("Трекер", TRAC_PUBLIC)],
                [("Документы ТЗ", _url("/tz/")), ("Mind map ТЗ", _url("/tz/mindmap.html"))],
                [("Привязать аккаунт стенда", _url("/account"))]]

    def welcome(self, cid: int):
        sent = self.send(cid, "<b>Привет, команда!</b> Я бот стенда DXA QC «Квантового Скачка».\n\n"
                              f"{self.links_text()}\n\n{GROUP_HELP}", self.links_buttons(), preview=_url("/"))
        if sent and sent.get("message_id"):
            self.call("pinChatMessage", chat_id=cid, message_id=sent["message_id"], disable_notification=True)
        A.tg_state("announced_version", __version__)
        if not A.tg_state("announce_since"):
            A.tg_state("announce_since", str(time.time()))
        return sent

    def cmd_site(self, cid, user, args, msg):
        return self.send(cid, self.links_text(), self.links_buttons(), preview=_url("/"))

    def cmd_group_help(self, cid, user, args, msg):
        return self.send(cid, GROUP_HELP)

    @staticmethod
    def last_train(runs):
        return next((r for r in runs if r.get("dataset") == "train" and r.get("state") == "done"
                     and (r.get("summary") or {}).get("studies", 0) >= 90), None)

    def cmd_status(self, cid, user, args, msg):
        runs = ctx["list_runs"](300)
        running = sum(r.get("state") == "running" for r in runs)
        queued = sum(r.get("state") == "queued" for r in runs)
        lines = [f"<b>Стенд DXA QC</b> · версия {__version__}", f"Обрабатывается прогонов: {running}, в очереди: {queued}"]
        buttons = [[("Открыть стенд", _url("/"))]]
        train = self.last_train(runs)
        if train:
            s = train.get("summary") or {}
            man = ctx["read"](train["id"], os.path.join("out", "manifest.json")) or {}
            ev = (man.get("evaluation") or {}).get("spine_overall") or {}
            lines.append(f"Весь обучающий набор, {esc(train.get('created_str'))}: снимков {s.get('images', 0)}, "
                         f"✓ {s.get('good', 0)} · ✕ {s.get('bad', 0)}"
                         + (f", F1 по позвоночнику {num(ev.get('f1'))} на {ev['n']} исследованиях" if ev.get("n") else ""))
            buttons[0].append(("Прогон всего набора", _url(f"/runs/{train['id']}")))
        return self.send(cid, "\n".join(lines), buttons)

    def run_line(self, run_id: str, key: str | None = None) -> str | None:
        st = ctx["read"](run_id, "status.json")
        if not st:
            return None
        man = ctx["read"](run_id, os.path.join("out", "manifest.json"))
        link = _url(f"/runs/{run_id}")
        if key:
            row = next((r for r in (man or {}).get("rows", []) if r.get("key") == key), None)
            if not row:
                return None
            verdict = {0: "✓ качественное", 1: "✕ нарушение"}.get(row.get("quality_class"), "— не оценено")
            viol = "; ".join(ctx["violation_ru"].get(v, v) for v in row.get("violation_list") or [] if not v.startswith("hip_not"))
            return (f'<a href="{link}/images/{key}">{esc(os.path.basename(row.get("path_to_study") or key))}</a> · '
                    f"{esc(ctx['region_ru'].get(row.get('anatomical_region'), ''))} · {verdict}" + (f": {esc(viol)}" if viol else ""))
        title = f'<a href="{link}">{esc(st.get("title") or run_id)}</a>'
        if not man:
            state = {"running": "обрабатывается", "queued": "в очереди", "error": "ошибка", "cancelled": "отменён"}.get(st.get("state"), st.get("state"))
            return f"{title} · {esc(state)}"
        s = man["summary"]
        ev = (man.get("evaluation") or {}).get("spine_overall") or {}
        return (f"{title} · снимков {s.get('images', 0)}: ✓ {s.get('good', 0)} · ✕ {s.get('bad', 0)} · — {s.get('not_evaluated', 0)}"
                + (f" · F1 {num(ev.get('f1'))}" if ev.get("n") else ""))

    @staticmethod
    def ticket_line(n: int, t: dict) -> str:
        status = STATUS_RU.get(t.get("status"), t.get("status") or "")
        if t.get("status") == "closed" and t.get("resolution") not in (None, "", "fixed"):
            status += f" ({t['resolution']})"
        return (f'<a href="{TRAC_PUBLIC}ticket/{n}">#{n}</a> {esc(t.get("summary"))} · {esc(status)}'
                + (f" · {esc(t['milestone'])}" if t.get("milestone") else ""))

    def unfurl(self, cid: int, msg: dict, text: str):
        """Ссылки на прогоны и снимки стенда и номера тикетов — короткий ответ, не больше трёх объектов."""
        host = re.escape(re.sub(r"^https?://", "", ctx["public_url"]))
        lines, seen = [], set()
        for m in re.finditer(host + r"/runs/([A-Za-z0-9-]{6,64})(?:/images/([0-9a-f]{6,40}))?", text):
            if m.group(0) in seen or len(lines) >= MAX_UNFURL:
                continue
            seen.add(m.group(0))
            line = self.run_line(m.group(1), m.group(2))
            if line:
                lines.append(line)
        if TRAC_INTERNAL:
            for n in dict.fromkeys(TICKET_RE.findall(text)):
                if len(lines) >= MAX_UNFURL:
                    break
                t = fetch_ticket(int(n))
                if t:
                    lines.append(self.ticket_line(int(n), t))
        return self.send(cid, "\n".join(lines), reply_to=msg.get("message_id")) if lines else None

    def announce(self):
        """Команде в разрешённые группы: обновление стенда и итоги прогонов всего обучающего набора, каждое один раз."""
        chats = [g["chat_id"] for g in A.tg_groups()]
        if not chats:
            return
        if A.tg_state("announced_version") != __version__:
            A.tg_state("announced_version", __version__)
            for c in chats:
                self.send(c, f"Стенд обновлён до версии <b>{__version__}</b>.", [[("Открыть стенд", _url("/"))]])
        since = A.tg_state("announce_since") or A.tg_state("announce_since", str(time.time()))
        for r in ctx["list_runs"](20):
            if self.last_train([r]) is None or (r.get("finished") or r.get("created") or 0) <= float(since):
                continue
            if A.tg_state(f"announced_run:{r['id']}"):
                continue
            A.tg_state(f"announced_run:{r['id']}", "1")
            text, buttons = self.summary(r["id"], group=True)
            for c in chats:
                self.send(c, f"<b>Завершён прогон всего обучающего набора</b>\n{text}", buttons)

    # ---------------------------------------------------------------- живой прогресс и итоги

    def _watch(self, cid, user, run_id, kind):
        sent = self.send(cid, self.progress_text(run_id), [[("Открыть прогон", _url(f"/runs/{run_id}"))]])
        A.tg_add_run(run_id, user["id"], cid, (sent or {}).get("message_id"), kind)
        return sent

    @staticmethod
    def _percent(p: dict) -> int:
        if p.get("state") == "done":
            return 100
        total = got = 0.0
        stages, step = p.get("stages") or {}, p.get("step") or {}
        for s in p.get("stage_list") or []:
            if s["key"] == "done":
                continue
            total += s["weight"]
            st = stages.get(s["key"]) or {}
            if st.get("end"):
                got += s["weight"]
            elif s["key"] == p.get("stage") and st.get("start") and p.get("state") == "running":
                got += s["weight"] * (min(1.0, step.get("done", 0) / step["total"]) if step.get("total") else 0.3)
        return min(99, int(got / total * 100)) if total else 0

    def progress_text(self, run_id: str) -> str:
        p = ctx["progress_payload"](run_id)
        pct = self._percent(p)
        bar = "▰" * (pct // 10) + "▱" * (10 - pct // 10)
        stage = next((s["label"] for s in p.get("stage_list") or [] if s["key"] == p.get("stage")), "в очереди")
        step, t = p.get("step") or {}, p.get("tally") or {}
        lines = [f"<b>{esc(p.get('title') or run_id)}</b>", f"{bar} {pct}%"]
        if p.get("state") == "queued":
            lines.append(f"в очереди{', впереди прогонов: ' + str(p['queue_position']) if p.get('queue_position') else ''}")
        else:
            counter = f" · {step.get('done', 0)} из {step['total']}" if step.get("total") else ""
            lines.append(esc(stage) + counter)
        if t:
            lines.append(f"✓ {t.get('good', 0)} качественных · ✕ {t.get('bad', 0)} с нарушением · — {t.get('na', 0) + t.get('failed', 0)} не оценено")
        return "\n".join(lines)

    def summary(self, run_id: str, group: bool = False):
        st = ctx["read"](run_id, "status.json") if re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id or "") else None
        if not st:
            return None, None
        man = ctx["read"](run_id, os.path.join("out", "manifest.json"))
        title = esc(st.get("title") or run_id)
        if st.get("state") in ("error", "cancelled"):
            return f"<b>{title}</b>\n{'Ошибка: ' + esc(st.get('error')) if st.get('state') == 'error' else 'Прогон отменён.'}", \
                [[("Открыть прогон", _url(f"/runs/{run_id}"))]]
        if not man:
            return self.progress_text(run_id), [[("Открыть прогон", _url(f"/runs/{run_id}"))]]
        s = man["summary"]
        lines = [f"<b>Готово · {title}</b>",
                 f"Снимков {s.get('images', 0)} в {s.get('studies', 0)} исследованиях, {num(s.get('mean_time'))} с на снимок",
                 f"✓ качественных {s.get('good', 0)} · ✕ с нарушением {s.get('bad', 0)} · — не оценено {s.get('not_evaluated', 0)}"]
        if s.get("failures"):
            lines.append(f"отказов {s['failures']}: файлы не подошли — причины в «Нарушения и отказы»")
        top = Counter(v for r in man["rows"] for v in r.get("violation_list") or [] if not v.startswith("hip_not")).most_common(3)
        if top:
            lines.append("Чаще всего: " + "; ".join(f"{esc(ctx['violation_ru'].get(v, v))} — {n}" for v, n in top))
        ev = (man.get("evaluation") or {}).get("spine_overall")
        if ev and ev.get("n"):
            lines.append(f"Сравнение с экспертами по позвоночнику: F1 {num(ev.get('f1'))} на {ev['n']} исследованиях")
        base = f"/runs/{run_id}/files"
        buttons = [[("Открыть прогон", _url(f"/runs/{run_id}")), ("Нарушения и отказы", f"bad:{run_id}")],
                   [("Таблица CSV", _url(f"{base}/results.csv"))]]
        if s.get("images") and not group and not analysis.organizer_run(run_id, st):
            buttons[1].append(("Атласы снимков", f"atlas:{run_id}"))
        return "\n".join(lines), buttons

    def send_summary(self, cid, run_id):
        text, buttons = self.summary(run_id, group=is_group(cid))
        if not text:
            return self.send(cid, "Прогон не найден — список в /runs.")
        return self.send(cid, text, buttons)

    def tick(self):
        """Один проход наблюдения: обновить сообщения прогресса, у завершённых — итог."""
        for w in A.tg_active_runs():
            run_id = w["run_id"]
            st = ctx["read"](run_id, "status.json")
            if not st:
                A.tg_finish_run(run_id)
                continue
            final = st.get("state") in ("done", "error", "cancelled")
            if final:
                text, buttons = self.summary(run_id, group=is_group(w["chat_id"]))
            else:
                text, buttons = self.progress_text(run_id), [[("Открыть прогон", _url(f"/runs/{run_id}"))]]
            if w.get("message_id"):
                self.edit(w["chat_id"], w["message_id"], text, buttons)
            elif final:
                self.send(w["chat_id"], text, buttons)
            if final:
                A.tg_finish_run(run_id)

    # ---------------------------------------------------------------- кнопки

    def on_callback(self, cq: dict):
        cid = ((cq.get("message") or {}).get("chat") or {}).get("id") or (cq.get("from") or {}).get("id")
        data = str(cq.get("data") or "")
        note = ""
        kind, _, rest = data.partition(":")
        if kind == "run":
            self.send_summary(cid, rest)
        elif kind == "bad":
            self.send_violations(cid, rest)
        elif kind == "atlas":
            note = self.send_atlases(cid, rest)
        elif kind == "req":
            note = self.decide_request(cq, cid, rest)
        elif kind == "grp":
            note = self.decide_group(cq, cid, rest)
        self.call("answerCallbackQuery", callback_query_id=cq.get("id"), text=note[:190] if note else "")

    def send_violations(self, cid, run_id):
        man = ctx["read"](run_id, os.path.join("out", "manifest.json")) if re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id or "") else None
        if not man:
            return self.send(cid, "Итогов этого прогона пока нет.")
        bad = [r for r in man["rows"] if r.get("quality_class") == 1]
        failed = [r for r in man["rows"] if r.get("processing_status") != "Success"]
        if not bad and not failed:
            return self.send(cid, "Нарушений и отказов нет.")
        lines = [f"<b>Нарушения: {len(bad)}</b>"]
        for r in bad[:10]:
            name = esc(os.path.basename(r.get("path_to_study") or ""))
            link = f'<a href="{_url(f"/runs/{run_id}/images/{r["key"]}")}">{name}</a>' if r.get("key") else name
            viol = "; ".join(esc(ctx["violation_ru"].get(v, v)) for v in r.get("violation_list") or [])
            lines.append(f"• {link} — {esc(ctx['region_ru'].get(r.get('anatomical_region'), ''))}: {viol}")
        if len(bad) > 10:
            lines.append(f"…и ещё {len(bad) - 10} — на странице прогона")
        if failed:
            lines.append(f"\n<b>Отказы: {len(failed)}</b>")
            for r in failed[:5]:
                lines.append(f"• {esc(os.path.basename(r.get('path_to_study') or ''))} — {esc((r.get('explanations') or [''])[0])[:160]}")
        return self.send(cid, "\n".join(lines), [[("Открыть прогон", _url(f"/runs/{run_id}"))]])

    def send_atlases(self, cid, run_id) -> str:
        if is_group(cid):
            return "атласы снимков — только в личке с ботом"
        st = ctx["read"](run_id, "status.json") if re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id or "") else None
        man = ctx["read"](run_id, os.path.join("out", "manifest.json")) if st else None
        if not man:
            return "итогов этого прогона пока нет"
        if analysis.organizer_run(run_id, st):
            self.send(cid, "Атласы снимков организатора в Telegram не пересылаются — откройте прогон на стенде.",
                      [[("Открыть прогон", _url(f"/runs/{run_id}"))]])
            return "снимки организатора — только на стенде"
        rows = sorted((r for r in man["rows"] if r.get("overlay_png") and r.get("key")),
                      key=lambda r: {1: 0, None: 1, 0: 2}.get(r.get("quality_class"), 1))
        for r in rows[:5]:
            verdict = {0: "✓ качественное", 1: "✕ нарушение"}.get(r.get("quality_class"), "— не оценено")
            viol = "; ".join(ctx["violation_ru"].get(v, v) for v in r.get("violation_list") or [] if not v.startswith("hip_not"))
            caption = f"{os.path.basename(r.get('path_to_study') or '')} · {ctx['region_ru'].get(r.get('anatomical_region'), '')} · {verdict}"
            if viol:
                caption += f"\n{viol}"
            self.call("sendPhoto", chat_id=cid, photo=_url(f"/runs/{run_id}/files/{r['overlay_png']}"), caption=caption[:1000],
                      reply_markup=self.markup([[("Карточка снимка", _url(f"/runs/{run_id}/images/{r['key']}"))]]))
        return f"атласов: {min(5, len(rows))}"

    def decide_request(self, cq, cid, rest) -> str:
        admin = A.tg_user(cid)
        if not admin or not admin["is_admin"]:
            return "решение принимает админ"
        decision, _, rid = rest.partition(":")
        try:
            req = A.decide_request(int(rid), admin, decision == "ok")
        except (A.AccountError, ValueError) as exc:
            return str(exc)
        if req["status"] == "approved":
            analysis._execute(req, admin)
            req = A.get_request(req["id"])
        msg = cq.get("message") or {}
        verdict = "✓ одобрен" if decision == "ok" else "✕ отклонён"
        extra = ""
        if req.get("result_run"):
            extra = f'\n<a href="{_url("/runs/" + req["result_run"])}">принудительный прогон</a>'
        elif req.get("error"):
            extra = f"\nошибка: {esc(req['error'])}"
        if msg.get("message_id"):
            self.edit(cid, msg["message_id"], f"{request_text(req)}\n\n<b>{verdict}</b> · {esc(admin['login'])}{extra}")
        return verdict

    def decide_group(self, cq, cid, rest) -> str:
        if not self.trusted((cq.get("from") or {}).get("id")):
            return "решение принимает админ"
        decision, _, gid = rest.partition(":")
        try:
            gid = int(gid)
        except ValueError:
            return "неизвестная группа"
        g = A.tg_group(gid)
        if not g:
            return "бота в этой группе уже нет"
        if decision == "ok":
            if g["status"] != "allowed":
                A.tg_group_set(gid, status="allowed")
                self.welcome(gid)
            verdict = "✓ группа разрешена"
        else:
            A.tg_group_set(gid, status="blocked")
            self.call("leaveChat", chat_id=gid)
            verdict = "✕ бот вышел из группы"
        msg = cq.get("message") or {}
        if msg.get("message_id"):
            self.edit(cid, msg["message_id"], f"Группа <b>{esc(g['title'] or gid)}</b>: {verdict}")
        return verdict

    # ---------------------------------------------------------------- фоновые потоки

    def setup_profile(self):
        me = self.call("getMe")
        if isinstance(me, dict) and me.get("username"):
            self.username = me["username"]
            ctx.get("templates") and ctx["templates"].env.globals.update(tg_bot_username=self.username)
        self.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS])
        self.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in GROUP_COMMANDS],
                  scope={"type": "all_group_chats"})
        self.call("setMyShortDescription", short_description="Контроль качества денситометрии DXA: проверки и итоги стенда ЛЦТ 2026")
        self.call("setMyDescription", description=(
            "Бот стенда DXA QC команды «Квантовый Скачок» (ЛЦТ 2026, задача 04). Проверяет наборы организатора и ваши DICOM, "
            "присылает живой прогресс, вердикты и нарушения со ссылками на карточки снимков. Запуск проверок — после привязки "
            "аккаунта стенда. Присылайте только обезличенные данные."))

    def poll_loop(self):
        offset = None
        while not self.stopped.is_set():
            try:
                if offset is None:                  # профиль и сохранённое смещение — при старте и после сбоя базы
                    self.setup_profile()
                    offset = int(A.tg_state("offset") or 0)
                    print(f"[tg] бот @{self.username} слушает обновления", flush=True)
                updates = self.call("getUpdates", timeout=40, offset=offset,
                                    allowed_updates=["message", "callback_query", "my_chat_member"])
                if updates is None:
                    self.stopped.wait(5)
                    continue
                for upd in updates:
                    offset = max(offset, upd["update_id"] + 1)
                    A.tg_state("offset", str(offset))
                    self.handle(upd)
            except Exception as exc:  # noqa: BLE001 — поток опроса не должен умирать
                print(f"[tg] опрос: {type(exc).__name__}: {exc}", flush=True)
                self.stopped.wait(5)

    def watch_loop(self):
        while not self.stopped.is_set():
            try:
                self.tick()
                if time.time() - self._last_announce > ANNOUNCE_EVERY:
                    self._last_announce = time.time()
                    self.announce()
            except Exception as exc:  # noqa: BLE001
                print(f"[tg] прогресс: {type(exc).__name__}: {exc}", flush=True)
            self.stopped.wait(WATCH_EVERY)


def request_text(req: dict) -> str:
    kind = A.REQUEST_KINDS.get(req["kind"], req["kind"])
    warn = "\n⚠️ изображение уйдёт во внешний сервис Claude" if req["kind"] == "claude" else ""
    return (f"<b>Запрос на анализ</b>: {esc(kind)}\nФайл: {esc(req['label'])}\nОт: {esc(req['login'])} · прогон "
            f'<a href="{_url("/runs/" + req["run_id"])}">{esc(req["run_id"])}</a>\n{esc((req.get("reason") or "")[:300])}{warn}')


def notify_request(req: dict):
    """Новый запрос на анализ — привязанным админам в личку с кнопками решения."""
    if BOT is None:
        return
    for chat in A.admin_tg_chats():
        BOT.send(chat, request_text(req), [[("✓ Одобрить", f"req:ok:{req['id']}"), ("✕ Отклонить", f"req:no:{req['id']}")],
                                           [("Открыть админку", _url("/admin#requests"))]])


def start():
    global BOT
    token = ""
    if TOKEN_FILE:
        try:
            with open(TOKEN_FILE) as f:
                token = f.read().strip()
        except OSError:
            token = ""
    if not token:
        return None
    BOT = Bot(token)
    threading.Thread(target=BOT.poll_loop, name="tg-poll", daemon=True).start()
    threading.Thread(target=BOT.watch_loop, name="tg-watch", daemon=True).start()
    return BOT


def stop():
    if BOT is not None:
        BOT.stopped.set()


# ------------------------------------------------------------------ кабинет: подключение Telegram

@router.post("/account/telegram")
def account_link(request: Request, csrf: str = Form("")):
    user = request.state.user
    if not user:
        return RedirectResponse("/login?next=/account", status_code=303)
    ask._check_csrf(request, csrf)
    if BOT is None:
        raise HTTPException(503, "Telegram-бот на этом стенде не подключён")
    code = A.create_tg_code(user)
    return RedirectResponse(f"https://t.me/{BOT.username}?start=link_{code}", status_code=303)


@router.post("/account/telegram/unlink")
def account_unlink(request: Request, csrf: str = Form("")):
    user = request.state.user
    if not user:
        return RedirectResponse("/login?next=/account", status_code=303)
    ask._check_csrf(request, csrf)
    A.unlink_tg(user_id=user["id"])
    return RedirectResponse("/account", status_code=303)
