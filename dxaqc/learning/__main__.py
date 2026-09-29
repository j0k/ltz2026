# -*- coding: utf-8 -*-
"""Командная строка дообучения.

    python -m dxaqc.learning status                  плагины, число правок врачей, активные версии, журнал
    python -m dxaqc.learning feedback                правки врачей, которые пойдут в обучение
    python -m dxaqc.learning run [--plugin NAME] [--dry-run] [--force]
    python -m dxaqc.learning rollback NAME [VERSION]
"""
import argparse
import json
import sys

from dxaqc import learning as L


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m dxaqc.learning", description="Дообучение Kostik на правках врачей")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("feedback")
    r = sub.add_parser("run")
    r.add_argument("--plugin", action="append", help="имя плагина (можно несколько); по умолчанию — все")
    r.add_argument("--dry-run", action="store_true", help="обучить и оценить, но не устанавливать")
    r.add_argument("--force", action="store_true", help="запустить, даже если правок врачей меньше минимума")
    b = sub.add_parser("rollback")
    b.add_argument("plugin")
    b.add_argument("version", nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(L.status(), ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "feedback":
        for s in L.feedback(with_pixels=False):
            print(f"{s.region:13} {'брак' if s.bad else 'годен':6} {','.join(s.types) or '—':28} {s.source:20} {s.key}")
    elif a.cmd == "run":
        res = L.run(a.plugin, dry_run=a.dry_run, force=a.force, by="cli", progress=lambda m: print("…", m, file=sys.stderr))
        for x in res:
            print(f"[{x.plugin}] {'OK' if x.ok else '—'} {x.message}")
            if x.metrics:
                print("   кандидат:", json.dumps(x.metrics, ensure_ascii=False))
            if x.baseline:
                print("   действующая:", json.dumps(x.baseline, ensure_ascii=False))
    elif a.cmd == "rollback":
        print("активна:", L.rollback(a.plugin, a.version))


if __name__ == "__main__":
    main()
