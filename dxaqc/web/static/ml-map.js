/* Шпаргалка scikit-learn (/tz/ml-map.html): рисует узлы и стрелки схемы из #ml-data, выбор узла открывает оценку для
   задачи 04, «Путь задачи 04» подсвечивает маршрут, фильтр оставляет алгоритмы выбранной перспективности. Без зависимостей. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const $ = id => document.getElementById(id);
  const src = $('ml-data'), svg = $('mlSvg');
  if (!src || !svg) return;
  const data = JSON.parse(src.textContent);
  const byId = Object.fromEntries(data.nodes.map(n => [n.id, n]));
  const onPath = new Set(data.path);
  const pathEdges = new Set(data.path.slice(1).map((id, i) => data.path[i] + '>' + id));
  let selected = null, level = '';

  const el = (tag, attrs, parent, text) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    if (text !== undefined) e.textContent = text;
    if (parent) parent.append(e);
    return e;
  };

  // ---------- геометрия: точка на границе узла в сторону другой точки
  function boundary(n, tx, ty) {
    const dx = tx - n.x, dy = ty - n.y, len = Math.hypot(dx, dy) || 1;
    if (n.kind === 'estimator') {
      const hw = n.w / 2 + 3, hh = n.h / 2 + 3;
      const k = Math.min(hw / Math.abs(dx || 1e-6), hh / Math.abs(dy || 1e-6));
      return [n.x + dx * k, n.y + dy * k];
    }
    const r = (n.r || 40) + 3;
    return [n.x + dx / len * r, n.y + dy / len * r];
  }
  // ---------- стрелки
  const gEdges = $('mlEdges');
  data.edges.forEach(e => {
    const a = byId[e.src], b = byId[e.dst];
    const [x1, y1] = boundary(a, b.x, b.y), [x2, y2] = boundary(b, a.x, a.y);
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, nx = -(y2 - y1), ny = x2 - x1, nl = Math.hypot(nx, ny) || 1;
    const bend = 0.12 * Math.hypot(x2 - x1, y2 - y1);
    const cx = mx + nx / nl * bend, cy = my + ny / nl * bend;
    const key = e.src + '>' + e.dst;
    const path = el('path', { class: `ml-edge e-${e.kind}`, d: `M${x1.toFixed(1)},${y1.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`,
      'marker-end': `url(#ml-arrow-${e.kind})`, 'data-key': key }, gEdges);
    if (pathEdges.has(key)) path.classList.add('on-path');
    const label = data.edge_kinds[e.kind];
    // подписи стрелок — отдельным слоем поверх узлов, на светлой обводке: иначе узлы закрывали «не сработало»
    if (label) el('text', { class: `ml-elabel e-${e.kind}`, x: (0.25 * x1 + 0.5 * cx + 0.25 * x2).toFixed(1), y: (0.25 * y1 + 0.5 * cy + 0.25 * y2 - 4).toFixed(1),
      'text-anchor': 'middle' }, $('mlEdgeLabels'), label);
  });

  // ---------- узлы
  const gNodes = $('mlNodes');
  function wrap(text, max) {
    const words = text.replace(/ · /g, ' ·\n').split(/\s+|\n/), lines = [];
    let cur = '';
    words.forEach(w => {
      if (w === '·') { if (cur) lines.push(cur); cur = ''; return; }
      if ((cur + ' ' + w).trim().length > max && cur) { lines.push(cur); cur = w; } else cur = (cur + ' ' + w).trim();
    });
    if (cur) lines.push(cur);
    return lines;
  }
  data.nodes.forEach(n => {
    const g = el('g', { class: `ml-n ${n.kind}${n.perspective ? ' p-' + n.perspective : ''}`, tabindex: '0', role: 'button',
      'aria-label': `${n.ru} (${n.label})` + (n.perspective ? `, перспективность ${data.perspective[n.perspective].label}` : '') }, gNodes);
    if (onPath.has(n.id)) g.classList.add('on-path');
    if (n.kind === 'estimator') {
      if (n.perspective) el('rect', { class: 'ring', x: n.x - n.w / 2 - 6, y: n.y - n.h / 2 - 6, width: n.w + 12, height: n.h + 12, rx: 9 }, g);
      el('rect', { class: 'shape', x: n.x - n.w / 2, y: n.y - n.h / 2, width: n.w, height: n.h, rx: 5 }, g);
    } else {
      el('ellipse', { class: 'shape', cx: n.x, cy: n.y, rx: (n.r || 40) * (n.kind === 'start' ? 1.15 : 1.08), ry: (n.r || 40) * (n.kind === 'start' ? 0.82 : 0.78) }, g);
    }
    const lines = wrap(n.label, n.kind === 'estimator' ? Math.max(9, Math.round(n.w / 6.6)) : 13);
    const lh = n.kind === 'start' ? 18 : 13.5, top = n.y - (lines.length - 1) * lh / 2 + 4;
    lines.forEach((ln, i) => el('text', { x: n.x, y: (top + i * lh).toFixed(1) }, g, ln));
    if (n.perspective && n.kind === 'estimator') {
      const px = n.x + n.w / 2 + 4, py = n.y - n.h / 2 - 4;
      el('circle', { class: 'pdot', cx: px, cy: py, r: 9 }, g);
      el('text', { class: 'pmark', x: px, y: py + 4 }, g, data.perspective[n.perspective].icon);
    } else if (n.perspective) {
      const px = n.x + (n.r || 40) * 0.95, py = n.y - (n.r || 40) * 0.7;
      el('circle', { class: 'pdot', cx: px, cy: py, r: 9 }, g);
      el('text', { class: 'pmark', x: px, y: py + 4 }, g, data.perspective[n.perspective].icon);
    }
    g.addEventListener('click', () => select(n));
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(n); } });
    n.g = g;
  });

  // ---------- панель
  const KIND = { estimator: 'алгоритм scikit-learn', decision: 'вопрос схемы', action: 'исход схемы', start: 'начало' };
  function html(tag, cls, text, parent) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    if (parent) parent.append(e);
    return e;
  }
  function select(n) {
    if (selected) selected.g.classList.remove('is-selected');
    selected = n; n.g.classList.add('is-selected');
    const region = data.regions.find(r => r.id === n.region);
    $('mlKind').textContent = KIND[n.kind] + (region ? ' · ' + region.ru : '') + (onPath.has(n.id) ? ' · на пути задачи 04' : '');
    $('mlTitle').textContent = n.ru + (n.label && n.label.toLowerCase() !== n.ru.toLowerCase() ? ` · ${n.label}` : '');
    const badges = $('mlBadges'); badges.replaceChildren();
    if (n.perspective) {
      const b = html('span', 'ml-pbadge p-' + n.perspective, '', badges);
      html('span', '', data.perspective[n.perspective].icon, b).setAttribute('aria-hidden', 'true');
      b.append(document.createTextNode(`перспективность для задачи 04: ${data.perspective[n.perspective].label}`));
    }
    const body = $('mlBody'); body.replaceChildren();
    if (n.text) html('p', '', n.text, body);
    if (n.sklearn && n.sklearn.length) {
      html('div', 'ml-sub', 'Классы scikit-learn', body);
      const codes = html('div', 'ml-codes', '', body);
      n.sklearn.forEach(s => html('code', '', s, codes));
    }
    if (n.used) { html('div', 'ml-sub', 'Используется у нас', body); html('div', 'ml-used', n.used, body); }
    if (n.why) { html('div', 'ml-sub', 'Почему такая оценка', body); html('p', '', n.why, body); }
    if (n.ours) { html('div', 'ml-sub', n.kind === 'decision' ? 'Ответ для задачи 04' : 'Для задачи 04', body); html('div', 'ml-used', n.ours, body); }
    if (window.matchMedia('(max-width: 1000px)').matches) $('mlPanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ---------- путь и фильтр
  const scroll = $('mlScroll');
  function setPath(on) {
    scroll.classList.toggle('show-path', on);
    $('mlPath').setAttribute('aria-pressed', String(on));
  }
  $('mlPath').addEventListener('click', () => setPath(!scroll.classList.contains('show-path')));
  document.querySelectorAll('.ml-chip[data-level]').forEach(b => b.addEventListener('click', () => {
    level = level === b.dataset.level ? '' : b.dataset.level;
    document.querySelectorAll('.ml-chip[data-level]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.level === level)));
    data.nodes.forEach(n => n.g.classList.toggle('is-dim', !!level && n.kind === 'estimator' && n.perspective !== level));
  }));
  setPath(true);
  window.__mlmap = { select: id => select(byId[id]), selected: () => selected && selected.id, nodes: data.nodes.length };
})();
