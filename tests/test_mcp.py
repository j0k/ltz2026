# -*- coding: utf-8 -*-
"""MCP-сервер: токены от админа, протокол JSON-RPC поверх HTTP, инструменты, права, лимит и статистика в кабинете."""
from __future__ import annotations

import base64
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


def accounts():
    return sys.modules["dxaqc.web.accounts"]


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


@pytest.fixture()
def admin(client):
    A = accounts()
    if not A.get_user_by_login("mcp-admin"):
        A.create_user("mcp-admin", PASSWORD, role="admin", can_ask=True)
    c = TestClient(client.app)
    assert c.post("/login", data={"login": "mcp-admin", "password": PASSWORD}, follow_redirects=False).status_code == 303
    yield c
    c.close()


def issue(admin, name, scope="analyze", limit=500) -> str:
    page = admin.post("/admin/mcp/tokens", data={"name": name, "scope": scope, "days": "30", "daily_limit": str(limit),
                                                  "csrf": csrf_of(admin.get("/admin/mcp").text)})
    assert page.status_code == 200 and "показать токен ещё раз нельзя" in page.text
    return re.search(r'id="tokenValue" type="text" value="(dxq_[^"]+)"', page.text).group(1)


class Mcp:
    def __init__(self, client, token):
        self.c, self.token, self.n, self.session = client, token, 0, None

    def post(self, body, **headers):
        h = {"Authorization": f"Bearer {self.token}", "Accept": "application/json, text/event-stream", **headers}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        return self.c.post("/mcp", json=body, headers=h)

    def rpc(self, method, params=None):
        self.n += 1
        r = self.post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def call(self, name, **args):
        res = self.rpc("tools/call", {"name": name, "arguments": args})["result"]
        return res


