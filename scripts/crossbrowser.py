# -*- coding: utf-8 -*-
"""Кроссбраузерная проверка главной: Chromium, Firefox и WebKit (движок Safari) на нескольких ширинах экрана.

    python scripts/crossbrowser.py http://127.0.0.1:8768 --out /tmp/xb

Для каждого движка и ширины: нет горизонтальной прокрутки, нет ошибок JavaScript, шрифт Inter загружен,
положение и размеры ключевых блоков. Расхождение с Chromium больше 2 px — провал. Сохраняет снимки первого экрана
и сводный лист contact_sheet.png. Анимации выключены (prefers-reduced-motion), чтобы кадры были сравнимы.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

VIEWPORTS = [(1440, 900), (1024, 768), (768, 1024), (390, 844), (320, 640)]
BLOCKS = {"заголовок": ".hero h1", "подзаголовок": ".lede", "загрузка": "#upload", "кнопка": "form.upload button",
          "визуализация": ".hero-viz", "возможности": "#about", "наборы": "#check", "точность": "#accuracy", "прогоны": "#runs"}
TOL = 2
CHROME = os.environ.get("FILM_CHROME") or sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))[-1]


def measure(page) -> dict:
    return page.evaluate("""(blocks) => {
        const out = {};
        for (const [name, sel] of Object.entries(blocks)) {
            const el = document.querySelector(sel);
            if (!el) { out[name] = null; continue; }
            const r = el.getBoundingClientRect();
            out[name] = [Math.round(r.left), Math.round(r.top + window.scrollY), Math.round(r.width), Math.round(r.height)];
        }
        return out;
    }""", BLOCKS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="/tmp/crossbrowser")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    results, failures, shots = {}, [], []
    with sync_playwright() as p:
        engines = [("chromium", p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--lang=ru"])),
                   ("firefox", p.firefox.launch()), ("webkit", p.webkit.launch())]
        for name, browser in engines:
            for w, h in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ru-RU",
                                          reduced_motion="reduce")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(a.url, wait_until="networkidle")
                page.evaluate("document.fonts.ready")
                fonts = page.evaluate("[...document.fonts].filter(f => f.family.includes('InterDXA') && f.status === 'loaded').length")
                doc_w = page.evaluate("document.documentElement.scrollWidth")
                boxes = measure(page)
                results[(name, w)] = boxes
                if doc_w > w:
                    failures.append(f"{name} {w}px: горизонтальная прокрутка, документ {doc_w}px")
                if errors:
                    failures.append(f"{name} {w}px: ошибки JS: {errors[:2]}")
                if not fonts:
                    failures.append(f"{name} {w}px: шрифт Inter не загрузился")
                missing = [k for k, v in boxes.items() if v is None]
                if missing:
                    failures.append(f"{name} {w}px: нет блоков {missing}")
                path = os.path.join(a.out, f"{name}_{w}.png")
                page.screenshot(path=path)
                shots.append((name, w, path))
                ctx.close()
            browser.close()

    print(f"{'ширина':>7} | {'движок':9} | макс. расхождение с Chromium, px (блок)")
    for w, _ in VIEWPORTS:
        base = results[("chromium", w)]
        for name in ("firefox", "webkit"):
            other = results[(name, w)]
            worst, where = 0, ""
            for k, b in base.items():
                o = other.get(k)
                if not b or not o:
                    continue
                d = max(abs(x - y) for x, y in zip(b, o))
                if d > worst:
                    worst, where = d, k
            print(f"{w:>7} | {name:9} | {worst:>3} {('(' + where + ')') if where else ''}")
            if worst > TOL:
                failures.append(f"{name} {w}px: расхождение {worst}px в блоке «{where}»: chromium {base[where]} против {other[where]}")

    # сводный лист: строки — ширины, столбцы — движки, кадр первого экрана уменьшен до 360 px
    thumb_w, pad, head = 360, 16, 28
    rows = []
    for w, h in VIEWPORTS:
        ims = [Image.open(pth) for n, ww, pth in shots if ww == w]
        k = thumb_w / max(im.width for im in ims)
        ims = [im.resize((round(im.width * k), round(im.height * k))) for im in ims]
        rows.append((w, ims))
    width = pad + 3 * (thumb_w + pad)
    height = sum(head + max(im.height for im in ims) + pad for _, ims in rows) + head
    sheet = Image.new("RGB", (width, height), "#e9eef4")
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for i, n in enumerate(("Chromium", "Firefox", "WebKit (Safari)")):
        d.text((pad + i * (thumb_w + pad), 6), n, fill="#0b1b2b", font=font)
    y = head
    for w, ims in rows:
        d.text((pad, y + 4), f"{w} px", fill="#48607a", font=font)
        for i, im in enumerate(ims):
            sheet.paste(im, (pad + i * (thumb_w + pad), y + head))
        y += head + max(im.height for im in ims) + pad
    sheet.save(os.path.join(a.out, "contact_sheet.png"))

    print("\n" + ("всё совпало" if not failures else "проблемы:\n  " + "\n  ".join(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
