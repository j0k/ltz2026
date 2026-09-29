# -*- coding: utf-8 -*-
"""Учётные записи стенда и очередь вопросов к Claude: SQLite в каталоге данных.

Пароли — scrypt с солью, сессия — случайный токен в cookie (в базе только его SHA-256) и CSRF-токен для форм.
Роли: user и admin. Спрашивать Claude можно только с флагом can_ask, его выдаёт админ. Вопрос выполняется
только на чтение; исполнение с полными правами — после одобрения админом (статус awaiting_approval).

    python -m dxaqc.web.accounts create-admin LOGIN      создать или повысить админа, пароль печатается
    python -m dxaqc.web.accounts set-password LOGIN      новый случайный пароль
    python -m dxaqc.web.accounts invite [--role admin|ask] [--hours 48] [--note ТЕКСТ]   одноразовая инвайт-ссылка

Инвайт-ссылка одноразовая и со сроком действия; в базе хранится только SHA-256 токена. Роль admin делает админом,
роль ask выдаёт доступ к вопросам Claude.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time

DATA = os.environ.get("DXAQC_DATA", "/data")
DB_PATH = os.path.join(DATA, "app.db")
SESSION_TTL = 14 * 24 * 3600
DEFAULT_LIMIT = 20
MAX_LIMIT = 100000
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 10
MAX_QUESTION = 4000
FAIL_WINDOW, FAIL_MAX = 15 * 60, 5
MSK = 3 * 3600  # у Москвы нет летнего времени

# реентрантная: запись (_x, claim_next) держит блокировку и открывает соединение, а первое соединение
# создаёт схему под той же блокировкой; с обычным Lock исполнитель, пришедший к базе первым, зависал навсегда
_lock = threading.RLock()
_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, login TEXT NOT NULL UNIQUE COLLATE NOCASE, pw TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user', blocked INTEGER NOT NULL DEFAULT 0, can_ask INTEGER NOT NULL DEFAULT 0,
  daily_limit INTEGER NOT NULL DEFAULT 20, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures (key TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, text TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'read',
  status TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL, started REAL, finished REAL, approved_by INTEGER, parent_id INTEGER);
CREATE INDEX IF NOT EXISTS q_status ON questions(status, id);
CREATE INDEX IF NOT EXISTS q_user ON questions(user_id, created);
CREATE TABLE IF NOT EXISTS analysis_requests (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, run_id TEXT NOT NULL, target TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '', user_id INTEGER NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
  decided_by INTEGER, decided REAL, result_run TEXT, question_id INTEGER, error TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ar_run ON analysis_requests(run_id);
CREATE TABLE IF NOT EXISTS tg_links (
  user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL UNIQUE, username TEXT NOT NULL DEFAULT '', linked REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tg_codes (code_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tg_runs (
  run_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, message_id INTEGER, kind TEXT NOT NULL,
  created REAL NOT NULL, done INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tg_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tg_groups (
  chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, added_by TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS api_tokens (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, prefix TEXT NOT NULL, scope TEXT NOT NULL,
  daily_limit INTEGER NOT NULL DEFAULT 500, created_by TEXT NOT NULL, created REAL NOT NULL, expires REAL, revoked REAL, last_used REAL);
CREATE TABLE IF NOT EXISTS api_usage (
  id INTEGER PRIMARY KEY, token_id INTEGER, ts REAL NOT NULL, method TEXT NOT NULL, tool TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL, duration_ms REAL NOT NULL DEFAULT 0, bytes_in INTEGER NOT NULL DEFAULT 0, bytes_out INTEGER NOT NULL DEFAULT 0,
  run_id TEXT NOT NULL DEFAULT '', client TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '', session TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS au_token_ts ON api_usage(token_id, ts);
CREATE INDEX IF NOT EXISTS au_ts ON api_usage(ts);
CREATE TABLE IF NOT EXISTS api_sessions (
  id TEXT PRIMARY KEY, token_id INTEGER, client TEXT NOT NULL DEFAULT '', protocol TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, user_id INTEGER, login TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', path TEXT NOT NULL DEFAULT '',
  run_id TEXT NOT NULL DEFAULT '', status INTEGER, device TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ev_ts ON events(ts);
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, role TEXT NOT NULL DEFAULT 'admin', note TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, used_by INTEGER, used_at REAL,
  revoked INTEGER NOT NULL DEFAULT 0);
"""


