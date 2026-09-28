# -*- coding: utf-8 -*-
"""MCP по stdio для Claude Desktop (#153): те же инструменты, что у HTTP-сервера, в процессе приложения.

Протокол — JSON-RPC построчно: запрос в stdin, ответ в stdout. Всё прочее, что печатает сервис, уходит в stderr,
чтобы не сломать протокол. Окно приложения для работы не нужно.
"""
from __future__ import annotations

import asyncio
import json
import sys


class _Request:
    headers: dict = {}
    client = None


def serve() -> int:
    out = sys.stdout
    sys.stdout = sys.stderr                       # печать сервиса — не в канал протокола
    from dxaqc.web import accounts as A, app as webapp, desktop, mcp  # noqa: F401 — импорт настраивает сервис
    token = A.resolve_api_token(desktop.mcp_token() or "")
    if not token:
        print("[mcp] ИИ-ассистент выключен в приложении: Kostik → ИИ-ассистент → Включить", file=sys.stderr, flush=True)
        return 1
    loop = asyncio.new_event_loop()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "строка не JSON"}}
        else:
            items = msg if isinstance(msg, list) else [msg]
            answers = [loop.run_until_complete(mcp._handle(m, token, _Request(), len(line), None))[0] for m in items]
            answers = [x for x in answers if x is not None]
            if not answers:
                continue
            resp = answers if isinstance(msg, list) else answers[0]
        out.write(json.dumps(resp, ensure_ascii=False) + "\n")
        out.flush()
    return 0
