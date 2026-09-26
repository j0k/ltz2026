# -*- coding: utf-8 -*-
"""Собирает каталог документов для страницы /tz/: жёсткие ссылки на PDF, превью первой страницы и число страниц.

    python scripts/tz_docs.py            → docs/tz/ (в git не попадает, в контейнер монтируется только на чтение)

Что показывать и с каким описанием, задаёт каталог в dxaqc/web/tz.py; здесь только файлы.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dxaqc.web.tz import CATALOG  # noqa: E402

OUT = ROOT / "docs" / "tz"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    for doc in CATALOG:
        # исходники в корне репозитория — симлинки на файлы рядом с ним: жёсткая ссылка на симлинк была бы
        # симлинком с путём хоста, которого нет в контейнере стенда, поэтому берём настоящий файл
        src = (ROOT / doc["source_path"]).resolve()
        if not src.exists():
            print(f"нет файла: {src}")
            continue
        dst = OUT / f"{doc['slug']}.pdf"
        if dst.exists():
            dst.unlink()
        try:
            os.link(src, dst)
        except OSError:
            dst.write_bytes(src.read_bytes())
        info = subprocess.run(["pdfinfo", str(dst)], capture_output=True, text=True).stdout
        pages = next((int(l.split()[-1]) for l in info.splitlines() if l.startswith("Pages:")), None)
        subprocess.run(["pdftoppm", "-png", "-r", "60", "-f", "1", "-l", "1", "-singlefile", str(dst), str(OUT / doc["slug"])], check=True)
        meta[doc["slug"]] = {"pages": pages, "bytes": dst.stat().st_size, "mtime": int(src.stat().st_mtime)}
        print(f"{doc['slug']}: {pages} стр., {dst.stat().st_size // 1024} КБ")
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
