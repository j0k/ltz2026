#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Работа с Trac проекта из командной строки: эпики (вехи) и тикеты.

Плагина XML-RPC в образе нет, поэтому команды выполняются Python-API Trac внутри контейнера
через `docker exec`. Вывод — JSON.

Примеры:
  tools/trac_cli.py epic-add "MVP · промежуточная сдача" --due 2026-09-29 --desc "..."
  tools/trac_cli.py epics
  tools/trac_cli.py add "Загрузчик DICOM" --epic "MVP · промежуточная сдача" --component "Пайплайн и API" --priority critical
  tools/trac_cli.py list --epic "MVP · промежуточная сдача" --status open
  tools/trac_cli.py show 12
  tools/trac_cli.py update 12 --status closed --comment "готово"
"""
import argparse
import json
import subprocess
import sys

CONTAINER = "ltz_trac"
ENV = "/trac/env"

INNER = r'''
import json, sys
from datetime import datetime
from trac.env import open_environment
from trac.ticket.model import Ticket, Milestone
from trac.ticket.query import Query
from trac.util.datefmt import utc, parse_date

a = json.loads(sys.stdin.read())
env = open_environment(ENV)
cmd = a["cmd"]
out = None

def tdict(t):
    return {k: (str(v) if v is not None else None) for k, v in
            dict(id=t.id, summary=t["summary"], type=t["type"], status=t["status"],
                 priority=t["priority"], component=t["component"], epic=t["milestone"],
                 owner=t["owner"], keywords=t["keywords"]).items()}

if cmd == "epic-add":
    m = Milestone(env)
    m.name = a["name"]
    m.description = a.get("desc") or ""
    if a.get("due"):
        m.due = parse_date(a["due"] + "T23:59:59", utc)
    m.insert()
    out = {"created_epic": m.name}
elif cmd == "epics":
    res = []
    for m in Milestone.select(env, include_completed=True):
        q = Query.from_string(env, "milestone=%s&max=0" % m.name.replace("&", "\\&"))
        tickets = q.execute()
        closed = sum(1 for t in tickets if t["status"] == "closed")
        res.append(dict(epic=m.name, due=str(m.due.date()) if m.due else None,
                        done=bool(m.completed), tickets=len(tickets), closed=closed))
    out = res
elif cmd == "add":
    t = Ticket(env)
    t["summary"] = a["summary"]
    t["reporter"] = a.get("reporter") or "claude"
    t["type"] = a.get("type") or "task"
    t["status"] = "new"
    t["priority"] = a.get("priority") or "major"
    if a.get("component"): t["component"] = a["component"]
    if a.get("epic"): t["milestone"] = a["epic"]
    if a.get("owner"): t["owner"] = a["owner"]
    if a.get("keywords"): t["keywords"] = a["keywords"]
    t["description"] = a.get("desc") or ""
    t.insert()
    out = tdict(t)
elif cmd == "list":
    parts = []
    if a.get("epic"): parts.append("milestone=" + a["epic"].replace("&", "\\&"))
    if a.get("status") == "open": parts.append("status!=closed")
    elif a.get("status"): parts.append("status=" + a["status"])
    if a.get("component"): parts.append("component=" + a["component"])
    parts += ["max=0", "order=id"] + ["col=" + c for c in ("id", "summary", "status", "priority", "component", "milestone", "type")]
    q = Query.from_string(env, "&".join(parts))
    out = [dict(id=r["id"], summary=r["summary"], status=r["status"], priority=r["priority"],
                component=r["component"], epic=r["milestone"], type=r["type"]) for r in q.execute()]
elif cmd == "show":
    t = Ticket(env, int(a["id"]))
    out = tdict(t)
    out["description"] = t["description"]
elif cmd == "update":
    t = Ticket(env, int(a["id"]))
    for k_cli, k_trac in (("status", "status"), ("priority", "priority"), ("component", "component"),
                          ("epic", "milestone"), ("owner", "owner"), ("summary", "summary"), ("type", "type")):
        if a.get(k_cli):
            t[k_trac] = a[k_cli]
    if a.get("status") == "closed":
        t["resolution"] = a.get("resolution") or "fixed"
    elif a.get("status"):
        t["resolution"] = ""
    t.save_changes(author=a.get("reporter") or "claude", comment=a.get("comment") or "")
    out = tdict(t)
print(json.dumps(out, ensure_ascii=False))
'''.replace("ENV", repr(ENV), 1)


def run(payload):
    proc = subprocess.run(["docker", "exec", "-i", CONTAINER, "python", "-c", INNER],
                          input=json.dumps(payload), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-2000:])
        sys.exit(proc.returncode)
    print(proc.stdout.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("epic-add"); e.add_argument("name"); e.add_argument("--due"); e.add_argument("--desc")
    sub.add_parser("epics")
    t = sub.add_parser("add"); t.add_argument("summary")
    for f in ("epic", "component", "priority", "type", "owner", "keywords", "desc", "reporter"):
        t.add_argument("--" + f)
    ls = sub.add_parser("list")
    for f in ("epic", "status", "component"):
        ls.add_argument("--" + f)
    s = sub.add_parser("show"); s.add_argument("id")
    u = sub.add_parser("update"); u.add_argument("id")
    for f in ("status", "resolution", "priority", "component", "epic", "owner", "summary", "type", "comment", "reporter"):
        u.add_argument("--" + f)
    args = {k: v for k, v in vars(p.parse_args()).items() if v is not None}
    run(args)


if __name__ == "__main__":
    main()
