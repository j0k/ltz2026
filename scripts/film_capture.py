# -*- coding: utf-8 -*-
"""Съёмка кадров для ролика о стенде DXA QC: настоящие страницы и состояния через Playwright.

    python scripts/film_capture.py RUN_ID   ->  films/service/assets/*.png и films/service/meta.json

RUN_ID — прогон обучающего набора целиком (нужны разметка экспертов и снимки с нарушениями).
Наведение и клики делаются мышью по карте зон, касание — в мобильном контексте, голосовой вопрос
распознаётся настоящим /api/stt по записи webm. meta.json хранит координаты для действий курсора
и цифры для текста озвучки.
"""
from __future__ import annotations

import base64
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

BASE = os.environ.get("FILM_BASE", "https://ltz2026.ru")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "films", "service")
ASSETS = os.path.join(OUT, "assets")
VW, VH = 1920, 854
CHROME = os.environ.get("FILM_CHROME") or sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))[-1]
QUESTION = "Покажи гребни подвздошных костей."

meta: dict = {"shots": {}}


def get(path: str) -> bytes:
    return urllib.request.urlopen(BASE + path, timeout=180).read()


def box(loc) -> list[int]:
    b = loc.bounding_box()
    return [round(b["x"]), round(b["y"]), round(b["width"]), round(b["height"])]


def pt(x, y) -> list[int]:
    return [round(x), round(y), 0, 0]


def scroll_to(page, loc, offset=20):
    loc.first.evaluate("(el, off) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - off)", offset)
    page.wait_for_timeout(400)


def shot(page, name, **boxes):
    page.screenshot(path=os.path.join(ASSETS, name))
    meta["shots"][name] = boxes
    print("кадр", name, boxes, flush=True)


def open_card(page, run_id, key):
    page.goto(f"{BASE}/runs/{run_id}/images/{key}", wait_until="networkidle")
    # у canvas по умолчанию ширина 300: ждём, пока страница выставит размер карты зон (около 1000 px)
    page.wait_for_function("document.getElementById('atlasOv') && document.getElementById('atlasOv').width > 400")
    page.wait_for_function("!document.getElementById('bMic').hidden")


_hits: dict = {}


def region_point(run_id, row, key):
    """Точка в глубине зоны. Точка у края не годится: click приходит с целыми координатами,
    сдвиг меньше пикселя экрана выносит её за границу, и страница видит пустое место."""
    reg = next(g for g in row["regions"] if g["key"] == key)
    if row["key"] not in _hits:
        _hits[row["key"]] = np.array(Image.open(io.BytesIO(get(f"/runs/{run_id}/files/{row['hit_png']}"))))
    rgb = _hits[row["key"]]
    code = reg["id"] * 20
    m = (rgb[..., 0] == code) & (rgb[..., 1] == code)  # сама анатомическая зона, а не только область захвата
    if m.sum() < 30:
        m = rgb[..., 0] == code
    while True:  # сжимаем маску, пока от неё что-то остаётся
        e = m.copy()
        e[1:, :] &= m[:-1, :]
        e[:-1, :] &= m[1:, :]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        if e.sum() < 5:
            break
        m = e
    ys, xs = np.nonzero(m)
    i = int(np.argmin((ys - ys.mean()) ** 2 + (xs - xs.mean()) ** 2))
    return int(xs[i]), int(ys[i]), rgb.shape[1], rgb.shape[0]


def canvas_xy(page, row, run_id, key):
    px, py, W, H = region_point(run_id, row, key)
    b = page.locator("#atlasOv").bounding_box()
    return b["x"] + px * b["width"] / W, b["y"] + py * b["height"] / H


