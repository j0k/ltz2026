const { chromium } = require('playwright');
const fs = require('fs');
const OUT = '/home/jk/exp/LTZ2026/films/kostik/assets/';
const RUN = 'https://ltz2026.ru/check/20260929-113951-f00f86';
const REJ = 'https://ltz2026.ru/check/20260929-113749-64567f';
const meta = {};
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 854 }, deviceScaleFactor: 1 });
  const hide = async (extra = '') => p.addStyleTag({ content: '[class*=cookie],#cookieBar{display:none!important}' + extra });
  const bb = async (sel) => { const e = p.locator(sel).first(); const r = await e.boundingBox(); return r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null; };
  const shot = async (name) => { await p.waitForTimeout(700); await p.screenshot({ path: OUT + name }); };
  const top = async (sel, off = 90) => { await p.evaluate(([s, o]) => { const e = document.querySelector(s); window.scrollTo(0, e.getBoundingClientRect().top + scrollY - o); }, [sel, off]); await p.waitForTimeout(400); };

  // главная без декоративной 3D-модели
  await p.goto('https://ltz2026.ru/', { waitUntil: 'load' }); await hide('#bone3d,.k-bone{display:none!important}');
  const skip = p.getByText('Пропустить'); if (await skip.count()) await skip.first().click().catch(() => {});
  meta.home = { drop: await bb('.k-drop'), presets: await bb('text=или выберите готовый пример') };
  await shot('02_home.png');

  await p.goto(RUN, { waitUntil: 'load' }); await p.evaluate(() => localStorage.removeItem('dxaqc_pic_view'));
  await p.goto(RUN, { waitUntil: 'load' }); await hide();
  meta.dash = { kpis: await bb('.d-kpis'), bad: await bb('.d-thumb.bad'), xlsx: await bb('text=Таблица XLSX'), types: await bb('.d-bars li.on') };
  await shot('03_dashboard.png');

  const card = 'article.d-img.bad';
  await top(card, 20);
  meta.card = { pic: await bb(card + ' .pic'), checks: await bb(card + ' .d-checks'), verdict: await bb(card + ' .d-img-h .pill') };
  await shot('04_card.png');

  await p.locator(card + ' .pic-sw button[data-p=raw]').click(); await p.waitForTimeout(500);
  meta.raw = { pic: await bb(card + ' .pic'), sw: await bb(card + ' .pic-sw') };
  await shot('05_raw.png');
  await p.locator(card + ' .pic-sw button[data-p=atlas]').click();

  await top(card + ' .xg-box', 60);
  meta.graph = { box: await bb(card + ' .xg-box'), sw: await bb(card + ' .xg-sw') };
  await shot('06_graph.png');
  await p.locator(card + ' .xg-sw button[data-v=text]').click(); await p.waitForTimeout(400);
  meta.text = { box: await bb(card + ' .xg-box') };
  await shot('07_text.png');
  await p.locator(card + ' .xg-sw button[data-v=graph]').click();

  const tbl = await p.evaluateHandle(() => [...document.querySelectorAll('h2')].find(e => e.textContent.includes('Таблица результатов')));
  await p.evaluate((h) => window.scrollTo(0, h.getBoundingClientRect().top + scrollY - 40), tbl); await p.waitForTimeout(400);
  meta.table = { table: await bb('table.d-res, .d-table table, table') };
  await shot('08_table.png');

  await p.goto(REJ, { waitUntil: 'load' }); await hide(); await top('.d-rej', 30);
  meta.reject = { card: await bb('.d-rej'), seen: await bb('.d-rej-seen'), els: await bb('.d-rej-el') };
  await shot('09_reject.png');

  await p.goto('https://ltz2026.ru/download', { waitUntil: 'load' }); await hide('#shots{display:none!important}');
  await p.evaluate(() => { const h = [...document.querySelectorAll('h2')].find(e => e.textContent.includes('Как выглядит')); if (h) h.style.display = 'none'; });
  meta.download = { btn: await bb('.dl-main'), files: await bb('.dl-files') };
  await shot('10_download.png');
  fs.writeFileSync(OUT + '../meta.json', JSON.stringify(meta, null, 1));
  console.log(JSON.stringify(meta));
  await b.close();
})();
