// Живая запись демо Kostik: настоящий браузер, видимый курсор, плавная прокрутка, загрузка архива.
// Длительность сцен — по озвучке (script.json, dur). Пишет video/*.webm и timeline.json.
const { chromium } = require('/tmp/pwv/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const DIR = __dirname;
const S = JSON.parse(fs.readFileSync(path.join(DIR, 'script.json'), 'utf8'));
const BASE = 'https://ltz2026.ru';
const REJ = BASE + '/check/20260929-113749-64567f';
const HIDE = '[class*=cookie],#cookieBar{display:none!important}';

const CURSOR = `(() => {
  const mk = () => {
    if (document.getElementById('fc')) return;
    const c = document.createElement('div'); c.id = 'fc';
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.2-7.3L20 11.5z" fill="#0B1320" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '-100px', top: '-100px', zIndex: 2147483647, pointerEvents: 'none',
      transition: 'transform .08s', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))' });
    document.documentElement.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX - 3 + 'px'; c.style.top = e.clientY - 2 + 'px'; }, true);
    addEventListener('mousedown', e => {
      const r = document.createElement('div');
      Object.assign(r.style, { position: 'fixed', left: e.clientX - 22 + 'px', top: e.clientY - 22 + 'px', width: '44px', height: '44px',
        borderRadius: '50%', border: '3px solid #2E6BFF', zIndex: 2147483646, pointerEvents: 'none', opacity: '1',
        transition: 'transform .5s ease-out, opacity .5s ease-out' });
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 600);
      c.style.transform = 'scale(.85)'; setTimeout(() => c.style.transform = '', 120);
    }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
})();`;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: path.join(DIR, 'video'), size: { width: 1920, height: 1080 } } });
  await ctx.addInitScript(CURSOR);
  const p = await ctx.newPage();
  const T0 = Date.now();
  const now = () => (Date.now() - T0) / 1000;
  let mx = 960, my = 540;
  const move = async (x, y, ms = 700) => {
    const steps = Math.max(6, Math.round(ms / 55));          // один шаг мыши под записью ≈ 45–55 мс
    const t0 = Date.now();
    for (let i = 1; i <= steps; i++) {
      const t = i / steps, e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      await p.mouse.move(mx + (x - mx) * e, my + (y - my) * e);
      const lag = t0 + ms * t - Date.now(); if (lag > 5) await p.waitForTimeout(lag);
    }
    mx = x; my = y;
  };
  const center = async (sel) => { const r = await p.locator(sel).first().boundingBox(); return [r.x + r.width / 2, r.y + r.height / 2, r]; };
  const glide = async (sel, ms = 700, dx = 0, dy = 0) => { const [x, y] = await center(sel); await move(x + dx, y + dy, ms); };
  const click = async (sel, ms = 600) => { await glide(sel, ms); await p.mouse.down(); await p.waitForTimeout(90); await p.mouse.up(); };
  const scrollTo = async (sel, off = 80, ms = 1200) => {
    await p.evaluate(([s, o, d]) => new Promise(res => {
      const el = document.querySelector(s); const y0 = scrollY, y1 = el.getBoundingClientRect().top + scrollY - o, t0 = performance.now();
      const step = (t) => { const k = Math.min(1, (t - t0) / d), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        scrollTo(0, y0 + (y1 - y0) * e); k < 1 ? requestAnimationFrame(step) : res(); };
      requestAnimationFrame(step);
    }), [sel, off, ms]);
  };
  const timeline = [], cuts = [];
  let sceneStart = 0, idx = 0, sceneCut = 0;
  const cut = (a, b) => { if (b > a) { cuts.push([a, b]); sceneCut += b - a; } };
  const scene = async (fn) => {
    const s = S[idx++]; sceneStart = now(); sceneCut = 0; timeline.push({ id: s.id, start: sceneStart });
    await fn();
    const until = sceneStart + sceneCut + s.dur + 0.7;
    while (now() < until) await p.waitForTimeout(50);
    timeline[timeline.length - 1].end = now();
  };
  const slide = async (file) => {
    const b64 = fs.readFileSync(path.join(DIR, file)).toString('base64');
    await p.setContent(`<html><body style="margin:0;background:#0B1320;overflow:hidden">
      <img src="data:image/png;base64,${b64}" style="width:100vw;height:100vh;object-fit:cover;transform-origin:28% 42%;animation:kb 18s ease-out forwards">
      <style>@keyframes kb{from{transform:scale(1)}to{transform:scale(1.07)}}</style></body></html>`);
  };

  // 1. Титул
  await scene(async () => { await slide('slide-01.png'); await p.waitForTimeout(1500); await move(620, 520, 1400); await move(420, 470, 1600); });

  // 2. Загрузка архива на главной
  await scene(async () => {
    await p.goto(BASE + '/', { waitUntil: 'load' });
    await p.addStyleTag({ content: HIDE + '#bone3d,.k-bone{display:none!important}' });
    const skip = p.getByText('Пропустить'); if (await skip.count()) await skip.first().click().catch(() => {});
    await p.waitForTimeout(500);
    await glide('.k-drop', 900); await p.waitForTimeout(500);
    await p.mouse.down(); await p.waitForTimeout(90); await p.mouse.up();
    const up = now();
    await p.setInputFiles('#v2Files', path.join(DIR, 'kostik_demo_phantoms.zip'));
    await p.waitForURL(/\/check\//, { timeout: 60000 });
    await p.waitForSelector('.d-kpis', { timeout: 60000 });
    cut(up + 2.2, now() - 0.4);                               // ожидание сети и очереди — вырезаем при монтаже
    await p.addStyleTag({ content: HIDE });
    await p.evaluate(() => localStorage.removeItem('dxaqc_pic_view'));
  });

  // 3. Дашборд
  await scene(async () => {
    await glide('.d-kpis', 900); await p.waitForTimeout(600);
    await glide('.d-kpi.bad', 700); await p.waitForTimeout(700);
    await glide('.d-thumb.bad', 900); await p.waitForTimeout(600);
    await glide('.d-bars li.on', 800);
  });

  // 4. Карточка снимка
  const card = 'article.d-img.bad';
  await scene(async () => {
    await glide('.d-thumb.bad', 500); await p.mouse.down(); await p.waitForTimeout(90); await p.mouse.up();
    await p.waitForTimeout(300);
    await scrollTo(card, 20, 1300);
    await p.waitForTimeout(400);
    const [, , r] = await center(card + ' .pic');
    await move(r.x + r.width * 0.34, r.y + r.height * 0.22, 900); await p.waitForTimeout(700);
    await move(r.x + r.width * 0.62, r.y + r.height * 0.55, 900); await p.waitForTimeout(700);
    await glide(card + ' .d-checks li.bad', 900);
  });

  // 5. Атлас ⇄ снимок
  await scene(async () => {
    await click(card + ' .pic-sw button[data-p=raw]', 800); await p.waitForTimeout(2600);
    await click(card + ' .pic-sw button[data-p=atlas]', 500); await p.waitForTimeout(800);
  });

  // 6. Граф решения → текст
  await scene(async () => {
    await scrollTo(card + ' .xg-box', 120, 1200);
    const [, , r] = await center(card + ' .xg-box');
    await move(r.x + r.width * 0.5, r.y + r.height * 0.18, 800); await p.waitForTimeout(600);
    await move(r.x + r.width * 0.83, r.y + r.height * 0.58, 1000); await p.waitForTimeout(1200);
    await move(r.x + r.width * 0.5, r.y + r.height * 0.78, 800); await p.waitForTimeout(1500);
    await click(card + ' .xg-sw button[data-v=text]', 700); await p.waitForTimeout(1600);
  });

  // 7. Таблица
  await scene(async () => {
    await click(card + ' .xg-sw button[data-v=graph]', 400);
    const h = await p.evaluateHandle(() => [...document.querySelectorAll('h2')].find(e => e.textContent.includes('Таблица результатов')));
    await p.evaluate((el) => el.id = 'resTable', h);
    await scrollTo('#resTable', 60, 1500);
    await p.waitForTimeout(400);
    const [, , r] = await center('#resTable');
    await move(r.x + 120, r.y + 140, 900); await p.waitForTimeout(500);
    await move(r.x + 760, r.y + 140, 1300); await p.waitForTimeout(800);
    await scrollTo('body', 0, 1300); await p.waitForTimeout(300);
    await glide('text=Таблица XLSX', 800);
  });

  // 8. Не тот файл
  await scene(async () => {
    await p.goto(REJ, { waitUntil: 'load' }); await p.addStyleTag({ content: HIDE });
    await scrollTo('.d-rej', 40, 1200);
    await glide('.d-rej-pic', 800); await p.waitForTimeout(600);
    await glide('.d-rej-seen', 900, 120); await p.waitForTimeout(900);
    await glide('.d-rej-el', 900, 60);
  });

  // 9. Приложение
  await scene(async () => {
    await p.goto(BASE + '/download', { waitUntil: 'load' });
    await p.addStyleTag({ content: HIDE + '#shots{display:none!important}' });
    await p.evaluate(() => { const h = [...document.querySelectorAll('h2')].find(e => e.textContent.includes('Как выглядит')); if (h) h.style.display = 'none'; });
    await glide('.dl-main', 900); await p.waitForTimeout(700);
    await glide('.dl-files', 900, -250, 20);
  });

  // 10. Финал
  await scene(async () => { await slide('slide-21.png'); await move(1500, 700, 1600); });

  fs.writeFileSync(path.join(DIR, 'timeline.json'), JSON.stringify({ scenes: timeline, cuts }, null, 1));
  const video = await p.video().path();
  await ctx.close(); await browser.close();
  fs.writeFileSync(path.join(DIR, 'video_path.txt'), video);
  console.log('video', video, 'timeline', JSON.stringify(timeline));
})();