def test_auth_protocol_and_scopes(client, admin):
    A = accounts()
    anon = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert anon.status_code == 401 and "Bearer" in anon.headers["www-authenticate"]
    assert client.get("/mcp").status_code == 405
    assert client.post("/mcp", json={}, headers={"Authorization": "Bearer dxq_wrong"}).status_code == 401

    token = issue(admin, "Клиент чтения", scope="read")
    stored = A.resolve_api_token(token)
    assert stored and stored["prefix"] == token[:12] and token not in str(A.list_api_tokens())
    m = Mcp(client, token)
    init = m.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}}})
    assert init.status_code == 200 and init.headers.get("mcp-session-id")
    body = init.json()["result"]
    assert body["protocolVersion"] == "2025-03-26" and body["serverInfo"]["name"] == "dxa-qc" and "tools" in body["capabilities"]
    m.session = init.headers["mcp-session-id"]
    assert m.post({"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    assert m.rpc("initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == "2025-06-18"
    assert m.rpc("ping")["result"] == {}

    names = {t["name"] for t in m.rpc("tools/list")["result"]["tools"]}
    assert "get_results" in names and "analyze_dataset" not in names, "токен чтения не видит запуск анализа"
    denied = m.call("analyze_dataset", dataset="test")
    assert denied["isError"] and "только на чтение" in denied["content"][0]["text"]
    info = m.call("service_info")
    assert not info["isError"] and "result_columns" in info["content"][0]["text"]

    assert m.rpc("nope/method")["error"]["code"] == -32601
    assert m.rpc("tools/call", {"name": "no_such_tool"})["error"]["code"] == -32602
    bad = client.post("/mcp", content=b"{not json", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == -32700
    batch = m.post([{"jsonrpc": "2.0", "id": 10, "method": "ping"}, {"jsonrpc": "2.0", "id": 11, "method": "tools/list"}])
    assert batch.status_code == 200 and [x["id"] for x in batch.json()] == [10, 11]

    # отзыв токена: клиент получает 401 сразу
    tid = stored["id"]
    admin.post(f"/admin/mcp/tokens/{tid}/revoke", data={"csrf": csrf_of(admin.get(f"/admin/mcp/tokens/{tid}").text)})
    r = m.post({"jsonrpc": "2.0", "id": 99, "method": "ping"})
    assert r.status_code == 401 and "отозван" in r.json()["error"]["message"]


def test_daily_limit(client, admin):
    m = Mcp(client, issue(admin, "Лимит", scope="read", limit=2))
    assert not m.call("service_info")["isError"]
    assert not m.call("list_runs", limit=3)["isError"]
    third = m.call("service_info")
    assert third["isError"] and "суточный лимит" in third["content"][0]["text"]


def _wait(m, run_id, timeout=150):
    t0 = time.time()
    while time.time() - t0 < timeout:
        info = m.call("get_run", run_id=run_id)["structuredContent"]
        if info["state"] in ("done", "error", "cancelled"):
            return info
        time.sleep(0.5)
    raise AssertionError("прогон не завершился")


@needs_data
def test_tools_analyze_results_images_and_stats(client, admin):
    m = Mcp(client, issue(admin, "Алексей — Claude Code"))
    m.rpc("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "claude-code", "version": "2.1"}})

    ds = m.call("list_datasets", with_studies=True)["structuredContent"]["datasets"]
    assert {d["id"] for d in ds} >= {"test", "train"} and next(d for d in ds if d["id"] == "train")["studies"]

    started = m.call("analyze_dataset", dataset="test", mode="all")
    run_id = started["structuredContent"]["run_id"]
    info = _wait(m, run_id)
    assert info["state"] == "done" and info["summary"]["images"] == 3 and info["files"]["results_csv"].endswith("results.csv")
    res = m.call("get_results", run_id=run_id, filter="all", limit=2)["structuredContent"]
    assert res["total"] == 3 and res["returned"] == 2 and res["final"] and "anatomical_region" in res["rows"][0]
    spine = next(r for r in m.call("get_results", run_id=run_id)["structuredContent"]["rows"] if r["anatomical_region"] == "lumbar_spine")
    img = m.call("get_image", run_id=run_id, key=spine["key"], include_atlas=True)
    assert all(c["type"] == "text" for c in img["content"]) and "атлас снимков организатора" in img["content"][0]["text"]
    assert m.call("get_image", run_id=run_id, key="nope")["isError"]
    assert m.call("get_run", run_id="../../etc")["isError"]

    upload = m.call("analyze_files", files=[{"name": "Для теста.zip", "content_base64": base64.b64encode(SEED_ZIP.read_bytes()).decode()}],
                    wait=True, title="загрузка через MCP")["structuredContent"]
    assert upload["state"] == "done" and upload["summary"]["images"] == 3, upload
    own = next(r for r in m.call("get_results", run_id=upload["run_id"])["structuredContent"]["rows"] if r["anatomical_region"] == "lumbar_spine")
    atlas = m.call("get_image", run_id=upload["run_id"], key=own["key"], include_atlas=True)
    image = next(c for c in atlas["content"] if c["type"] == "image")
    assert image["mimeType"] == "image/png" and base64.b64decode(image["data"]).startswith(b"\x89PNG")
    assert m.call("analyze_files", files=[{"name": "x.dcm", "content_base64": "@@@"}])["isError"]
    assert "MCP · Алексей — Claude Code" in client.get(f"/runs/{upload['run_id']}").text

    # кабинет админа: сводка, график, инструменты, прогоны, журнал; страница токена
    page = admin.get("/admin/mcp").text
    for marker in ('id="by-day"', "<svg", 'id="by-tool"', "get_results", "Алексей — Claude Code", "claude-code 2.1", 'id="runs"', 'id="log"'):
        assert marker in page, marker
    tid = accounts().resolve_api_token(m.token)["id"]
    detail = admin.get(f"/admin/mcp/tokens/{tid}").text
    assert "analyze_files" in detail and upload["run_id"] in detail and "Отозвать токен" in detail
    stats = sys.modules["dxaqc.web.mcp"].build_stats(tid)
    assert stats["week"]["tool_calls"] >= 9 and any(t["tool"] == "get_run" and t["p50"] is not None for t in stats["tools"])
    assert sum(d["ok"] + d["err"] for d in stats["by_day"]) == stats["week"]["requests"]

    user = TestClient(client.app)
    accounts().create_user("mcp-user", PASSWORD)
    user.post("/login", data={"login": "mcp-user", "password": PASSWORD})
    assert user.get("/admin/mcp").status_code == 403
    assert client.get("/admin/mcp", follow_redirects=False).status_code == 303
    user.close()