class AccountError(ValueError):
    """Ошибка, которую можно показать пользователю."""


def _conn() -> sqlite3.Connection:
    global _ready
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    if not _ready:
        with _lock:
            # режим WAL хранится в самом файле базы: включаем один раз под блокировкой, иначе смена режима
            # во время создания схемы другим потоком сразу даёт «database is locked» без ожидания
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            try:  # вложение вопроса (снимок для Claude) появилось позже таблицы
                c.execute("ALTER TABLE questions ADD COLUMN attachment TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:  # id того, кто добавил бота в группу, появился позже таблицы групп
                c.execute("ALTER TABLE tg_groups ADD COLUMN added_by_id INTEGER")
            except sqlite3.OperationalError:
                pass
            # вопросы, прерванные перезапуском, возвращаем в очередь
            c.execute("UPDATE questions SET status='queued', started=NULL WHERE status='running'")
            _ready = True
    return c


def _q(sql: str, args=(), one=False):
    c = _conn()
    try:
        cur = c.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        return (rows[0] if rows else None) if one else rows
    finally:
        c.close()


def _x(sql: str, args=()) -> int:
    with _lock:
        c = _conn()
        try:
            return c.execute(sql, args).lastrowid
        finally:
            c.close()


# ------------------------------------------------------------------ пароли и пользователи

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = 2 ** 14, 8, 1
    h = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


def _public(u: dict | None) -> dict | None:
    if not u:
        return None
    u = dict(u)
    u.pop("pw", None)
    u["is_admin"] = u["role"] == "admin"
    return u


def create_user(login: str, password: str, *, role: str = "user", can_ask: bool = False, daily_limit: int = DEFAULT_LIMIT) -> dict:
    login = (login or "").strip()
    if not LOGIN_RE.match(login):
        raise AccountError("логин: 3–32 символа, латинские буквы, цифры, точка, дефис или подчёркивание")
    if len(password or "") < MIN_PASSWORD:
        raise AccountError(f"пароль не короче {MIN_PASSWORD} символов")
    if get_user_by_login(login):
        raise AccountError("такой логин уже занят")
    uid = _x("INSERT INTO users (login, pw, role, can_ask, daily_limit, created) VALUES (?,?,?,?,?,?)",
             (login, hash_password(password), role, int(can_ask), int(daily_limit), time.time()))
    return get_user(uid)


def get_user(uid: int) -> dict | None:
    return _public(_q("SELECT * FROM users WHERE id=?", (uid,), one=True))


def get_user_by_login(login: str) -> dict | None:
    return _public(_q("SELECT * FROM users WHERE login=?", ((login or "").strip(),), one=True))


def list_users() -> list[dict]:
    rows = _q("SELECT * FROM users ORDER BY role='admin' DESC, created")
    today = _day_start()
    counts = {r["user_id"]: r["n"] for r in _q("SELECT user_id, COUNT(*) n FROM questions WHERE created>=? GROUP BY user_id", (today,))}
    out = []
    for r in rows:
        u = _public(r)
        u["asked_today"] = counts.get(u["id"], 0)
        out.append(u)
    return out


def update_user(uid: int, *, role: str | None = None, blocked: bool | None = None, can_ask: bool | None = None,
                daily_limit: int | None = None) -> dict:
    sets, args = [], []
    if role is not None:
        if role not in ("user", "admin"):
            raise AccountError("неизвестная роль")
        sets.append("role=?"); args.append(role)
    if blocked is not None:
        sets.append("blocked=?"); args.append(int(blocked))
    if can_ask is not None:
        sets.append("can_ask=?"); args.append(int(can_ask))
    if daily_limit is not None:
        if not 0 <= int(daily_limit) <= MAX_LIMIT:
            raise AccountError(f"лимит от 0 до {MAX_LIMIT}")
        sets.append("daily_limit=?"); args.append(int(daily_limit))
    if sets:
        _x(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*args, uid))
    if blocked:
        _x("DELETE FROM sessions WHERE user_id=?", (uid,))
    return get_user(uid)


def set_password(uid: int, password: str):
    if len(password or "") < MIN_PASSWORD:
        raise AccountError(f"пароль не короче {MIN_PASSWORD} символов")
    _x("UPDATE users SET pw=? WHERE id=?", (hash_password(password), uid))


# ------------------------------------------------------------------ вход и сессии

