# -*- coding: utf-8 -*-
"""Плагин Kostik для Claude Code (30.09, Юрий): состав, запуск сервера MCP и ни токенов, ни личных данных внутри."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "kostik")


def _json(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def _texts():
    files = [os.path.join(ROOT, ".claude-plugin", "marketplace.json")]
    for folder, _, names in os.walk(PLUGIN):
        files += [os.path.join(folder, n) for n in names]
    for path in files:
        with open(path, encoding="utf-8") as f:
            yield os.path.relpath(path, ROOT), f.read()


def test_plugin_layout():
    market = _json(ROOT, ".claude-plugin", "marketplace.json")
    entry = next(p for p in market["plugins"] if p["name"] == "kostik")
    assert os.path.normpath(os.path.join(ROOT, entry["source"])) == PLUGIN
    manifest = _json(PLUGIN, ".claude-plugin", "plugin.json")
    assert manifest["name"] == "kostik" and re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    server = _json(PLUGIN, ".mcp.json")["mcpServers"]["kostik"]
    assert server["args"] == ["--mcp-stdio"] and server["command"].endswith("Kostik-cli.exe}") and "KOSTIK_CLI" in server["command"]
    assert "env" not in server and "headers" not in server and "url" not in server, "сервер — только stdio, без токена"
    for name in ("check", "results", "runs"):
        text = open(os.path.join(PLUGIN, "commands", name + ".md"), encoding="utf-8").read()
        assert text.startswith("---\ndescription: ") or text.startswith("---\r\ndescription: "), name
    skill = open(os.path.join(PLUGIN, "skills", "kostik", "SKILL.md"), encoding="utf-8").read()
    assert re.search(r"^name: kostik\r?$", skill, re.M) and re.search(r"^description: .{80,}", skill, re.M)


def test_plugin_tools_exist(tmp_path):
    """Команды и навык называют только те инструменты, что есть у сервера программы. Сервер спрашиваем так же,
    как Claude Code: отдельным процессом по stdio — и режим приложения не задевает остальные тесты."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    env = dict(os.environ, DXAQC_HOME=str(tmp_path / "home"), PYTHONPATH=ROOT, DXAQC_NO_WEBVIEW="1")
    env.pop("DXAQC_MODE", None); env.pop("DXAQC_DATA", None)
    r = subprocess.run([sys.executable, "-W", "ignore", "-m", "dxaqc.desktop", "--mcp-stdio"], env=env, capture_output=True, text=True,
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", timeout=240)
    known = {t["name"] for t in json.loads(r.stdout.strip().splitlines()[-1])["result"]["tools"]}
    assert {"analyze_paths", "describe_run", "get_run", "list_runs", "get_image"} <= known, r.stderr[-2000:]
    for path, text in _texts():
        if path.endswith(".md"):
            named = set(re.findall(r"`((?:analyze|describe|get|list)_[a-z_]+)`", text))
            assert named <= known, f"{path}: нет инструментов {named - known}"


def test_plugin_has_no_secrets_or_personal_data():
    for path, text in _texts():
        assert not re.search(r"dxq_[A-Za-z0-9]|Bearer\s+\S|api[_-]?key|password|пароль:", text, re.I), f"{path}: похоже на токен"
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), f"{path}: почтовый адрес"
        assert not re.search(r"[A-Za-z]:\\Users\\|/home/\w|/Users/\w", text), f"{path}: путь в папку пользователя"
        assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text.replace("127.0.0.1", "")), f"{path}: сетевой адрес"
        assert not re.search(r"t\.me/|@[a-z_]{4,}\b", text), f"{path}: личный контакт"
