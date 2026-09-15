# -*- coding: utf-8 -*-
"""Собирает web/index.html — штурвал команды Codellake для веб-шаринга.

Данные берутся из живого codellake instances.json, отсчёт до дедлайна считает браузер.
"""
import json
import os

INST = {i["cwd"]: i for i in json.load(open("/home/jk/.codellake/instances.json"))["instances"]}
LTZ = INST.get("/home/jk/exp/LTZ2026", {"model": "opus", "started": "2026-09-10T15:53:53"})
FLEET = [i["cwd"].rstrip("/").split("/")[-1].split(".")[0]
         for i in INST.values() if i["cwd"] != "/home/jk/exp/LTZ2026"]
WATCH = LTZ["started"][8:10] + "." + LTZ["started"][5:7]

CREW = [
    dict(id="cap", name="Юрий Коноплёв", tag="@bimodaling", role="курс", helm=False, spoke=1,
         lines=["Ставит курс: какую задачу берём и что показываем на защите.",
                "Владелец репозитория j0k/ltz2026."]),
    dict(id="alex", name="Алексей", tag="второй на поле", role="борт", helm=False, spoke=3,
         lines=["Роль пока не закреплена: модель, бэкенд или демо.",
                "Свободная рукоять на штурвале."]),
    dict(id="claude", name="Claude", tag=f"codellake · инстанс LTZ · {LTZ['model']}",
         role="у руля", helm=True, spoke=5,
         lines=["Разбор десяти городских задач, инфографика, репозиторий, план на две недели.",
                f"На вахте с {WATCH}, рядом вахты {' и '.join(FLEET) if FLEET else 'нет'}."]),
]


def card(m):
    lines = "".join(f"<p>{ln}</p>" for ln in m["lines"])
    return f'''<article class="card{' helm' if m['helm'] else ''}" data-spoke="{m['spoke']}" tabindex="0">
      <div class="card-top"><h2>{m['name']}</h2><span class="pill">{m['role']}</span></div>
      <div class="tag">{m['tag']}</div>
      {lines}
    </article>'''


def spokes():
    out = []
    for k in range(6):
        ang = k * 60 + 30
        out.append(f'<line class="spoke" data-spoke="{k}" x1="0" y1="0" x2="0" y2="-150" '
                   f'transform="rotate({ang})"/>')
    return "".join(out)


def handles():
    out = []
    for k in range(6):
        ang = k * 60 + 30
        out.append(f'<g class="handle" data-spoke="{k}" transform="rotate({ang}) translate(0,-155)">'
                   f'<rect x="-7" y="-32" width="14" height="32" rx="7"/>'
                   f'<circle cx="0" cy="-30" r="8.5"/></g>')
    return "".join(out)