def authenticate(login: str, password: str, ip: str = "") -> dict:
    key = f"{(login or '').lower()}|{ip}"
    now = time.time()
    _x("DELETE FROM login_failures WHERE ts<?", (now - FAIL_WINDOW,))
    fails = _q("SELECT COUNT(*) n FROM login_failures WHERE key=?", (key,), one=True)["n"]
    if fails >= FAIL_MAX:
        raise AccountError("слишком много попыток входа, попробуйте через 15 минут")
    row = _q("SELECT * FROM users WHERE login=?", ((login or "").strip(),), one=True)
    ok = check_password(password or "", row["pw"]) if row else check_password(password or "", hash_password("x" * MIN_PASSWORD))
    if not row or not ok:
        _x("INSERT INTO login_failures (key, ts) VALUES (?,?)", (key, now))
        raise AccountError("неверный логин или пароль")
    if row["blocked"]:
        raise AccountError("учётная запись заблокирована")
    _x("DELETE FROM login_failures WHERE key=?", (key,))
    return _public(row)


def create_session(uid: int) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = time.time()
    _x("DELETE FROM sessions WHERE expires<?", (now,))
    _x("INSERT INTO sessions (token_hash, user_id, csrf, expires) VALUES (?,?,?,?)",
       (hashlib.sha256(token.encode()).hexdigest(), uid, csrf, now + SESSION_TTL))
    return token, csrf


def session_user(token: str | None) -> tuple[dict | None, str]:
    """→ (пользователь, csrf) по токену из cookie или (None, '')."""
    if not token:
        return None, ""
    s = _q("SELECT * FROM sessions WHERE token_hash=? AND expires>?", (hashlib.sha256(token.encode()).hexdigest(), time.time()), one=True)
    if not s:
        return None, ""
    u = get_user(s["user_id"])
    if not u or u["blocked"]:
        return None, ""
    return u, s["csrf"]


