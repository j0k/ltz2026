# -*- coding: utf-8 -*-
"""Сквозная проверка стенда в браузере (Playwright): главная на десктопе и телефоне, клавиатура, загрузка архива,
запуск набора, страница прогона (плитки, боксплоты, интервалы), карточка снимка (выбор зоны).

    python scripts/e2e_web.py http://127.0.0.1:8765 --write --shots /tmp/e2e

Без --write проверяет только чтение и ничего не создаёт на стенде. Код возврата 1, если что-то не прошло.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CHROME = os.environ.get("FILM_CHROME") or sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))[-1]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, bool(ok), detail))
    print(("  ok   " if ok else "  FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def no_overflow(page) -> tuple[bool, str]:
    # сравниваем с заданной шириной экрана: в мобильном режиме window.innerWidth растёт вслед за содержимым
    screen = page.viewport_size["width"]
    doc = page.evaluate("document.documentElement.scrollWidth")
    return doc <= screen, f"ширина документа {doc} при экране {screen}"


def wait_run_done(page, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page.locator(".tile").count():
            return True
        if page.locator(".pill.bad").count() and "ошибка" in page.locator("main").inner_text():
            return False
        page.wait_for_timeout(1500)
        page.reload(wait_until="networkidle")
    return False


def check_index(page, base, label):
    page.goto(base + "/", wait_until="networkidle")
    check(f"{label}: главная открывается", page.locator("h1").inner_text().startswith("Контроль качества"))
    ok, d = no_overflow(page)
    check(f"{label}: нет горизонтальной прокрутки", ok, d)
    check(f"{label}: все блоки на месте", all(page.locator(f"#{s}").count() == 1 for s in ("upload", "about", "check", "runs", "accuracy")))
    check(f"{label}: зона загрузки и кнопка видны", page.locator("form.upload label[for=files]").is_visible() and page.locator("form.upload button").is_visible())
    sets = page.locator('form[action="/runs/dataset"]').count()
    check(f"{label}: формы наборов организатора", sets >= 1, f"форм: {sets}")


def pick_zone(page) -> tuple[float, float] | None:
    """Точка внутри зоны на карте атласа: код зоны совпадает у точки и у соседей в 4 px."""
    b = page.locator("#atlasOv").bounding_box()
    step = 10
    for yy in range(int(b["y"] + b["height"] * 0.2), int(b["y"] + b["height"] * 0.9), step):
        for xx in range(int(b["x"] + b["width"] * 0.3), int(b["x"] + b["width"] * 0.7), step):
            ids = page.evaluate("""([x, y]) => [[0,0],[4,0],[-4,0],[0,4],[0,-4]].map(([dx, dy]) => window.__atlas.probe(x + dx, y + dy).id)""", [xx, yy])
            if ids[0] and len(set(ids)) == 1:
                return xx, yy
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--write", action="store_true", help="создавать прогоны: загрузка архива и запуск набора")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    shots = a.shots
    if shots:
        os.makedirs(shots, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--lang=ru"])
        errors: list[str] = []

        desk = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ru-RU").new_page()
        desk.on("pageerror", lambda e: errors.append(str(e)))
        print("главная, десктоп")
        check_index(desk, base, "десктоп")
        docs = urllib.request.urlopen(base + "/docs", timeout=30).status
        check("ссылка API открывается", docs == 200 and desk.locator('header a[href="/docs"]').count() == 1)
        check("ссылка на трекер есть", desk.locator('header a[href*="/trac"]').count() == 1)
        if shots:
            desk.screenshot(path=os.path.join(shots, "index_desktop.png"), full_page=True)

        print("клавиатура")
        desk.goto(base + "/", wait_until="networkidle")
        seen = []
        for _ in range(12):
            desk.keyboard.press("Tab")
            seen.append(desk.evaluate("(document.activeElement.id || document.activeElement.tagName) + ':' + (document.activeElement.textContent || '').trim().slice(0, 12)"))
        check("Tab доходит до поля файла и кнопки «проверить»", any(s.startswith("files") for s in seen) and any("проверить" in s.lower() for s in seen), " → ".join(seen[:8]))

        small = browser.new_context(viewport={"width": 320, "height": 640}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ru-RU").new_page()
        print("главная, узкий телефон 320 px")
        check_index(small, base, "телефон 320")
        mob_ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ru-RU")
        mob = mob_ctx.new_page()
        mob.on("pageerror", lambda e: errors.append(str(e)))
        print("главная, телефон 390 px")
        check_index(mob, base, "телефон")
        if shots:
            mob.screenshot(path=os.path.join(shots, "index_phone.png"), full_page=True)

        print("пульт анализа")
        desk.goto(base + "/control", wait_until="networkidle")
        check("пульт открывается", desk.locator("h1").inner_text() == "Пульт анализа")
        check("пульт: счётчики, очередь, параметры, журнал", all(desk.locator(f"#{s}").count() == 1 for s in ("kpis", "queue", "params", "journal")))
        rows = desk.locator("#calib-table tbody tr")
        if rows.count():
            first = rows.first.locator("td")
            check("пульт: пересчёт по умолчанию совпадает с оценкой прогона", first.nth(3).inner_text() == first.nth(4).inner_text(),
                  f"F1 {first.nth(3).inner_text()} при значениях по умолчанию")
            axis_row = desk.locator('#calib-table tbody tr[data-check="наклон оси"] td')
            before = axis_row.nth(1).inner_text()
            desk.fill("#p-axis_limit_deg", "2")
            desk.locator("#p-axis_limit_deg").dispatch_event("input")
            after = axis_row.nth(1).inner_text()
            check("пульт: сдвиг допуска оси пересчитывает чувствительность", after != before and desk.locator('.prm.changed').count() == 1,
                  f"чувствительность оси {before} → {after}")
        else:
            print("  инфо: на стенде нет полного прогона обучающего набора, пересчёт метрик не проверяется")
        mob.goto(base + "/control", wait_until="networkidle")
        ok, d = no_overflow(mob)
        check("пульт на телефоне без горизонтальной прокрутки", ok, d)
        if shots:
            desk.screenshot(path=os.path.join(shots, "control_desktop.png"), full_page=True)

        if a.write:
            print("загрузка архива")
            desk.goto(base + "/", wait_until="networkidle")
            desk.set_input_files("#files", os.path.join(ROOT, "Для теста.zip"))
            desk.locator("form.upload button").click()
            desk.wait_for_url("**/runs/*", timeout=60000)
            run_url = desk.url
            check("загрузка ведёт на страницу прогона", "/runs/" in run_url, run_url.split("/runs/")[-1])
            check("после отправки видна живая панель или уже результаты", desk.locator("#live").count() + desk.locator(".tile").count() > 0)
            check("прогон загруженного архива готов", wait_run_done(desk))
            desk.locator('.tile[data-tile="bad"]').click()
            desk.wait_for_timeout(400)
            check("плитка «с нарушением» фильтрует таблицу", "Показано" in desk.locator("#shown").inner_text(), desk.locator("#shown").inner_text())
            desk.locator('.tile[data-tile="all"]').click()
            check("боксплоты построены", desk.locator("#box-grid .viz-card").count() >= 1, f"карточек {desk.locator('#box-grid .viz-card').count()}")

            print("карточка снимка")
            desk.locator('#results a[href*="/images/"]').first.click()
            desk.wait_for_load_state("networkidle")
            desk.wait_for_function("document.getElementById('atlasOv') && document.getElementById('atlasOv').width > 400", timeout=30000)
            pt = pick_zone(desk)
            if pt:
                desk.mouse.click(*pt)
                desk.wait_for_timeout(400)
            title = desk.locator("#apTitle").inner_text()
            check("клик по рисунку выбирает зону", pt is not None and not title.startswith("Наведите"), title)

            print("набор организатора")
            desk.goto(base + "/", wait_until="networkidle")
            train = desk.locator('form[action="/runs/dataset"]', has=desk.locator("input[name=dataset][value=train]"))
            if train.count():
                train.locator("input[name=mode][value=sample]").check()
                train.locator("select[name=n]").select_option("5")
                train.locator("button[type=submit]").click()
                desk.wait_for_url("**/runs/*", timeout=60000)
                rid = desk.url.rsplit("/", 1)[1]
                check("запуск набора ведёт на страницу прогона", True, rid)
                most, pct, t0 = 0, "", time.time()
                while time.time() - t0 < 120:  # смотрим, как этапы отмечаются, пока страница сама не перейдёт к результатам
                    try:
                        if desk.locator(".tile").count():
                            break
                        most = max(most, desk.locator("#live-steps li.done").count())
                        if desk.locator("#live-pct").count():
                            pct = desk.locator("#live-pct").inner_text()
                    except Exception:
                        pass
                    desk.wait_for_timeout(200)
                check("этапы отмечаются в реальном времени", most >= 3, f"больше всего пройденных этапов на панели: {most}, последний процент {pct}")
                check("прогон набора готов", wait_run_done(desk))
                check("интервалы по разметке экспертов построены", desk.locator("#ci-grid .viz-card").count() == 3)
                desk.goto(base + "/", wait_until="networkidle")
                item = desk.locator("#runs tr", has=desk.locator(f'a[href="/runs/{rid}"]'))
                check("новый прогон в списке главной с csv", item.count() == 1 and item.locator('a[href$="results.csv"]').count() == 1,
                      item.inner_text().replace("\n", " ") if item.count() else "")
                ok, d = no_overflow(mob)
                mob.goto(base + f"/runs/{rid}", wait_until="networkidle")
                ok, d = no_overflow(mob)
                print(f"  инфо: страница прогона на телефоне — {d}")
            else:
                check("форма обучающего набора есть", False)

        check("нет ошибок JavaScript", not errors, "; ".join(errors[:3]))
        browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\nитого: {len(results) - len(failed)} из {len(results)} проверок прошли")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