HTML = f'''<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codellake — команда у штурвала</title>
<style>
:root{{
  color-scheme: light;
  --bg:#f7f6f3; --card:#ffffff; --ink:#0b0b0b; --ink2:#52514e; --ink3:#8a8983;
  --blue:#2a78d6; --deep:#104281; --mid:#1c5cab; --pale:#cde2fb; --accent:#eb6834;
  --pill:#eef4fd; --pill-helm:#fdece3; --line:#c9d4e4; --shadow:0 1px 2px rgba(11,11,11,.06),0 8px 24px rgba(11,11,11,.06);
}}
@media (prefers-color-scheme: dark){{
  :root{{
    color-scheme: dark;
    --bg:#12140f; --card:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --ink3:#8f8e85;
    --blue:#3987e5; --deep:#9ec5f4; --mid:#5598e7; --pale:#1c5cab; --accent:#d95926;
    --pill:#16243a; --pill-helm:#33190e; --line:#2f3a49; --shadow:none;
  }}
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 -apple-system,Segoe UI,Roboto,"Noto Sans",sans-serif;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1180px;margin:0 auto;padding:40px 20px 64px}}
header{{text-align:center;margin-bottom:8px}}
h1{{margin:0;font-size:clamp(30px,6vw,46px);letter-spacing:.02em;font-weight:800}}
.sub{{color:var(--ink2);margin-top:6px;font-size:14px}}
.countdown{{display:inline-flex;align-items:center;gap:8px;margin-top:14px;
  background:var(--pill-helm);color:var(--accent);border-radius:999px;
  padding:7px 16px;font-weight:700;font-size:13px}}
.countdown .dot{{width:7px;height:7px;border-radius:50%;background:var(--accent);
  animation:pulse 2s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.stage{{display:grid;gap:26px;align-items:center;margin-top:26px;
  grid-template-columns:1fr minmax(320px,440px) 1fr;
  grid-template-areas:"cap wheel alex" ". claude .";}}
.card{{grid-area:cap;background:var(--card);border-radius:14px;padding:18px 20px;
  box-shadow:var(--shadow);border-left:3px solid var(--blue);
  transition:transform .18s ease, box-shadow .18s ease;outline:none}}
.card:nth-of-type(2){{grid-area:alex}}
.card:nth-of-type(3){{grid-area:claude;max-width:440px;justify-self:center}}
.card.helm{{border-left-color:var(--accent)}}
.card:hover,.card:focus-visible{{transform:translateY(-3px)}}
.card:focus-visible{{box-shadow:0 0 0 3px var(--pale)}}
.card-top{{display:flex;align-items:center;justify-content:space-between;gap:12px}}
h2{{margin:0;font-size:19px;font-weight:800}}
.pill{{background:var(--pill);color:var(--deep);border-radius:999px;padding:4px 11px;
  font-size:11px;font-weight:700;white-space:nowrap}}
.helm .pill{{background:var(--pill-helm);color:var(--accent)}}
.tag{{color:var(--ink3);font-size:12px;margin:4px 0 10px;word-break:break-word}}
.card p{{margin:6px 0;color:var(--ink2);font-size:13.5px}}
.wheel{{grid-area:wheel;justify-self:center;width:100%;max-width:440px}}
svg{{width:100%;height:auto;display:block}}
#rotor{{transform-origin:0 0;animation:spin 90s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@media (prefers-reduced-motion: reduce){{#rotor{{animation:none}} .countdown .dot{{animation:none}}}}
.rim{{fill:none;stroke:var(--deep);stroke-width:15}}
.rim-in{{fill:none;stroke:var(--pale);stroke-width:3}}
.spoke{{stroke:var(--blue);stroke-width:9;stroke-linecap:round;transition:stroke .2s ease}}
.handle rect,.handle circle{{fill:var(--mid);transition:fill .2s ease}}
.spoke.lit{{stroke:var(--accent)}}
.handle.lit rect,.handle.lit circle{{fill:var(--accent)}}
.hub-out{{fill:var(--deep)}} .hub-in{{fill:var(--bg)}}
.hub-t{{fill:var(--deep);font-weight:800;font-size:17px;text-anchor:middle}}
.hub-s{{fill:var(--ink2);font-size:9.5px;text-anchor:middle}}
footer{{margin-top:34px;text-align:center;color:var(--ink3);font-size:12.5px;line-height:1.8}}
@media (max-width:860px){{
  .stage{{grid-template-columns:1fr;grid-template-areas:"wheel" "cap" "alex" "claude";}}
  .card:nth-of-type(3){{max-width:none}}
}}
</style></head>
<body><div class="wrap">
<header>
  <h1>CODELLAKE</h1>
  <div class="sub">трое на поле · ЛЦТ 2026 · штурвал стендапа</div>
  <div class="countdown"><span class="dot"></span><span id="cd">считаем…</span></div>
</header>

<div class="stage">
  {card(CREW[0])}
  {card(CREW[1])}
  <div class="wheel">
    <svg viewBox="-210 -210 420 420" role="img" aria-label="Штурвал команды: капитан, борт и агент у руля">
      <g id="rotor">
        {spokes()}
        <circle class="rim" cx="0" cy="0" r="150"/>
        <circle class="rim-in" cx="0" cy="0" r="139"/>
        {handles()}
      </g>
      <circle class="hub-out" cx="0" cy="0" r="60"/>
      <circle class="hub-in" cx="0" cy="0" r="50"/>
      <text class="hub-t" x="0" y="-4">ЛЦТ</text>
      <text class="hub-s" x="0" y="12">заявка</text>
      <text class="hub-s" x="0" y="26" id="hubdays">…</text>
    </svg>
  </div>
  {card(CREW[2])}
</div>

<footer>
  заявки до 14 сентября · разработка 15–29 сентября · защита 23 октября · награждение 30 октября<br>
  страница собрана из живых данных codellake instances.json
</footer>
</div>
<script>
const DEADLINE = new Date("2026-09-14T23:59:59+03:00");
function tick(){{
  const ms = DEADLINE - new Date();
  const el = document.getElementById("cd"), hub = document.getElementById("hubdays");
  if (ms <= 0) {{ el.textContent = "приём заявок закрыт"; hub.textContent = "закрыт"; return; }}
  const d = Math.floor(ms/86400000), h = Math.floor(ms/3600000)%24, m = Math.floor(ms/60000)%60;
  el.textContent = `до подачи заявки ${{d}} д ${{h}} ч ${{m}} мин`;
  hub.textContent = d + " дн.";
}}
tick(); setInterval(tick, 30000);

document.querySelectorAll(".card").forEach(cardEl => {{
  const k = cardEl.dataset.spoke;
  const parts = () => [...document.querySelectorAll(`[data-spoke="${{k}}"]`)].filter(n => n.tagName !== "ARTICLE");
  const on  = () => parts().forEach(n => n.classList.add("lit"));
  const off = () => parts().forEach(n => n.classList.remove("lit"));
  cardEl.addEventListener("mouseenter", on);
  cardEl.addEventListener("mouseleave", off);
  cardEl.addEventListener("focus", on);
  cardEl.addEventListener("blur", off);
}});
</script>
</body></html>
'''

os.makedirs("/home/jk/exp/LTZ2026/web", exist_ok=True)
with open("/home/jk/exp/LTZ2026/web/index.html", "w", encoding="utf-8") as f:
    f.write(HTML)
print("web/index.html", len(HTML), "байт")
