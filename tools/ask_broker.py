# -*- coding: utf-8 -*-
"""Брокер вопросов со стенда LTZ2026 к Claude через отдельный инстанс Codellake.

Каждый вопрос — новая сессия Codellake, поэтому контекст разных пользователей не смешивается, и свой режим прав:
  read — только чтение: команды, правка файлов, веб и подагенты запрещены на уровне Claude Code;
  full — полные права в рабочей папке; стенд отправляет такой вопрос только после одобрения админом.
Вопросы выполняются по одному. Результаты хранятся в памяти 6 часов.

    /home/jk/exp/Codellake/.venv/bin/python tools/ask_broker.py --instance LTZ-ASK \
        --workspace /home/jk/exp/ltz2026-workspace --host 172.27.0.1 --port 8099

HTTP API, заголовок «Authorization: Bearer <токен>», токен в ~/.codellake/instances/<инстанс>/broker_token:
  GET  /v1/health
  POST /v1/questions        {"id", "text", "mode": "read"|"full", "user", "approver", "attachments": [{"name", "data": base64}]}  -> 202
                            вложения (PNG/JPEG до 5 МБ) кладутся в <рабочая папка>/.ltz_attachments/<id>/ и удаляются после ответа
  GET  /v1/questions/<id>   -> {"status": "queued|running|done|error", "answer", "error", "started", "finished"}
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

READ_ONLY_DENY = ("Bash", "BashOutput", "KillShell", "Edit", "MultiEdit", "Write", "NotebookEdit",
                  "WebFetch", "WebSearch", "Task", "Agent")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
KEEP_SEC = 6 * 3600
MAX_BODY = 8 * 1024 * 1024          # вложение-снимок в base64
MAX_ATTACHMENT = 5 * 1024 * 1024
ATTACH_DIR = ".ltz_attachments"     # внутри рабочей папки: инструмент Read в режиме чтения видит только её


def instance_home(name: str) -> Path:
    return Path.home() / ".codellake" / "instances" / name


def prompt_for(job: dict) -> str:
    who = job.get("user") or "пользователь"
    if job["mode"] == "full":
        rights = (f"Режим: исполнение, одобрено админом {job.get('approver') or ''}. Можно запускать команды и менять файлы, "
                  "но только внутри рабочей папки; ничего не удаляй за её пределами и не меняй настройки системы.")
    else:
        rights = ("Режим: только чтение. Запускать команды и менять файлы нельзя. Если без этого не ответить, "
                  "скажи, что именно нужно выполнить, и предложи запросить исполнение у админа.")
    files = ""
    if job.get("files"):
        files = ("Приложенные изображения, открой их инструментом Read и смотри сами пиксели:\n"
                 + "\n".join(f"- {p}" for p in job["files"]) + "\n")
    return (f"Вопрос от пользователя «{who}» веб-стенда DXA QC команды «Квантовый Скачок» (ЛЦТ 2026).\n"
            "Рабочая папка — копия проекта, её состав описан в README_WORKSPACE.md.\n"
            f"{rights}\n"
            "Отвечай по-русски и по существу, файлы указывай в виде путь:строка.\n"
            f"{files}\n"
            f"Вопрос:\n{job['text']}")


def save_attachments(workspace: str, jid: str, items) -> list[str]:
    """Вложения вопроса в рабочую папку: только PNG и JPEG до 5 МБ, имена очищаются."""
    import base64
    out = []
    folder = Path(workspace) / ATTACH_DIR / jid
    for i, item in enumerate((items or [])[:2]):
        data = base64.b64decode(str(item.get("data", "")), validate=True)
        if len(data) > MAX_ATTACHMENT or not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
            raise ValueError("вложение: только PNG или JPEG до 5 МБ")
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(item.get("name") or f"image{i}.png"))[:40]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{i}_{name}"
        path.write_bytes(data)
        out.append(str(path))
    return out


class Runner:
    def __init__(self, config_path: Path, workspace: str):
        self.config_path, self.workspace = config_path, workspace
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._loop, name="ask-runner", daemon=True).start()

    def submit(self, job: dict) -> dict:
        with self.lock:
            if job["id"] in self.jobs:  # повтор того же запроса не ставит вопрос второй раз
                return dict(self.jobs[job["id"]])
            job.update(status="queued", answer="", error="", created=time.time(), started=None, finished=None)
            self.jobs[job["id"]] = job
        self.queue.put(job["id"])
        return dict(job)

    def get(self, jid: str) -> dict | None:
        with self.lock:
            now = time.time()
            for k in [k for k, j in self.jobs.items() if j.get("finished") and now - j["finished"] > KEEP_SEC]:
                del self.jobs[k]
            job = self.jobs.get(jid)
            return dict(job) if job else None

    def _loop(self):
        while True:
            jid = self.queue.get()
            with self.lock:
                job = self.jobs.get(jid)
                if not job:
                    continue
                job.update(status="running", started=time.time())
            print(f"[broker] {jid} {job['mode']} от {job.get('user')}: {job['text'][:80]!r}", flush=True)
            try:
                answer = self._ask(job) or "(пустой ответ)"
                with self.lock:
                    job.update(status="done", answer=answer)
            except Exception as exc:  # noqa: BLE001 — ошибка уходит пользователю, брокер продолжает работать
                traceback.print_exc()
                with self.lock:
                    job.update(status="error", error=f"{type(exc).__name__}: {exc}"[:1500])
            if job.get("files"):   # вложения нужны только на время ответа
                import shutil
                shutil.rmtree(Path(self.workspace) / ATTACH_DIR / jid, ignore_errors=True)
            with self.lock:
                job["finished"] = time.time()
            print(f"[broker] {jid} {job['status']} за {job['finished'] - job['started']:.0f} с", flush=True)

    def _ask(self, job: dict) -> str:
        from codellake.agent.claude_backend import build_claude_backend
        from codellake.core.config import load_config
        from codellake.core.session import Session

        cfg = load_config(self.config_path)
        cc = cfg.claude
        extra = [a for a in (cc.extra_args or []) if a != "--dangerously-skip-permissions"]
        if job["mode"] == "full":
            mode = "bypassPermissions"
            extra.append("--dangerously-skip-permissions")
        else:
            mode = "default"  # в неинтерактивном режиме всё, что требует разрешения, отклоняется
            extra.append("--disallowedTools=" + ",".join(READ_ONLY_DENY))
        cc.extra_args = extra
        cc.permission_mode = mode
        backend = build_claude_backend(cfg, workspace=self.workspace, permission_mode=mode)
        session = Session.create(workspace=self.workspace, model=cc.model)  # новая сессия на каждый вопрос
        out = backend.run(prompt_for(job), session=session)
        return getattr(out, "text", "") or ""


def make_handler(runner: Runner, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ltz-ask-broker"

        def log_message(self, fmt, *args):
            sys.stderr.write("[broker-http] " + fmt % args + "\n")

        def _json(self, code: int, obj: dict):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _auth(self) -> bool:
            got = self.headers.get("Authorization", "")
            if got.startswith("Bearer ") and hmac.compare_digest(got[7:].encode(), token.encode()):
                return True
            self._json(401, {"error": "unauthorized"})
            return False

        def do_GET(self):
            if not self._auth():
                return
            if self.path == "/v1/health":
                return self._json(200, {"status": "ok", "queue": runner.queue.qsize()})
            m = re.fullmatch(r"/v1/questions/([A-Za-z0-9_-]{1,64})", self.path)
            job = runner.get(m.group(1)) if m else None
            if not job:
                return self._json(404, {"error": "not found"})
            self._json(200, {k: job.get(k) for k in ("id", "status", "answer", "error", "started", "finished")})

        def do_POST(self):
            if not self._auth():
                return
            if self.path != "/v1/questions":
                return self._json(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"error": "too large"})
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"error": "bad json"})
            jid, text, mode = str(data.get("id", "")), str(data.get("text", "")).strip(), data.get("mode")
            if not ID_RE.match(jid) or not text or mode not in ("read", "full"):
                return self._json(400, {"error": "id, text и mode read|full обязательны"})
            try:
                files = save_attachments(runner.workspace, jid, data.get("attachments")) if data.get("attachments") else []
            except (ValueError, TypeError) as exc:
                return self._json(400, {"error": str(exc)[:200]})
            job = runner.submit(dict(id=jid, text=text[:8000], mode=mode, files=files,
                                     user=str(data.get("user", ""))[:40], approver=str(data.get("approver", ""))[:40]))
            self._json(202, {"id": jid, "status": job["status"]})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Брокер вопросов стенда к Claude через Codellake")
    ap.add_argument("--instance", default="LTZ-ASK")
    ap.add_argument("--workspace", default="/home/jk/exp/ltz2026-workspace")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    a = ap.parse_args()

    home = instance_home(a.instance)
    config = home / "config.yaml"
    if not config.is_file():
        sys.exit(f"нет {config}: создайте конфиг инстанса")
    if not os.path.isdir(a.workspace):
        sys.exit(f"нет рабочей папки {a.workspace}: запустите tools/sync_workspace.sh")
    os.environ["CODELLAKE_CONFIG"] = str(config)
    os.environ["CODELLAKE_AUDIT"] = str(home / "audit.jsonl")
    os.environ["CODELLAKE_SESSIONS_DIR"] = str(home / "sessions")
    token_file = home / "broker_token"
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32) + "\n")
        token_file.chmod(0o600)
    token = token_file.read_text().strip()

    server = ThreadingHTTPServer((a.host, a.port), make_handler(Runner(config, a.workspace), token))
    print(f"[broker] {a.instance}: http://{a.host}:{a.port}, рабочая папка {a.workspace}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