def drop_session(token: str | None):
    if token:
        _x("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


# ------------------------------------------------------------------ вопросы

def _day_start(now: float | None = None) -> float:
    now = time.time() if now is None else now
    return (now + MSK) // 86400 * 86400 - MSK


def asked_today(uid: int) -> int:
    return _q("SELECT COUNT(*) n FROM questions WHERE user_id=? AND created>=?", (uid, _day_start()), one=True)["n"]


def add_question(user: dict, text: str, *, want_exec: bool = False, parent_id: int | None = None) -> dict:
    text = (text or "").strip()
    if not user or user.get("blocked"):
        raise AccountError("нужен вход")
    if not user.get("can_ask"):
        raise AccountError("доступ к вопросам ещё не выдан, его выдаёт админ")
    if not text:
        raise AccountError("вопрос пустой")
    if len(text) > MAX_QUESTION:
        raise AccountError(f"вопрос длиннее {MAX_QUESTION} символов")
    if asked_today(user["id"]) >= user["daily_limit"]:
        raise AccountError(f"лимит на сегодня исчерпан: {user['daily_limit']} вопросов в сутки")
    status = "awaiting_approval" if want_exec else "queued"
    qid = _x("INSERT INTO questions (user_id, text, mode, status, created, parent_id) VALUES (?,?,?,?,?,?)",
             (user["id"], text, "full" if want_exec else "read", status, time.time(), parent_id))
    return get_question(qid)


def get_question(qid: int) -> dict | None:
    return _q("SELECT q.*, u.login FROM questions q JOIN users u ON u.id=q.user_id WHERE q.id=?", (qid,), one=True)


def user_questions(uid: int, limit: int = 50) -> list[dict]:
    return _q("SELECT q.*, u.login FROM questions q JOIN users u ON u.id=q.user_id WHERE q.user_id=? ORDER BY q.id DESC LIMIT ?", (uid, limit))


def journal(limit: int = 100) -> list[dict]:
    return _q("SELECT q.*, u.login, a.login AS approver FROM questions q JOIN users u ON u.id=q.user_id "
              "LEFT JOIN users a ON a.id=q.approved_by ORDER BY q.id DESC LIMIT ?", (limit,))


def awaiting_approval() -> list[dict]:
    return _q("SELECT q.*, u.login FROM questions q JOIN users u ON u.id=q.user_id WHERE q.status='awaiting_approval' ORDER BY q.id")


def decide(qid: int, admin: dict, approve: bool) -> dict:
    if not admin or not admin.get("is_admin"):
        raise AccountError("решение принимает админ")
    q = get_question(qid)
    if not q or q["status"] != "awaiting_approval":
        raise AccountError("этот вопрос не ждёт одобрения")
    _x("UPDATE questions SET status=?, approved_by=? WHERE id=?", ("queued" if approve else "rejected", admin["id"], qid))
    return get_question(qid)


def claim_next() -> dict | None:
    """Взять следующий вопрос из очереди и отметить его выполняемым."""
    with _lock:
        c = _conn()
        try:
            row = c.execute("SELECT id FROM questions WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
            if not row:
                return None
            c.execute("UPDATE questions SET status='running', started=? WHERE id=? AND status='queued'", (time.time(), row["id"]))
        finally:
            c.close()
    return get_question(row["id"])


def finish(qid: int, *, answer: str = "", error: str = ""):
    _x("UPDATE questions SET status=?, answer=?, error=?, finished=? WHERE id=?",
       ("error" if error else "done", answer, error[:2000], time.time(), qid))


# ------------------------------------------------------------------ запросы на анализ с одобрением админа

REQUEST_KINDS = {"force": "принудительный анализ", "claude": "анализ снимка в Claude"}
REQUEST_STATUS = {"pending": "ждёт одобрения админа", "approved": "одобрен", "rejected": "отклонён админом", "error": "ошибка"}
_REQ_SELECT = ("SELECT r.*, u.login AS login, a.login AS approver FROM analysis_requests r JOIN users u ON u.id=r.user_id "
               "LEFT JOIN users a ON a.id=r.decided_by")


def add_request(user: dict, kind: str, run_id: str, target: str, label: str, reason: str = "") -> dict:
    """Запрос на принудительный анализ или анализ снимка в Claude. Повторный запрос того же файла возвращает прежний."""
    if not user or user.get("blocked"):
        raise AccountError("нужен вход")
    if kind not in REQUEST_KINDS:
        raise AccountError("неизвестный вид запроса")
    same = _q(_REQ_SELECT + " WHERE r.kind=? AND r.run_id=? AND r.target=? AND r.status IN ('pending', 'approved') ORDER BY r.id DESC LIMIT 1",
              (kind, run_id, target), one=True)
    if same:
        return same
    rid = _x("INSERT INTO analysis_requests (kind, run_id, target, label, reason, user_id, status, created) VALUES (?,?,?,?,?,?,?,?)",
             (kind, run_id, target[:500], label[:200], reason[:500], user["id"], "pending", time.time()))
    return get_request(rid)


def get_request(rid: int) -> dict | None:
    return _q(_REQ_SELECT + " WHERE r.id=?", (rid,), one=True)


def pending_requests() -> list[dict]:
    return _q(_REQ_SELECT + " WHERE r.status='pending' ORDER BY r.id")


def recent_requests(limit: int = 30) -> list[dict]:
    return _q(_REQ_SELECT + " WHERE r.status!='pending' ORDER BY r.id DESC LIMIT ?", (limit,))


def run_requests(run_id: str) -> list[dict]:
    return _q(_REQ_SELECT + " WHERE r.run_id=? ORDER BY r.id", (run_id,))


def decide_request(rid: int, admin: dict, approve: bool) -> dict:
    if not admin or not admin.get("is_admin"):
        raise AccountError("решение принимает админ")
    with _lock:
        c = _conn()
        try:
            cur = c.execute("UPDATE analysis_requests SET status=?, decided_by=?, decided=? WHERE id=? AND status='pending'",
                            ("approved" if approve else "rejected", admin["id"], time.time(), rid))
            if cur.rowcount != 1:
                raise AccountError("этот запрос уже решён")
        finally:
            c.close()
    return get_request(rid)


def update_request(rid: int, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("status", "result_run", "question_id", "error")}
    if allowed:
        _x(f"UPDATE analysis_requests SET {', '.join(k + '=?' for k in allowed)} WHERE id=?", (*allowed.values(), rid))


def add_image_question(user_id: int, text: str, attachment: str, approver_id: int) -> dict:
    """Вопрос к Claude со снимком по одобренному запросу: доступ и лимит уже решил админ, режим только чтение."""
    qid = _x("INSERT INTO questions (user_id, text, mode, status, created, approved_by, attachment) VALUES (?,?,?,?,?,?,?)",
             (user_id, text[:MAX_QUESTION], "read", "queued", time.time(), approver_id, attachment))
    return get_question(qid)


# ------------------------------------------------------------------ токены MCP и журнал использования

TOKEN_SCOPES = {"read": "чтение результатов", "analyze": "чтение и запуск анализа"}
TOKEN_PREFIX = "dxq_"
OK_STATUSES = ("ok", "tool_error")   # вызов дошёл до инструмента и считается в суточный лимит


def _token_row(row: dict | None) -> dict | None:
    if not row:
        return None
    now = time.time()
    row["status"] = "revoked" if row["revoked"] else "expired" if row["expires"] and row["expires"] <= now else "active"
    return row


def create_api_token(created_by: str, name: str, scope: str = "read", days: int | None = None, daily_limit: int = 500) -> tuple[str, dict]:
    """→ (токен, запись). Токен показывается один раз, в базе SHA-256 и префикс для узнавания."""
    name = (name or "").strip()
    if not 1 <= len(name) <= 80:
        raise AccountError("укажите, кому токен: от 1 до 80 символов")
    if scope not in TOKEN_SCOPES:
        raise AccountError("неизвестные права токена")
    if not 1 <= int(daily_limit) <= 100000:
        raise AccountError("суточный лимит от 1 до 100 000 вызовов")
    if days is not None and not 1 <= int(days) <= 365:
        raise AccountError("срок действия от 1 до 365 дней")
    token, now = TOKEN_PREFIX + secrets.token_urlsafe(32), time.time()
    tid = _x("INSERT INTO api_tokens (name, token_hash, prefix, scope, daily_limit, created_by, created, expires) VALUES (?,?,?,?,?,?,?,?)",
             (name, _token_hash(token), token[:12], scope, int(daily_limit), created_by[:40], now,
              now + int(days) * 86400 if days else None))
    return token, get_api_token(tid)


def get_api_token(tid: int) -> dict | None:
    return _token_row(_q("SELECT * FROM api_tokens WHERE id=?", (tid,), one=True))


def list_api_tokens() -> list[dict]:
    return [_token_row(r) for r in _q("SELECT * FROM api_tokens ORDER BY revoked IS NOT NULL, id DESC")]


def resolve_api_token(secret: str) -> dict | None:
    if not secret or not secret.startswith(TOKEN_PREFIX) or len(secret) > 100:
        return None
    return _token_row(_q("SELECT * FROM api_tokens WHERE token_hash=?", (_token_hash(secret),), one=True))


def revoke_api_token(tid: int):
    _x("UPDATE api_tokens SET revoked=? WHERE id=? AND revoked IS NULL", (time.time(), tid))


def set_token_limit(tid: int, daily_limit: int):
    if not 1 <= int(daily_limit) <= 100000:
        raise AccountError("суточный лимит от 1 до 100 000 вызовов")
    _x("UPDATE api_tokens SET daily_limit=? WHERE id=?", (int(daily_limit), tid))


def calls_today(tid: int) -> int:
    return _q("SELECT COUNT(*) n FROM api_usage WHERE token_id=? AND method='tools/call' AND status IN (?, ?) AND ts>=?",
              (tid, *OK_STATUSES, _day_start()), one=True)["n"]


def log_usage(**f):
    _x("INSERT INTO api_usage (token_id, ts, method, tool, status, duration_ms, bytes_in, bytes_out, run_id, client, ip, session, error) "
       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
       (f.get("token_id"), f.get("ts") or time.time(), str(f.get("method", ""))[:60], str(f.get("tool") or "")[:60], f.get("status", "ok"),
        round(float(f.get("duration_ms") or 0), 2), int(f.get("bytes_in") or 0), int(f.get("bytes_out") or 0), f.get("run_id") or "",
        str(f.get("client") or "")[:80], str(f.get("ip") or "")[:60], str(f.get("session") or "")[:64], str(f.get("error") or "")[:300]))
    if f.get("token_id") and f.get("status") in OK_STATUSES:
        _x("UPDATE api_tokens SET last_used=? WHERE id=?", (time.time(), f["token_id"]))


def save_session(sid: str, token_id: int, client: str, protocol: str):
    _x("INSERT OR REPLACE INTO api_sessions (id, token_id, client, protocol, created) VALUES (?,?,?,?,?)",
       (sid, token_id, client[:80], protocol[:20], time.time()))


def get_session(sid: str) -> dict | None:
    return _q("SELECT * FROM api_sessions WHERE id=?", ((sid or "")[:64],), one=True) if sid else None


def usage_rows(token_id: int | None = None, since: float = 0) -> list[dict]:
    if token_id is None:
        return _q("SELECT * FROM api_usage WHERE ts>=? ORDER BY ts LIMIT 200000", (since,))
    return _q("SELECT * FROM api_usage WHERE token_id=? AND ts>=? ORDER BY ts LIMIT 200000", (token_id, since))


def usage_recent(token_id: int | None = None, limit: int = 50) -> list[dict]:
    where, args = ("WHERE u.token_id=?", (token_id,)) if token_id is not None else ("", ())
    return _q(f"SELECT u.*, t.name AS token_name FROM api_usage u LEFT JOIN api_tokens t ON t.id=u.token_id {where} "
              "ORDER BY u.id DESC LIMIT ?", (*args, limit))


# ------------------------------------------------------------------ журнал действий для админов

EVENT_TTL = 30 * 24 * 3600


def log_event(kind: str, action: str, *, user: dict | None = None, login: str = "", ip: str = "", detail: str = "",
              path: str = "", run_id: str = "", status: int | None = None, device: str = "") -> int:
    """Событие в ленту админов. IP сюда приходит уже обрезанным, хранится 30 дней."""
    eid = _x("INSERT INTO events (ts, user_id, login, ip, kind, action, detail, path, run_id, status, device) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
             (time.time(), (user or {}).get("id"), (user or {}).get("login") or login or "", ip[:40], kind, action[:200],
              (detail or "")[:400], (path or "")[:300], run_id or "", status, device[:60]))
    if eid % 500 == 0:
        _x("DELETE FROM events WHERE ts<?", (time.time() - EVENT_TTL,))
    return eid


def events_after(after_id: int = 0, limit: int = 200) -> list[dict]:
    return _q("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (after_id, limit))


def events_recent(limit: int = 200) -> list[dict]:
    return _q("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


def events_stats() -> dict:
    day = _day_start()
    row = _q("SELECT COUNT(*) n, SUM(kind='auth') auth, SUM(kind='action') act FROM events WHERE ts>=?", (day,), one=True)
    return dict(today=row["n"] or 0, auth=row["auth"] or 0, actions=row["act"] or 0)


def online(minutes: int = 5) -> list[dict]:
    """Кто был на сайте за последние минуты: вошедшие по логину, гости по началу IP и устройству."""
    since = time.time() - minutes * 60
    rows = _q("SELECT login, ip, device, MAX(ts) last, COUNT(*) n FROM events WHERE ts>=? AND kind!='system' "
              "GROUP BY CASE WHEN login!='' THEN login ELSE ip || device END ORDER BY last DESC", (since,))
    return rows


# ------------------------------------------------------------------ Telegram-бот

TG_CODE_TTL = 600


def create_tg_code(user: dict) -> str:
    """Одноразовый код привязки Telegram на 10 минут; в базе только хеш."""
    if not user or user.get("blocked"):
        raise AccountError("нужен вход")
    code, now = secrets.token_urlsafe(9), time.time()
    _x("DELETE FROM tg_codes WHERE expires<? OR user_id=?", (now, user["id"]))
    _x("INSERT INTO tg_codes (code_hash, user_id, expires) VALUES (?,?,?)", (_token_hash(code), user["id"], now + TG_CODE_TTL))
    return code


def consume_tg_code(code: str, chat_id: int, username: str = "") -> dict:
    row = _q("SELECT * FROM tg_codes WHERE code_hash=?", (_token_hash(code or ""),), one=True)
    if not row or row["expires"] < time.time():
        raise AccountError("код привязки не найден или устарел — получите новый в кабинете стенда")
    user = get_user(row["user_id"])
    if not user or user["blocked"]:
        raise AccountError("учётная запись недоступна")
    with _lock:
        c = _conn()
        try:
            c.execute("DELETE FROM tg_codes WHERE code_hash=?", (row["code_hash"],))
            c.execute("DELETE FROM tg_links WHERE chat_id=? OR user_id=?", (chat_id, user["id"]))
            c.execute("INSERT INTO tg_links (user_id, chat_id, username, linked) VALUES (?,?,?,?)",
                      (user["id"], chat_id, (username or "")[:64], time.time()))
        finally:
            c.close()
    return user


def tg_user(chat_id: int) -> dict | None:
    """Пользователь стенда, привязанный к чату; заблокированный не считается."""
    link = _q("SELECT * FROM tg_links WHERE chat_id=?", (chat_id,), one=True)
    user = get_user(link["user_id"]) if link else None
    return user if user and not user["blocked"] else None


def tg_link_for_user(uid: int) -> dict | None:
    return _q("SELECT * FROM tg_links WHERE user_id=?", (uid,), one=True)


def unlink_tg(chat_id: int | None = None, user_id: int | None = None):
    _x("DELETE FROM tg_links WHERE chat_id=? OR user_id=?", (chat_id if chat_id is not None else -1, user_id if user_id is not None else -1))


def admin_tg_chats() -> list[int]:
    return [r["chat_id"] for r in _q("SELECT l.chat_id FROM tg_links l JOIN users u ON u.id=l.user_id WHERE u.role='admin' AND u.blocked=0")]


def tg_add_run(run_id: str, user_id: int, chat_id: int, message_id: int | None, kind: str):
    _x("INSERT OR REPLACE INTO tg_runs (run_id, user_id, chat_id, message_id, kind, created) VALUES (?,?,?,?,?,?)",
       (run_id, user_id, chat_id, message_id, kind, time.time()))


def tg_active_runs() -> list[dict]:
    return _q("SELECT * FROM tg_runs WHERE done=0 ORDER BY created")


def tg_finish_run(run_id: str):
    _x("UPDATE tg_runs SET done=1 WHERE run_id=?", (run_id,))


def tg_runs_today(user_id: int) -> int:
    return _q("SELECT COUNT(*) n FROM tg_runs WHERE user_id=? AND created>=?", (user_id, _day_start()), one=True)["n"]


def tg_state(key: str, value: str | None = None) -> str | None:
    if value is None:
        row = _q("SELECT value FROM tg_state WHERE key=?", (key,), one=True)
        return row["value"] if row else None
    _x("INSERT OR REPLACE INTO tg_state (key, value) VALUES (?,?)", (key, value))
    return value


def tg_group(chat_id: int) -> dict | None:
    """Группа, куда добавили бота: status allowed — бот работает, pending — ждёт решения, blocked — бот выходит."""
    return _q("SELECT * FROM tg_groups WHERE chat_id=?", (chat_id,), one=True)


def tg_group_save(chat_id: int, title: str, status: str, added_by: str = "", added_by_id: int | None = None):
    _x("INSERT OR REPLACE INTO tg_groups (chat_id, title, status, added_by, added_by_id, created) VALUES (?,?,?,?,?,?)",
       (chat_id, (title or "")[:120], status, (added_by or "")[:64], added_by_id, time.time()))


def tg_group_set(chat_id: int, **fields):
    cols = {k: v for k, v in fields.items() if k in ("title", "status")}
    if cols:
        _x(f"UPDATE tg_groups SET {', '.join(k + '=?' for k in cols)} WHERE chat_id=?", (*cols.values(), chat_id))


def tg_groups(status: str | None = "allowed") -> list[dict]:
    if status is None:
        return _q("SELECT * FROM tg_groups ORDER BY created")
    return _q("SELECT * FROM tg_groups WHERE status=? ORDER BY created", (status,))


def tg_group_delete(chat_id: int):
    _x("DELETE FROM tg_groups WHERE chat_id=?", (chat_id,))


def tg_group_migrate(old: int, new: int):
    """Группа стала супергруппой — у неё новый id."""
    _x("UPDATE OR REPLACE tg_groups SET chat_id=? WHERE chat_id=?", (new, old))


# ------------------------------------------------------------------ приглашения

INVITE_ROLES = {"admin": "админ", "ask": "доступ к вопросам Claude"}
INVITE_DEFAULT_HOURS = 48
INVITE_MAX_HOURS = 24 * 30
PUBLIC_URL = os.environ.get("DXAQC_PUBLIC_URL", "https://ltz2026.ru").rstrip("/")
INVITE_ERRORS = {"used": "это приглашение уже использовано", "expired": "срок действия приглашения истёк",
                 "revoked": "приглашение отозвано админом"}


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def invite_url(token: str, base: str | None = None) -> str:
    return f"{(base or PUBLIC_URL).rstrip('/')}/invite/{token}"


def _with_status(row: dict | None) -> dict | None:
    if not row:
        return None
    row["status"] = ("revoked" if row["revoked"] else "used" if row["used_by"] else
                     "expired" if row["expires"] <= time.time() else "active")
    return row


_INVITE_SELECT = "SELECT i.*, u.login AS used_login FROM invites i LEFT JOIN users u ON u.id = i.used_by"


def create_invite(created_by: str, role: str = "admin", hours: float = INVITE_DEFAULT_HOURS, note: str = "") -> tuple[str, dict]:
    """→ (токен, приглашение). Токен показывается один раз, в базе только его хеш."""
    if role not in INVITE_ROLES:
        raise AccountError("неизвестная роль приглашения")
    hours = float(hours)
    if not 0 < hours <= INVITE_MAX_HOURS:
        raise AccountError(f"срок действия — до {INVITE_MAX_HOURS // 24} дней")
    token, now = secrets.token_urlsafe(32), time.time()
    iid = _x("INSERT INTO invites (token_hash, role, note, created_by, created, expires) VALUES (?,?,?,?,?,?)",
             (_token_hash(token), role, (note or "").strip()[:200], created_by[:40], now, now + hours * 3600))
    return token, get_invite_by_id(iid)


def get_invite_by_id(iid: int) -> dict | None:
    return _with_status(_q(_INVITE_SELECT + " WHERE i.id=?", (iid,), one=True))


def get_invite(token: str) -> dict | None:
    if not token or len(token) > 100:
        return None
    return _with_status(_q(_INVITE_SELECT + " WHERE i.token_hash=?", (_token_hash(token),), one=True))


def list_invites(limit: int = 50) -> list[dict]:
    return [_with_status(r) for r in _q(_INVITE_SELECT + " ORDER BY i.id DESC LIMIT ?", (limit,))]


def check_invite(token: str) -> dict:
    inv = get_invite(token)
    if not inv:
        raise AccountError("приглашение не найдено")
    if inv["status"] != "active":
        raise AccountError(INVITE_ERRORS[inv["status"]])
    return inv


def revoke_invite(iid: int):
    _x("UPDATE invites SET revoked=1 WHERE id=? AND used_by IS NULL", (iid,))


def accept_invite(token: str, user: dict) -> dict:
    """Погасить приглашение и выдать его роль пользователю. Одновременное второе использование не пройдёт."""
    inv = check_invite(token)
    if not user or user.get("blocked"):
        raise AccountError("нужен вход")
    with _lock:
        c = _conn()
        try:
            now = time.time()
            cur = c.execute("UPDATE invites SET used_by=?, used_at=? WHERE id=? AND used_by IS NULL AND revoked=0 AND expires>?",
                            (user["id"], now, inv["id"], now))
            if cur.rowcount != 1:
                raise AccountError(INVITE_ERRORS["used"])
        finally:
            c.close()
    if inv["role"] == "admin":
        update_user(user["id"], role="admin", can_ask=True, blocked=False)
    else:
        update_user(user["id"], can_ask=True)
    return get_user(user["id"])


# ------------------------------------------------------------------ командная строка

def _main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Учётные записи стенда")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("create-admin", "set-password"):
        sp = sub.add_parser(name)
        sp.add_argument("login")
    inv = sub.add_parser("invite", help="одноразовая инвайт-ссылка")
    inv.add_argument("--role", choices=sorted(INVITE_ROLES), default="admin")
    inv.add_argument("--hours", type=float, default=INVITE_DEFAULT_HOURS)
    inv.add_argument("--note", default="")
    inv.add_argument("--by", default="claude")
    a = p.parse_args(argv)
    if a.cmd == "invite":
        token, invite = create_invite(a.by, role=a.role, hours=a.hours, note=a.note)
        until = time.strftime("%d.%m %H:%M", time.gmtime(invite["expires"] + MSK))
        print(f"{INVITE_ROLES[a.role]}, одноразовая, до {until} МСК: {invite_url(token)}")
        return
    password = secrets.token_urlsafe(12)
    u = get_user_by_login(a.login)
    if a.cmd == "create-admin":
        if u:
            update_user(u["id"], role="admin", can_ask=True, blocked=False)
            set_password(u["id"], password)
        else:
            create_user(a.login, password, role="admin", can_ask=True, daily_limit=1000)
        print(f"админ {a.login}, пароль: {password}")
    else:
        if not u:
            raise SystemExit("нет такого пользователя")
        set_password(u["id"], password)
        print(f"{a.login}, новый пароль: {password}")


if __name__ == "__main__":
    _main()
