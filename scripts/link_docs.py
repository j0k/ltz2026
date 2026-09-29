# -*- coding: utf-8 -*-
"""Кликабельные кросс-ссылки в документации: упоминания файлов репозитория в doc/*.md, docs/*.md и README.md
становятся относительными ссылками — на GitHub и в PDF по ним можно перейти.

    python scripts/link_docs.py [--check]

Ссылкой становится только файл, который есть в git. Блоки кода ``` и готовые ссылки не трогаются.
--check — ничего не менять, код возврата 1, если есть что связать или битые относительные ссылки.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKED = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split())
BY_NAME: dict[str, list[str]] = {}
for f in TRACKED:
    BY_NAME.setdefault(os.path.basename(f), []).append(f)

SKIP = re.compile(r"\[[^\]]*\]\([^)]*\)|<[^>]+>|https?://\S+")            # готовые ссылки, теги, адреса
CODE = re.compile(r"`([^`\s]+)`")
BARE = re.compile(r"(?<![\w/.`-])((?:\./)?(?:[\w.-]+/)+[\w.-]+\.\w+|[A-Z][A-Z_]+\.md)(?![\w/`])")


def resolve(token: str, doc: Path) -> str | None:
    t = token[2:] if token.startswith("./") else token
    t = t.rstrip(".,;:")
    if t in TRACKED:
        return t
    if t.endswith("/") and t.count("/") >= 1 and any(f.startswith(t) for f in TRACKED):
        return t                                          # папка: GitHub покажет её содержимое
    if "/" not in t and t.endswith(".md"):
        near = str((doc.parent / t).relative_to(ROOT)) if (doc.parent / t).exists() else None
        if near in TRACKED:
            return near
        cands = BY_NAME.get(t, [])
        if len(cands) == 1:
            return cands[0]
    return None


def rel(target: str, doc: Path) -> str:
    r = os.path.relpath(ROOT / target, doc.parent).replace(os.sep, "/")
    return r + "/" if target.endswith("/") else r


def link_segment(seg: str, doc: Path, found: list) -> str:
    def code(m):
        t = resolve(m.group(1), doc)
        if not t:
            return m.group(0)
        found.append(t)
        return f"[`{m.group(1)}`]({rel(t, doc)})"

    parts, pos = [], 0
    for m in CODE.finditer(seg):                  # сначала `код`, между ними — голые пути
        parts.append(bare(seg[pos:m.start()], doc, found))
        parts.append(code(m))
        pos = m.end()
    parts.append(bare(seg[pos:], doc, found))
    return "".join(parts)


def bare(seg: str, doc: Path, found: list) -> str:
    if "`" in seg:
        return seg
    def sub(m):
        tok = m.group(1)
        tail = tok[len(tok.rstrip(".,;:")):]
        t = resolve(tok, doc)
        if not t or ROOT / t == doc:
            return tok
        found.append(t)
        clean = tok[:len(tok) - len(tail)] if tail else tok
        return f"[{clean}]({rel(t, doc)}){tail}"
    return BARE.sub(sub, seg)


def process(doc: Path) -> tuple[str, list, list]:
    found, broken, out, fence = [], [], [], False
    for line in doc.read_text(encoding="utf-8").split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        if fence or line.startswith("    "):
            out.append(line)
            continue
        for m in re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", line):          # проверка готовых относительных ссылок
            href = m.group(1)
            if not href.startswith(("http:", "https:", "mailto:")) and not (doc.parent / href).exists():
                broken.append(href)
        pieces, pos = [], 0
        for m in SKIP.finditer(line):
            pieces.append(link_segment(line[pos:m.start()], doc, found))
            pieces.append(m.group(0))
            pos = m.end()
        pieces.append(link_segment(line[pos:], doc, found))
        out.append("".join(pieces))
    return "\n".join(out), found, broken


def main() -> int:
    check = "--check" in sys.argv
    docs = sorted(ROOT.glob("doc/*.md")) + sorted(ROOT.glob("docs/*.md")) + [ROOT / "README.md"]
    bad = 0
    for doc in docs:
        text, found, broken = process(doc)
        if found:
            print(f"{doc.relative_to(ROOT)}: ссылок {len(found)} — {', '.join(sorted(set(found)))}")
        for b in broken:
            print(f"{doc.relative_to(ROOT)}: битая ссылка {b}")
        bad += len(broken) + (len(found) if check else 0)
        if not check and text != doc.read_text(encoding="utf-8"):
            doc.write_text(text, encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