def main(run_id: str):
    os.makedirs(ASSETS, exist_ok=True)
    man = json.loads(get(f"/runs/{run_id}/files/manifest.json"))
    rows = [r for r in man["rows"] if r["processing_status"] == "Success"]
    spine = [r for r in rows if r["anatomical_region"] == "lumbar_spine" and r.get("regions")]
    agreed = [r for r in spine if "artifact" in r["violation_list"] and r.get("expert") and "artifact" in r["expert"]["types"]]
    art = (agreed or [r for r in spine if "artifact" in r["violation_list"]])[0]
    hips = [r for r in rows if r["anatomical_region"] == "hip_left" and r.get("regions")]
    hip = next((r for r in hips if r["study_key"] == art["study_key"]), hips[0])
    lvl = next(k for k in ("L3", "L2", "L4", "L1") if any(g["key"] == k for g in art["regions"]))
    meta.update(run_id=run_id, summary=man["summary"], evaluation=man.get("evaluation"),
                art=dict(key=art["key"], violations=art["violation_list"], expert=art.get("expert"), level=lvl,
                         regions={g["key"]: g["text"] for g in art["regions"]}),
                hip=dict(key=hip["key"], regions={g["key"]: g["text"] for g in hip["regions"]}))

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, env={**os.environ, "LANGUAGE": "ru"},
                                    args=["--no-sandbox", "--lang=ru", "--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": VW, "height": VH}, locale="ru-RU")
        page = ctx.new_page()

        # главная: что умеет сервис и загрузка
        page.goto(BASE + "/", wait_until="networkidle")
        feats = page.locator("#about")
        upload = page.locator("form.upload")
        shot(page, "01_index.png", features=box(feats), upload=box(upload), file=box(page.locator("input[type=file]")))

        # наборы организатора: весь обучающий набор
        ds = page.locator("#check")
        scroll_to(page, ds, 60)
        train = page.locator('form[action="/runs/dataset"]', has=page.locator("input[name=dataset][value=train]"))
        radio = train.locator("input[name=mode][value=all]")
        radio.check()
        shot(page, "02_datasets.png", train=box(train), all=box(radio), submit=box(train.locator("button[type=submit]")))

        # прогон: итоги и выгрузки
        page.goto(f"{BASE}/runs/{run_id}", wait_until="networkidle")
        shot(page, "03_run.png", kpis=box(page.locator("main div.grid").first), csv=box(page.locator("a.btn", has_text="Таблица csv")),
             zip=box(page.locator("a.btn", has_text="Архив разметки")))

        # инфографика
        scroll_to(page, page.locator("h2", has_text="Инфографика прогона"), 10)
        shot(page, "04_charts.png", regions=box(page.locator("#chart-regions")), violations=box(page.locator("#chart-violations")))

        # порог наклона оси: по умолчанию и сдвинутый
        ang = page.locator(".viz-card", has=page.locator("#chart-angle"))
        scroll_to(page, ang, 20)
        meta["thr_default"] = page.locator("#thr-kpis").inner_text()
        shot(page, "05_threshold.png", card=box(ang), slider=box(page.locator("#thr")),
             confusion=box(page.locator(".viz-card", has=page.locator("#chart-confusion"))))
        page.locator("#thr").evaluate("el => { el.value = 3; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }")
        page.wait_for_timeout(400)
        meta["thr_3"] = page.locator("#thr-kpis").inner_text()
        sl = box(page.locator("#thr"))
        shot(page, "06_threshold_3.png", slider=sl, thumb=pt(sl[0] + sl[2] * (3 - 1) / 11, sl[1] + sl[3] / 2),
             kpis=box(page.locator("#thr-kpis")), chart=box(page.locator("#chart-angle")))

        # таблица снимков
        scroll_to(page, page.locator("#results"), 70)
        shot(page, "07_table.png", thumb=box(page.locator("#results img.thumb").first),
             expert=box(page.locator("#results th", has_text="Эксперты")), verdict=box(page.locator("#results th", has_text="Вердикт")))

        # карточка снимка с нарушением: итог, позвонок, предмет
        open_card(page, run_id, art["key"])
        x, y = canvas_xy(page, art, run_id, "verdict")
        page.mouse.click(x, y)
        page.wait_for_timeout(400)
        shot(page, "08_card_verdict.png", badge=pt(x, y), panel=box(page.locator(".ap")), stage=box(page.locator(".stage")))
        x, y = canvas_xy(page, art, run_id, lvl)
        page.mouse.move(x, y, steps=8)
        page.wait_for_timeout(400)
        shot(page, "09_card_level.png", level=pt(x, y), panel=box(page.locator(".ap")))
        x, y = canvas_xy(page, art, run_id, "artifact")
        page.mouse.click(x, y)
        page.wait_for_timeout(400)
        shot(page, "10_card_artifact.png", artifact=pt(x, y), panel=box(page.locator(".ap")), sound=box(page.locator("#bSound")))

        # голосовой вопрос: запись webm, настоящее распознавание, выбор зоны тем же сопоставлением, что у кнопки
        wav = get("/api/tts?" + urllib.parse.urlencode({"text": QUESTION}))
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "q.wav"), "wb") as f:
                f.write(wav)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", os.path.join(td, "q.wav"), "-c:a", "libopus",
                            os.path.join(td, "q.webm")], check=True)
            with open(os.path.join(td, "q.webm"), "rb") as f:
                webm = base64.b64encode(f.read()).decode()
        page.mouse.move(4, 4)
        heard = page.evaluate("""async (b64) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const fd = new FormData(); fd.append('file', new Blob([bytes], {type: 'audio/webm'}), 'question.webm');
            const r = await fetch('/api/stt', {method: 'POST', body: fd}); return (await r.json()).text; }""", webm)
        rid = page.evaluate("t => { const m = window.__atlas.match(t); return m.region ? m.region.id : 0; }", heard)
        meta["question"] = dict(asked=QUESTION, heard=heard, region_id=rid)
        chip = page.locator(f'#chips .chip[data-id="{rid}"]')
        chip.click()
        page.evaluate("t => { document.getElementById('vStat').textContent = 'вы спросили: «' + t + '»'; }", heard)
        page.mouse.move(4, 4)
        page.wait_for_timeout(400)
        shot(page, "11_voice.png", mic=box(page.locator("#bMic")), vstat=box(page.locator("#vStat")), chip=box(chip),
             tour=box(page.locator("#bTour")), panel=box(page.locator(".ap")))

        # бедро: шейка
        open_card(page, run_id, hip["key"])
        x, y = canvas_xy(page, hip, run_id, "neck")
        page.mouse.move(x, y, steps=8)
        page.wait_for_timeout(400)
        shot(page, "12_hip.png", neck=pt(x, y), panel=box(page.locator(".ap")))

        # телефон: касание пальцем
        mctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ru-RU")
        mp = mctx.new_page()
        open_card(mp, run_id, art["key"])
        scroll_to(mp, mp.locator(".atlas"), 8)
        tkey = "iliac"
        tx, ty = canvas_xy(mp, art, run_id, tkey)
        # касание пальцем: touchstart, touchend и click, как на телефоне (жест через CDP click не порождал)
        mp.touchscreen.tap(tx, ty)
        mp.wait_for_timeout(500)
        raw = mp.screenshot()
        ph = Image.open(io.BytesIO(raw)).convert("RGB")
        k = 790 / ph.height
        ph = ph.resize((round(ph.width * k), 790), Image.LANCZOS)
        comp = Image.new("RGB", (VW, VH), (18, 20, 24))
        x0, y0 = (VW - ph.width) // 2, (VH - ph.height) // 2
        d = ImageDraw.Draw(comp)
        d.rounded_rectangle([x0 - 14, y0 - 14, x0 + ph.width + 14, y0 + ph.height + 14], radius=38, fill=(44, 48, 56))
        m = Image.new("L", ph.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, ph.width - 1, ph.height - 1], radius=26, fill=255)
        comp.paste(ph, (x0, y0), m)
        comp.save(os.path.join(ASSETS, "13_phone.png"))
        tap = pt(x0 + tx * 2 * k, y0 + ty * 2 * k)
        meta["shots"]["13_phone.png"] = dict(tap=tap, phone=[x0, y0, ph.width, ph.height])
        print("кадр 13_phone.png", tap, flush=True)
        mctx.close()

        # API
        page.goto(BASE + "/docs", wait_until="networkidle")
        page.wait_for_selector(".opblock", timeout=60000)
        op = lambda path: page.locator(".opblock", has=page.locator(".opblock-summary-path", has_text=path)).first
        scroll_to(page, op("/api/health"), 140)
        shot(page, "14_api.png", batch=box(op("/api/batch")), stt=box(op("/api/stt")), tts=box(op("/api/tts")))

        # честные метрики
        page.goto(BASE + "/", wait_until="networkidle")
        note = page.locator("#accuracy")
        scroll_to(page, note, 180)
        shot(page, "15_metrics.png", note=box(note), table=box(note.locator("table")))
        browser.close()

    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("meta:", json.dumps({k: meta[k] for k in ("question", "thr_default", "thr_3")}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
