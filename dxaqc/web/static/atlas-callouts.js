/* Компонент стилизованных подписей атласа: рисует выноски, плашки, заголовок, отметки сторон и легенду поверх
   картинки без подписей. Данные — row.callouts из manifest (atlas.render), разметка — макрос
   templates/macros/atlas_callouts.html. Без зависимостей.

   data = {size: [W, H], image_box: [x, y, w, h], title, note,
           items: [{id, label, sub, color, align: "left"|"right", anchor: [x, y], knee: [x, y], end: [x, y]}],
           marks: [{text, x, y, align?}], legend: [{label, color}]}
   Координаты в пикселях атласа; end — край плашки: у align="left" плашка стоит левее этой точки, у "right" — правее.

   window.AtlasCallouts.mount(figure, data) — для фигуры, добавленной после загрузки страницы;
   window.AtlasCallouts.mountAll(root) — все [data-atlas-callouts] внутри root. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const EDGE = 1.6;   // отступ колонок подписей от края рисунка, % ширины (16 px атласа шириной 1020)
  let seq = 0;

  function svgEl(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (parent) parent.append(e);
    return e;
  }
  function htmlEl(tag, cls, parent, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    if (parent) parent.append(e);
    return e;
  }
  const pct = (v, total) => (v / total * 100).toFixed(3) + '%';
  const color = c => (/^#[0-9a-f]{6}$/i.test(c || '') ? c : '#9fb3c8');

  function mount(fig, data) {
    if (!fig || !data || !Array.isArray(data.size) || fig.dataset.acallMounted) return;
    fig.dataset.acallMounted = '1';
    const [W, H] = data.size;
    const [bx, by, bw, bh] = data.image_box || [0, 0, W, H];
    const uid = 'acall' + (++seq);

    const svg = svgEl('svg', { class: 'acall-svg', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', 'aria-hidden': 'true', focusable: 'false' });
    const defs = svgEl('defs', {}, svg);
    const layer = htmlEl('div', 'acall-layer');
    layer.setAttribute('aria-hidden', 'true');   // текст подписей уже есть в alt картинки и на странице
    const links = [];

    (data.items || []).forEach((it, i) => {
      const c = color(it.color);
      const grad = svgEl('linearGradient', { id: `${uid}g${i}`, gradientUnits: 'userSpaceOnUse',
        x1: it.anchor[0], y1: it.anchor[1], x2: it.end[0], y2: it.end[1] }, defs);
      svgEl('stop', { offset: '0', 'stop-color': c, 'stop-opacity': '1' }, grad);
      svgEl('stop', { offset: '1', 'stop-color': '#dbeafe', 'stop-opacity': '.45' }, grad);
      const g = svgEl('g', { class: 'acall-g', style: `--i:${i}` }, svg);
      const path = svgEl('path', { class: 'acall-leader', stroke: `url(#${uid}g${i})`,
        d: `M${it.anchor[0]},${it.anchor[1]} L${it.knee[0]},${it.knee[1]} L${it.end[0]},${it.end[1]}` }, g);
      svgEl('circle', { class: 'acall-halo', cx: it.anchor[0], cy: it.anchor[1], r: 10, fill: c }, g);
      svgEl('circle', { class: 'acall-dot', cx: it.anchor[0], cy: it.anchor[1], r: 3.8, fill: c }, g);

      const chip = htmlEl('div', 'acall-chip acall-' + (it.align === 'right' ? 'right' : 'left'), layer);
      chip.style.setProperty('--i', i);
      chip.style.setProperty('--c', c);
      chip.style.top = pct(it.end[1], H);
      // плашки выровнены по внешнему краю рисунка, как колонки подписей в атласе; ширина — по тексту, но не дальше
      // точки на зоне; выноска после вёрстки дотягивается до внутреннего края плашки (fit)
      const room = it.align === 'right' ? W - it.anchor[0] - 22 : it.anchor[0] - 22;
      chip.style.setProperty('--mw', Math.max(8, room / W * 100 - EDGE).toFixed(2) + '%');
      if (it.align === 'right') chip.style.right = EDGE + '%';
      else chip.style.left = EDGE + '%';
      links.push({ it, chip, path });
      htmlEl('i', '', chip);
      const text = htmlEl('span', 'acall-text', chip);
      htmlEl('b', '', text, it.label);
      if (it.sub) htmlEl('small', '', text, it.sub);
      const hot = on => { g.classList.toggle('is-hot', on); chip.classList.toggle('is-hot', on); };
      chip.addEventListener('pointerenter', () => hot(true));
      chip.addEventListener('pointerleave', () => hot(false));
    });

    if (data.title && fig.dataset.title !== 'off') {
      const t = htmlEl('div', 'acall-title', layer, data.title);
      t.style.top = pct(by / 2, H);
    }
    (data.marks || []).forEach(m => {
      const e = htmlEl('div', 'acall-mark' + (m.align ? ' is-' + m.align : ''), layer, m.text);
      e.style.left = pct(m.x, W);
      e.style.top = pct(m.y, H);
    });
    if ((data.legend || []).length && fig.dataset.legend !== 'off') {
      const lg = htmlEl('div', 'acall-legend', layer);
      lg.style.top = pct(by + bh + (H - by - bh) / 2, H);
      data.legend.forEach(l => {
        const s = htmlEl('span', '', lg);
        htmlEl('i', '', s).style.setProperty('--c', color(l.color));
        s.append(document.createTextNode(l.label));
      });
      if (data.note) htmlEl('em', '', lg, data.note);
    }

    fig.append(svg, layer);

    // выноска: от точки на зоне через излом к внутреннему краю плашки — пересчёт при изменении размера и загрузке шрифта
    function fit() {
      const f = fig.getBoundingClientRect();
      if (!f.width) return;
      const k = W / f.width;
      links.forEach(({ it, chip, path }) => {
        const r = chip.getBoundingClientRect();
        const [ax, ay] = it.anchor;
        const y = it.end[1];
        if (it.align === 'right') {               // плашка справа от зоны: внутренний край — левый
          const inner = (r.left - f.left) * k;
          const kx = Math.max(ax, inner - 14);    // излом в 14 px от плашки, но не за точкой на зоне
          path.setAttribute('d', `M${ax},${ay} L${kx.toFixed(1)},${y} L${inner.toFixed(1)},${y}`);
        } else {                                  // плашка слева от зоны: внутренний край — правый
          const inner = (r.right - f.left) * k;
          const kx = Math.min(ax, inner + 14);
          path.setAttribute('d', `M${ax},${ay} L${kx.toFixed(1)},${y} L${inner.toFixed(1)},${y}`);
        }
      });
    }
    fit();
    if (window.ResizeObserver) new ResizeObserver(fit).observe(fig);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);

    // появление по очереди начинается, когда картинка готова: подписи не висят над пустым фоном
    const img = fig.querySelector('img');
    const ready = () => requestAnimationFrame(() => fig.classList.add('is-ready'));
    if (!img || img.complete) ready();
    else { img.addEventListener('load', ready, { once: true }); img.addEventListener('error', ready, { once: true }); }
  }

  function mountAll(root) {
    (root || document).querySelectorAll('[data-atlas-callouts]').forEach(fig => {
      const src = fig.querySelector('script.acall-data');
      if (!src) return;
      try { mount(fig, JSON.parse(src.textContent)); } catch (e) { console.warn('atlas-callouts:', e); }
    });
  }

  window.AtlasCallouts = { mount, mountAll };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => mountAll());
  else mountAll();
})();
