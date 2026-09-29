# -*- coding: utf-8 -*-
"""Документация Kostik одним интерактивным PDF: README и doc/*.md → HTML с оглавлением и якорями → PDF (Chromium).

В PDF кликабельное оглавление, закладки (outline) по разделам, ссылки между документами ведут внутрь PDF,
внешние — в браузер.

    .venv/bin/python scripts/build_docs_pdf.py out.html   &&   node <скрипт печати> out.html Kostik_docs.pdf
"""
import html
import re
import sys
import time
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
GH = "https://github.com/j0k/ltz2026/blob/main/"
DOCS = [("readme", "README.md", "Обзор решения"), ("user", "doc/USER_GUIDE.md", "Руководство пользователя"),
        ("deploy", "doc/DEPLOY.md", "Руководство по развёртыванию"), ("training", "doc/TRAINING.md", "Обучение моделей"),
        ("learning", "doc/LEARNING.md", "Дообучение на правках врачей и плагины"), ("examples", "doc/EXAMPLES.md", "Примеры снимков"),
        ("demo", "doc/DEMO.md", "Демонстрационный сценарий")]
FILE2ID = {}
for did, path, _ in DOCS:
    FILE2ID[path] = did
    FILE2ID[Path(path).name] = did
    FILE2ID["docs/" + Path(path).name] = did


_n = {}


def slug(text, prefix):
    """Короткий латинский якорь: длинные кириллические имена назначений нарушают лимит PDF на длину имени."""
    _n[prefix] = _n.get(prefix, 0) + 1
    return f"{prefix}-{_n[prefix]}"


def link(m):
    href = m.group(1)
    if href.startswith(("http://", "https://", "mailto:", "#")):
        return f'href="{href}"'
    base = href.split("#")[0]
    if base in FILE2ID:
        return f'href="#doc-{FILE2ID[base]}"'
    return f'href="{GH}{href}"'


md = MarkdownIt("commonmark", {"html": False}).enable("table")
toc, parts = [], []
for did, path, title in DOCS:
    src = (ROOT / path).read_text(encoding="utf-8")
    body = md.render(src)
    heads = []

    def add_id(m, did=did, heads=heads):
        lvl, inner = int(m.group(1)), m.group(2)
        hid = f"doc-{did}" if lvl == 1 and not heads else slug(inner, did)
        heads.append((lvl, hid, re.sub(r"<[^>]+>", "", inner)))
        return f'<h{lvl} id="{hid}">{inner}</h{lvl}>'

    body = re.sub(r"<h([1-3])>(.*?)</h\1>", add_id, body)
    body = re.sub(r'href="([^"]+)"', link, body)
    body = re.sub(r'src="(?!https?:)([^"]+)"', lambda m, d=(ROOT / path).parent: f'src="file://{(d / m.group(1)).resolve()}"', body)
    toc.append((did, title, [h for h in heads if h[0] == 2]))
    parts.append(f'<section class="doc" id="sec-{did}"><div class="doc-tag">{html.escape(title)}</div>{body}</section>')

toc_html = "".join(
    f'<li><a href="#doc-{did}"><b>{html.escape(t)}</b></a><ul>' +
    "".join(f'<li><a href="#{hid}">{html.escape(text)}</a></li>' for _, hid, text in hs) + "</ul></li>"
    for did, t, hs in toc)

page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Kostik — документация</title>
<style>
@page {{ size: A4; margin: 18mm 16mm 18mm 16mm; }}
body {{ font-family: 'DejaVu Sans', sans-serif; font-size: 10.2pt; line-height: 1.5; color: #1C1D22; }}
.cover {{ height: 245mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always;
  background: linear-gradient(135deg, #2D1451, #520977 60%, #8A83D1); color: #fff; padding: 0 18mm; margin: -18mm -16mm 0; }}
.cover h1 {{ font-size: 44pt; margin: 0 0 6mm; color: #fff; border: 0; }}
.cover p {{ font-size: 14pt; margin: 2mm 0; color: #FFD6E3; }} .cover a {{ color: #fff; }}
.toc {{ page-break-after: always; }} .toc h2 {{ color: #520977; }}
.toc ul {{ list-style: none; padding-left: 0; }} .toc ul ul {{ padding-left: 6mm; margin: 1mm 0 3mm; }}
.toc a {{ color: #1C1D22; text-decoration: none; }} .toc a:hover {{ color: #FF0053; }}
.toc > ul > li {{ margin-bottom: 2mm; }}
.doc {{ page-break-before: always; }}
.doc-tag {{ display: inline-block; background: #FF0053; color: #fff; font-weight: 700; font-size: 9pt; letter-spacing: .06em;
  text-transform: uppercase; padding: 1.2mm 3.5mm; border-radius: 3mm; margin-bottom: 3mm; }}
h1 {{ font-size: 20pt; color: #2D1451; margin: 0 0 4mm; }}
h2 {{ font-size: 14pt; color: #520977; margin: 7mm 0 2mm; border-bottom: 1px solid #E5E7E9; padding-bottom: 1mm; }}
h3 {{ font-size: 11.5pt; color: #2D1451; margin: 5mm 0 1.5mm; }}
a {{ color: #520977; }} code {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 8.8pt; background: #F4F1F8; padding: .3mm 1mm; border-radius: 1mm; }}
pre {{ background: #F4F1F8; padding: 3mm 4mm; border-radius: 2mm; white-space: pre-wrap; font-size: 8.6pt; page-break-inside: avoid; }}
pre code {{ background: none; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9pt; page-break-inside: auto; }}
th {{ background: #520977; color: #fff; text-align: left; }} th, td {{ border: 1px solid #E5E7E9; padding: 1.4mm 2mm; vertical-align: top; }}
tr:nth-child(even) td {{ background: #FAF8FC; }}
img {{ max-width: 100%; border: 1px solid #E5E7E9; border-radius: 2mm; margin: 1mm 0 3mm; page-break-inside: avoid; }}
p:has(> img) {{ page-break-inside: avoid; }}
</style></head><body>
<div class="cover"><h1>Kostik</h1><p>Контроль качества снимков денситометрии DXA</p>
<p>Документация · версия 0.5.4 · приложение 1.0-Beta · {time.strftime('%d.%m.%Y')}</p>
<p>Команда «Квантовый Скачок»: Юрий Коноплёв, Алексей Чуркин</p>
<p><a href="https://ltz2026.ru/">https://ltz2026.ru/</a> · <a href="https://github.com/j0k/ltz2026">github.com/j0k/ltz2026</a></p></div>
<div class="toc"><h2>Содержание</h2><ul>{toc_html}</ul></div>
{''.join(parts)}
</body></html>"""
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/kostik_docs.html"
Path(out).write_text(page, encoding="utf-8")
print(out)
