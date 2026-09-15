# -*- coding: utf-8 -*-
"""Проверка просмотра результатов во время прогона: запускает прогон набора организатора и смотрит его в браузере.

    python scripts/e2e_live_peek.py http://127.0.0.1:8765 --shots /tmp/e2e_live --engines chromium,firefox,webkit

Каждый движок получает свой прогон (первый — весь обучающий набор, остальные — выборка), поэтому на стенде не запускать.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = os.environ.get("FILM_CHROME") or sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))[-1]
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def start_run(base: str, data: dict) -> str:
    req = urllib.request.Request(base + "/runs/dataset", data=urllib.parse.urlencode(data).encode(), method="POST")
    try:
        urllib.request.build_opener(NoRedirect).open(req)
    except urllib.error.HTTPError as e:
        return e.headers["Location"].rsplit("/", 1)[1]
    raise RuntimeError("прогон не создан")


def feed_names(page):
    return page.eval_on_selector_all("#live-feed li[data-n] .name", "els => els.map(e => e.textContent)")


def desktop(page, base, rid, tag, shots, full):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/runs/{rid}")
    page.wait_for_selector("#live", timeout=20000)
    page.wait_for_function("document.querySelectorAll('#live-feed li[data-n]').length >= 3", timeout=90000)
    page.wait_for_function("document.getElementById('peek-img').naturalWidth > 0", timeout=20000)
    check(f"{tag}: в режиме слежения виден атлас последнего снимка", page.evaluate("window.__live.follow()") and page.locator("#peek-card").is_visible())
    cap1 = page.inner_text("#peek-cap")
    if full:
        page.wait_for_function(f"document.getElementById('peek-cap').textContent !== {cap1!r}", timeout=15000)
        check(f"{tag}: просмотр сам переходит к новым снимкам", page.inner_text("#peek-cap") != cap1)
        if shots:
            page.screenshot(path=str(shots / f"{tag}_follow.png"))

    items = page.locator("#live-feed li[data-n]")
    target = items.nth(min(2, items.count() - 1))
    n = int(target.get_attribute("data-n"))
    name = target.locator(".name").inner_text()
    target.locator("button").click()
    check(f"{tag}: клик по снимку выключает слежение и открывает его", not page.evaluate("window.__live.follow()")
          and page.evaluate("window.__live.selected()") == n and name in page.inner_text("#peek-name"))
    time.sleep(2.5)
    check(f"{tag}: выбранный снимок остаётся в просмотре", page.evaluate("window.__live.selected()") == n and name in page.inner_text("#peek-name"))
    check(f"{tag}: выбранная строка подсвечена", page.locator(f"#live-feed li[data-n='{n}'].sel").count() == 1)
    if shots and full:
        page.screenshot(path=str(shots / f"{tag}_selected.png"))

    page.click(".live-kpi[data-f=good]")
    pills = page.eval_on_selector_all("#live-feed li[data-n] .pill", "els => els.map(e => e.className)")
    check(f"{tag}: плитка «качественных» фильтрует список", bool(pills) and all("ok" in c for c in pills), str(pills[:5]))
    page.click(".live-kpi[data-f=all]")

    href = page.get_attribute("#peek-open", "href")
    state = page.evaluate("fetch(location.pathname.replace('/runs/', '/api/runs/') + '/progress').then(r => r.json()).then(p => p.state)")
    card = page.context.new_page()
    card.goto(base + href)
    if state == "running":
        check(f"{tag}: карточка открывается до конца прогона", card.locator("#preliminary").count() == 1 or card.locator("#atlasOv").count() == 1)
    card.wait_for_function("window.__atlas && window.__atlas.probe(0, 0).loaded", timeout=30000)
    check(f"{tag}: в карточке работает атлас", card.locator("#atlasOv").count() == 1)
    card.close()

    page.wait_for_function("window.__live.finished()", timeout=400000)
    time.sleep(1.5)
    check(f"{tag}: после готовности страница не уходит, пока смотрят снимок",
          page.locator("#live-done").is_visible() and page.locator("#live").count() == 1)
    if shots and full:
        page.screenshot(path=str(shots / f"{tag}_done.png"))
    page.click("#live-open")
    page.wait_for_selector(".tile", timeout=20000)
    check(f"{tag}: кнопка открывает результаты прогона", page.locator("#live").count() == 0)
    check(f"{tag}: без ошибок JS", not errors, "; ".join(errors)[:300])


def phone(ctx, base, rid, shots):
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/runs/{rid}")
    page.wait_for_function("document.querySelectorAll('#live-feed li[data-n]').length >= 3", timeout=90000)
    check("телефон: без горизонтального переполнения", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
    page.locator("#live-feed li[data-n] button").nth(1).tap()
    page.wait_for_function("document.getElementById('peek-img').naturalWidth > 0", timeout=20000)
    time.sleep(1.0)
    box = page.locator("#peek").bounding_box()
    check("телефон: после касания просмотр прокручен на экран", box is not None and -5 <= box["y"] < 844 * 0.6, str(box))
    if shots:
        page.screenshot(path=str(shots / "phone_peek.png"))
    check("телефон: без ошибок JS", not errors, "; ".join(errors)[:300])
    page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--shots", default="")
    ap.add_argument("--engines", default="chromium,firefox,webkit")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        for i, engine in enumerate(a.engines.split(",")):
            full = i == 0
            rid = start_run(base, {"dataset": "train", "mode": "all"} if full else {"dataset": "train", "mode": "sample", "n": "40"})
            print(f"{engine}: прогон {rid}")
            browser = (p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--lang=ru"]) if engine == "chromium"
                       else getattr(p, engine).launch())
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1.5, locale="ru-RU")
            if engine == "chromium":
                pctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True, locale="ru-RU")
                phone(pctx, base, rid, shots)
            desktop(ctx.new_page(), base, rid, engine, shots, full)
            browser.close()
    print(f"итого: {'всё прошло' if not FAILS else 'не прошло ' + str(len(FAILS))}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
