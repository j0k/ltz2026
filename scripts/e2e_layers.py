# -*- coding: utf-8 -*-
"""Проверка слоёв атласа и лупы в браузерах: переключение слоёв меняет рисунок и запоминается,
лупа ходит за мышью, пальцем и стрелками, увеличение меняет картинку в линзе, на телефоне нет переполнения.

    python scripts/e2e_layers.py http://127.0.0.1:8765 /runs/RUN/images/KEY --shots /tmp/e2e_layers

Ничего не создаёт на стенде: только открывает карточку снимка.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = os.environ.get("FILM_CHROME") or sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))[-1]
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def changed(a, b, thr=30) -> int:
    return sum(1 for i in range(0, len(a), 3) if max(abs(a[i] - b[i]), abs(a[i + 1] - b[i + 1]), abs(a[i + 2] - b[i + 2])) > thr)


def open_card(page, url):
    page.goto(url)
    page.wait_for_function("window.__atlas && window.__atlas.layers().ready && window.__atlas.probe(0, 0).loaded", timeout=40000)


def stage_centre(page):
    b = page.locator("#stage").bounding_box()
    return b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.45, b


def desktop_checks(page, url, tag, shots: Path | None):
    open_card(page, url)
    page.evaluate("localStorage.removeItem('dxaqc-layers')")
    page.reload()
    open_card(page, url)
    s0 = page.evaluate("window.__atlas.snapshot()")

    page.click("[data-layer=labels]")
    s1 = page.evaluate("window.__atlas.snapshot()")
    check(f"{tag}: подписи выключаются", changed(s0, s1) > 15 and page.get_attribute("[data-layer=labels]", "aria-pressed") == "false",
          f"изменилось {changed(s0, s1)} клеток")
    page.click("[data-layer=image]")
    s2 = page.evaluate("window.__atlas.snapshot()")
    check(f"{tag}: снимок выключается", changed(s1, s2) > 60, f"изменилось {changed(s1, s2)}")
    if shots:
        page.screenshot(path=str(shots / f"{tag}_layers_off.png"))

    page.reload()
    open_card(page, url)
    st = page.evaluate("window.__atlas.layers().on")
    check(f"{tag}: выбор слоёв запоминается", st["labels"] is False and st["image"] is False, str(st))
    page.click("[data-layer=labels]")
    page.click("[data-layer=image]")
    s3 = page.evaluate("window.__atlas.snapshot()")
    check(f"{tag}: все слои снова дают исходный рисунок", changed(s0, s3, thr=4) == 0, f"отличий {changed(s0, s3, thr=4)}")

    zone = None
    b = page.locator("#stage").bounding_box()
    for fy in (0.3, 0.45, 0.6):
        for fx in (0.35, 0.4, 0.45, 0.5, 0.55):
            x, y = b["x"] + b["width"] * fx, b["y"] + b["height"] * fy
            if page.evaluate("([x, y]) => window.__atlas.probe(x, y).id", [x, y]):
                zone = (x, y)
                break
        if zone:
            break
    check(f"{tag}: зоны под указателем работают поверх слоёв", zone is not None)

    page.click("#bLoupe")
    check(f"{tag}: кнопки увеличения появились", page.locator("#zoomBar").is_visible())
    x, y = zone or stage_centre(page)[:2]
    page.mouse.move(x, y)
    page.mouse.move(x + 3, y + 2)
    st = page.evaluate("window.__atlas.lensStats()")
    check(f"{tag}: линза показывает рисунок", not st["hidden"] and st["std"] > 4, str(st))
    page.click("[data-zoom='2']")
    page.mouse.move(x, y)
    a2 = page.evaluate("window.__atlas.lensStats()")
    page.click("[data-zoom='6']")
    page.mouse.move(x + 1, y)
    a6 = page.evaluate("window.__atlas.lensStats()")
    check(f"{tag}: увеличение меняет картинку в линзе", not a6["hidden"] and abs(a2["sum"] - a6["sum"]) > 1, f"{a2} / {a6}")
    if shots:
        page.screenshot(path=str(shots / f"{tag}_loupe.png"))

    page.mouse.move(5, 5)
    check(f"{tag}: линза прячется, когда мышь ушла", page.evaluate("window.__atlas.loupe().hidden"))
    page.focus("#stage")
    page.keyboard.press("ArrowRight")
    x0 = page.evaluate("window.__atlas.loupe().x")
    for _ in range(3):
        page.keyboard.press("ArrowRight")
    x1 = page.evaluate("window.__atlas.loupe().x")
    check(f"{tag}: стрелки двигают лупу", abs((x1 - x0) - 30) < 0.5 and not page.evaluate("window.__atlas.loupe().hidden"), f"{x0} → {x1}")
    page.keyboard.press("-")
    check(f"{tag}: минус уменьшает увеличение", page.evaluate("window.__atlas.loupe().zoom") == 4)
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    check(f"{tag}: Escape выключает лупу", page.evaluate("!window.__atlas.loupe().on") and page.get_attribute("#bLoupe", "aria-pressed") == "false")


def phone_checks(ctx, page, url, shots: Path | None):
    open_card(page, url)
    check("телефон: без горизонтального переполнения", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
    page.locator("#bLoupe").tap()
    x, y, b = stage_centre(page)
    cdp = ctx.new_cdp_session(page)
    pt = lambda xx, yy: [{"x": xx, "y": yy, "radiusX": 4, "radiusY": 4, "force": 1, "id": 1}]
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt(x, y)})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": pt(x + 12, y + 6)})
    st = page.evaluate("window.__atlas.loupe()")
    lb = page.locator("#loupe").bounding_box()
    check("телефон: линза видна, пока палец на рисунке", not st["hidden"] and st["shown"], str(st))
    check("телефон: линза над пальцем, а не под ним", lb is not None and lb["y"] + lb["height"] <= y + 6, str(lb))
    if shots:
        page.screenshot(path=str(shots / "phone_loupe.png"))
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    check("телефон: линза прячется, когда палец отпущен", page.evaluate("window.__atlas.loupe().hidden"))
    page.locator("[data-layer=labels]").tap()
    check("телефон: слой переключается касанием", page.get_attribute("[data-layer=labels]", "aria-pressed") == "false")
    page.locator("[data-layer=labels]").tap()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("card", help="путь карточки снимка: /runs/RUN/images/KEY")
    ap.add_argument("--shots", default="")
    ap.add_argument("--engines", default="chromium,firefox,webkit")
    a = ap.parse_args()
    url = a.base.rstrip("/") + a.card
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        for engine in a.engines.split(","):
            browser = (p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--lang=ru"]) if engine == "chromium"
                       else getattr(p, engine).launch())
            ctx = browser.new_context(viewport={"width": 1280, "height": 860}, device_scale_factor=1.5, locale="ru-RU")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            desktop_checks(page, url, engine, shots if engine == "chromium" else None)
            check(f"{engine}: без ошибок JS", not errors, "; ".join(errors)[:300])
            if engine == "chromium":
                pctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True, locale="ru-RU")
                phone = pctx.new_page()
                perr = []
                phone.on("pageerror", lambda e: perr.append(str(e)))
                phone_checks(pctx, phone, url, shots)
                check("телефон: без ошибок JS", not perr, "; ".join(perr)[:300])
            browser.close()
    print(f"итого: {'всё прошло' if not FAILS else 'не прошло ' + str(len(FAILS))}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
