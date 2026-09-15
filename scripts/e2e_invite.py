# -*- coding: utf-8 -*-
"""Сквозная проверка инвайт-ссылок в браузере: админ создаёт ссылку, новичок регистрируется по ней и попадает в админку.

    python scripts/e2e_invite.py http://127.0.0.1:8765 ADMIN PASSWORD --shots /tmp/e2e_invite

Ссылку можно отозвать после проверки (--revoke) — так сценарий безопасно гоняется на стенде без регистрации (--no-register).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import secrets
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = os.environ.get("FILM_CHROME") or sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))[-1]
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def no_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("admin")
    ap.add_argument("password")
    ap.add_argument("--shots", default="/tmp/e2e_invite")
    ap.add_argument("--no-register", action="store_true", help="не регистрировать новичка, только показать страницу приглашения")
    ap.add_argument("--revoke", action="store_true", help="отозвать созданную ссылку в конце")
    a = ap.parse_args()
    base, shots = a.base.rstrip("/"), Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--lang=ru"])
        admin = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page = admin.new_page()
        page.goto(base + "/login?next=/admin")
        page.fill("#login", a.admin)
        page.fill("#password", a.password)
        page.click("button[type=submit]")
        page.wait_for_url(re.compile(r"/admin"))
        check("админ вошёл и видит раздел приглашений", page.locator("#invites h2").is_visible())

        page.select_option("#inv-role", "admin")
        page.select_option("#inv-hours", "1")
        page.fill("#inv-note", "проверка инвайт-ссылки")
        page.click("#invites button:has-text('Создать ссылку')")
        page.wait_for_selector("#inviteUrl")
        url = page.input_value("#inviteUrl")
        check("ссылка показана", "/invite/" in url, url[:60])
        token = url.split("/invite/")[1]
        page.click("#copyInvite")
        check("кнопка копирования отвечает", page.locator("#copyInvite").inner_text() == "Скопировано")
        page.screenshot(path=str(shots / "01_admin_invite_created.png"), full_page=False)

        guest = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
        g = guest.new_page()
        g.goto(f"{base}/invite/{token}")
        check("страница приглашения: роль и выдавший", "Доступ админа" in g.content() and a.admin in g.content())
        check("страница приглашения без переполнения на телефоне", no_overflow(g))
        g.screenshot(path=str(shots / "02_invite_mobile.png"), full_page=True)

        if not a.no_register:
            login = "inv" + secrets.token_hex(3)
            pw = secrets.token_urlsafe(12)
            g.fill("#login", login)
            g.fill("#password", pw)
            g.fill("#password2", pw)
            g.click("button:has-text('Зарегистрироваться и принять')")
            g.wait_for_url(re.compile(r"/admin"))
            check("новичок попал в админку", g.locator("h1", has_text="Админка").is_visible())
            check("админка без переполнения на телефоне", no_overflow(g))
            g.screenshot(path=str(shots / "03_admin_mobile.png"), full_page=False)

            again = browser.new_context().new_page()
            again.goto(f"{base}/invite/{token}")
            check("повторно ссылка не работает", "уже использовано" in again.content().lower())

            page.goto(base + "/admin#invites")
            row = page.locator("#invites tbody tr").first
            check("в списке: использована и кем", "использована" in row.inner_text() and login in row.inner_text())
            page.screenshot(path=str(shots / "04_admin_invites_used.png"), full_page=False)

        if a.revoke:
            page.goto(base + "/admin#invites")
            btn = page.locator("#invites tbody tr").first.locator("button:has-text('Отозвать')")
            if btn.count():
                btn.click()
                page.wait_for_load_state()
            gone = browser.new_context().new_page()
            gone.goto(f"{base}/invite/{token}")
            check("отозванная ссылка не работает", "отозвано" in gone.content())
        browser.close()

    print(f"итого: {'всё прошло' if not FAILS else 'не прошло ' + str(len(FAILS))}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
