// Предрасчёт видео «регенерации» кости для главной (29.09, Юрий): кадры сцены bone3d.js рендерятся заранее в headless Chromium
// (программный WebGL), потом собираются в mp4/webm. Браузер пользователя только проигрывает видео — ничего не считает.
//
//   node scripts/render_bone_video.js <папка кадров> [кадров=240] [размер=960]
//   scripts/encode_bone_video.sh <папка кадров>      # ffmpeg в docker → dxaqc/web/static/bone/regen.{mp4,webm}
//
// Цикл 10 с при 24 кадр/с: пустой срез → трабекулы вырастают от коры к центру (фронт светится) → держатся → рассасываются;
// модель плавно качается ±12°, камера наезжает на решётку, пока она растёт. Первый и последний кадры совпадают, петля бесшовная.
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const out = process.argv[2] || '/tmp/bone_frames', N = +(process.argv[3] || 240), SZ = +(process.argv[4] || 960);
const ROOT = path.join(__dirname, '..', 'dxaqc', 'web');
fs.mkdirSync(out, { recursive: true });
const mime = { '.js': 'text/javascript', '.gz': 'application/gzip', '.html': 'text/html', '.jpg': 'image/jpeg' };
const page = `<!doctype html><meta charset=utf-8><style>html,body{margin:0;background:#fff}#bone3d{width:${SZ}px;height:${SZ}px;background:#fff}</style>
<div id="bone3d" data-v="7"></div><script type="importmap">{"imports":{"three":"/static/vendor/three/three.module.min.js"}}</script>
<script>window.__BONE_RENDER=true</script><script type="module" src="/static/bone3d.js"></script>`;
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  if (u === '/render.html') { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(page); }
  const f = path.join(ROOT, u); if (!f.startsWith(ROOT) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': mime[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res);
});
// приближение камеры к решётке: наезд на росте, отъезд на рассасывании
const zoomAt = p => { const e = x => .5 - .5 * Math.cos(Math.PI * Math.min(Math.max(x, 0), 1)); return p < .04 ? 0 : p < .26 ? e((p - .04) / .22) : p < .62 ? 1 : p < .80 ? 1 - e((p - .62) / .18) : 0; };
const regen = p => { const e = x => .5 - .5 * Math.cos(Math.PI * Math.min(Math.max(x, 0), 1));
  return p < .10 ? -.05 : p < .62 ? -.05 + 1.45 * e((p - .10) / .52) : p < .86 ? 1.40 : 1.40 - 1.45 * Math.pow(e((p - .86) / .14), 1.6); };
(async () => {
  await new Promise(r => srv.listen(0, r)); const port = srv.address().port;
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: SZ, height: SZ }, deviceScaleFactor: 1 });
  p.on('pageerror', e => console.error('PAGEERR', e.message)); p.on('console', m => { if (m.type() === 'error') console.error('CONSOLE', m.text().slice(0, 200)); });
  await p.goto(`http://127.0.0.1:${port}/render.html`);
  await p.waitForFunction(() => document.getElementById('bone3d').dataset.ready === '1' || document.getElementById('bone3d').dataset.error, null, { timeout: 120000 });
  const err = await p.evaluate(() => document.getElementById('bone3d').dataset.error); if (err) throw new Error(err);
  const t0 = Date.now();
  for (let k = 0; k < N; k++) {
    const ph = k / N, rot = 12 * Math.sin(2 * Math.PI * ph);
    await p.evaluate(([r, t, z]) => window.__boneFrame(r, t, z), [rot, regen(ph), zoomAt(ph)]);
    await p.screenshot({ path: path.join(out, `f${String(k).padStart(4, '0')}.png`), clip: { x: 0, y: 0, width: SZ, height: SZ } });
    if (k % 20 === 0) console.log(`кадр ${k}/${N}, ${((Date.now() - t0) / 1000).toFixed(0)} с`);
  }
  await b.close(); srv.close(); console.log('готово:', out);
})();
