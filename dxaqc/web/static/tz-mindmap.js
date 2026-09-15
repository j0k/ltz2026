/* Mind map ТЗ (/tz/mindmap.html): горизонтальное дерево из JSON #mm-data, без зависимостей.
   Узлы — HTML поверх SVG со связями; раскладка считается по измеренной высоте узлов; перетаскивание, колесо и щипок
   двумя пальцами меняют смещение и масштаб; поиск и фильтр по статусу раскрывают нужные ветки. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const page = document.querySelector('.mm-page');
  const view = $('mm'), world = $('mmWorld'), links = $('mmLinks');
  const src = $('mm-data');
  if (!page || !view || !world || !src) return;
  page.classList.remove('no-js');

  const STATUS = { done: ['✓', 'сделано'], partial: ['◐', 'частично'], todo: ['✕', 'не сделано'], info: ['i', 'справка'] };
  const PDF = view.dataset.pdf || '';
  const NS = 'http://www.w3.org/2000/svg';
  const GAP_Y = 10, GAP_BRANCH = 22, GAP_X = 56, PAD = 40;
  const tree = JSON.parse(src.textContent);
  const nodes = [];
  let selected = null, query = '', filter = '';
  const T = { x: 0, y: 0, s: 1 };

  // ---------- модель
  (function prep(n, parent, depth, branch) {
    n.parent = parent; n.depth = depth; n.branch = branch; n.id = nodes.length;
    n.open = depth < 1;   // на старте видны 8 веток: дерево вписывается без мелкого текста, пункты раскрываются по клику
    nodes.push(n);
    n.children.forEach((c, i) => prep(c, n, depth + 1, depth === 0 ? i % 8 : branch));
  })(tree, null, 0, -1);
  const norm = s => (s || '').toLowerCase().replace(/ё/g, 'е');
  const descendantsOf = n => n.children.flatMap(c => [c, ...descendantsOf(c)]);
  const ancestors = n => { const out = []; for (let p = n.parent; p; p = p.parent) out.push(p); return out; };
  const isVisible = n => ancestors(n).every(p => p.open);

  // ---------- узлы
  nodes.forEach(n => {
    const el = document.createElement('div');
    el.className = `mm-node d${Math.min(n.depth, 3)}`;
    if (n.branch >= 0) el.style.setProperty('--b', `var(--br${n.branch})`);
    const main = document.createElement('button');
    main.type = 'button'; main.className = 'mm-main';
    if (n.status && n.depth > 0) {
      const ic = document.createElement('span');
      ic.className = 'mm-ic s-' + n.status; ic.textContent = STATUS[n.status][0];
      ic.title = STATUS[n.status][1];
      main.append(ic);
    }
    const t = document.createElement('span'); t.className = 'mm-t'; t.textContent = n.title;
    if (n.page) { const p = document.createElement('span'); p.className = 'mm-p'; p.textContent = `стр. ${n.page}`; t.append(p); }
    main.append(t);
    main.setAttribute('aria-label', n.title + (n.status ? `, ${STATUS[n.status][1]}` : ''));
    main.addEventListener('click', () => select(n, false));
    el.append(main);
    if (n.children.length) {
      const tog = document.createElement('button');
      tog.type = 'button'; tog.className = 'mm-tog';
      tog.addEventListener('click', e => { e.stopPropagation(); toggle(n); });
      el.append(tog);
      n.tog = tog;
    }
    world.append(el);
    n.el = el;
  });

  // ---------- раскладка: колонки по глубине, вертикаль — по высоте поддеревьев
  function layout(animate = true) {
    if (!animate) world.classList.add('mm-noanim');
    nodes.forEach(n => {
      n.el.hidden = !isVisible(n);
      if (n.tog) {
        n.tog.textContent = n.open ? '−' : `+${n.children.length}`;
        n.tog.setAttribute('aria-label', (n.open ? 'свернуть ' : 'раскрыть ') + n.title);
        n.tog.setAttribute('aria-expanded', String(n.open));
      }
    });
    // замер на просторном холсте: при узком холсте абсолютные узлы сжимаются и переносят текст, а после раскладки
    // расширяются и наезжают на соседнюю колонку
    world.style.width = '20000px';
    world.style.height = '20000px';
    const colW = [];
    nodes.forEach(n => { if (!n.el.hidden) { n.w = n.el.offsetWidth; n.h = n.el.offsetHeight; colW[n.depth] = Math.max(colW[n.depth] || 0, n.w); } });
    const colX = [PAD];
    for (let d = 1; d < colW.length; d++) colX[d] = colX[d - 1] + colW[d - 1] + GAP_X;
    let y = PAD;
    const shift = (n, dy) => { n.y += dy; if (n.open) n.children.forEach(c => shift(c, dy)); };
    (function place(n) {
      n.x = colX[n.depth];
      const kids = n.open ? n.children : [];
      if (!kids.length) { n.y = y; y += n.h + GAP_Y; return; }
      const start = y;
      kids.forEach(place);
      const first = kids[0], last = kids[kids.length - 1];
      n.y = (first.y + last.y + last.h) / 2 - n.h / 2;
      if (n.y < start) { const dy = start - n.y; shift(n, dy); y += dy; }
      y = Math.max(y, n.y + n.h + GAP_Y) + (n.depth === 1 ? GAP_BRANCH : 0);
    })(tree);
    let W = 0, H = 0;
    nodes.forEach(n => {
      if (n.el.hidden) return;
      n.el.style.left = n.x + 'px'; n.el.style.top = n.y + 'px';
      W = Math.max(W, n.x + n.w); H = Math.max(H, n.y + n.h);
    });
    world.style.width = (W + PAD) + 'px'; world.style.height = (H + PAD) + 'px';
    links.setAttribute('width', W + PAD); links.setAttribute('height', H + PAD);
    links.replaceChildren();
    nodes.forEach(n => {
      if (n.el.hidden || !n.parent) return;
      const p = n.parent, x1 = p.x + p.w, y1 = p.y + p.h / 2, x2 = n.x, y2 = n.y + n.h / 2, dx = (x2 - x1) / 2;
      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`);
      path.setAttribute('stroke', n.branch >= 0 ? getComputedStyle(page).getPropertyValue(`--br${n.branch}`).trim() || '#8a8983' : '#8a8983');
      if (n.el.classList.contains('is-dim')) path.classList.add('is-dim');
      links.append(path);
    });
    world.dataset.w = W + PAD; world.dataset.h = H + PAD;
    if (!animate) requestAnimationFrame(() => world.classList.remove('mm-noanim'));
  }

  // ---------- смещение и масштаб
  const apply = () => { world.style.transform = `translate(${T.x}px, ${T.y}px) scale(${T.s})`; };
  const clampS = s => Math.min(2.2, Math.max(0.25, s));
  function zoomAt(px, py, f) {
    const s2 = clampS(T.s * f);
    T.x = px - (px - T.x) * (s2 / T.s); T.y = py - (py - T.y) * (s2 / T.s); T.s = s2; apply();
  }
  function fit() {
    const W = +world.dataset.w, H = +world.dataset.h, vw = view.clientWidth, vh = view.clientHeight;
    T.s = clampS(Math.min(vw / W, vh / H, 1));
    T.x = (vw - W * T.s) / 2; T.y = Math.max(0, (vh - H * T.s) / 2); apply();
  }
  function centerOn(n) {
    const vw = view.clientWidth, vh = view.clientHeight;
    if (T.s < 0.7) T.s = 0.85;
    T.x = vw / 2 - (n.x + n.w / 2) * T.s; T.y = vh / 2 - (n.y + n.h / 2) * T.s; apply();
  }
  const pointers = new Map();
  let pinch = null, dragged = false;
  view.addEventListener('pointerdown', e => {
    if (e.target.closest('.mm-node') && e.pointerType === 'mouse') return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    dragged = false;
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), s: T.s };
    }
    view.classList.add('is-panning');
  });
  view.addEventListener('pointermove', e => {
    const prev = pointers.get(e.pointerId);
    if (!prev) return;
    const cur = { x: e.clientX, y: e.clientY };
    pointers.set(e.pointerId, cur);
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()], r = view.getBoundingClientRect();
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      zoomAt((a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top, clampS(pinch.s * d / pinch.d) / T.s);
    } else {
      if (Math.abs(cur.x - prev.x) + Math.abs(cur.y - prev.y) > 0) dragged = true;
      T.x += cur.x - prev.x; T.y += cur.y - prev.y; apply();
    }
    if (dragged && !view.hasPointerCapture(e.pointerId)) view.setPointerCapture(e.pointerId);
  });
  const up = e => { pointers.delete(e.pointerId); if (pointers.size < 2) pinch = null; if (!pointers.size) view.classList.remove('is-panning'); };
  view.addEventListener('pointerup', up);
  view.addEventListener('pointercancel', up);
  view.addEventListener('click', e => { if (dragged) { e.stopPropagation(); e.preventDefault(); dragged = false; } }, true);
  view.addEventListener('wheel', e => {
    e.preventDefault();
    const r = view.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0016)));
  }, { passive: false });
  view.addEventListener('keydown', e => {
    if (e.target !== view) return;
    const step = 60, map = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    if (map[e.key]) { T.x += map[e.key][0]; T.y += map[e.key][1]; apply(); e.preventDefault(); }
    else if (e.key === '+' || e.key === '=') { zoomAt(view.clientWidth / 2, view.clientHeight / 2, 1.2); e.preventDefault(); }
    else if (e.key === '-') { zoomAt(view.clientWidth / 2, view.clientHeight / 2, 1 / 1.2); e.preventDefault(); }
    else if (e.key === '0') { fit(); e.preventDefault(); }
  });

  // ---------- раскрытие, выбор, поиск, фильтр
  function toggle(n, open) {
    n.open = open === undefined ? !n.open : open;
    layout();
  }
  function setAll(open) {
    nodes.forEach(n => { if (n.children.length) n.open = open || n.depth === 0; });
    layout(); fit();
  }
  function panelLink(label, url, blank) {
    const a = document.createElement('a'); a.href = url; a.textContent = label;
    if (blank) { a.target = '_blank'; a.rel = 'noopener'; }
    return a;
  }
  function select(n, center) {
    if (selected) selected.el.classList.remove('is-selected');
    selected = n; n.el.classList.add('is-selected');
    $('mmCrumbs').textContent = ancestors(n).reverse().map(a => a.title).join(' › ') || 'ТЗ задачи 04';
    $('mmTitle').textContent = n.title;
    const st = $('mmStatus'); st.replaceChildren();
    if (n.status && n.depth > 0) {
      const box = document.createElement('div'); box.className = 'mm-st';
      const ic = document.createElement('span'); ic.className = 'mm-ic s-' + n.status; ic.textContent = STATUS[n.status][0];
      box.append(ic, document.createTextNode(n.status === 'info' ? 'справка' : `на стенде: ${STATUS[n.status][1]}`));
      st.append(box);
    } else if (n.children.length) {
      const c = { done: 0, partial: 0, todo: 0 };   // как плитки: все пункты ветки со статусом, не только конечные
      descendantsOf(n).forEach(l => { if (c[l.status] !== undefined) c[l.status]++; });
      const box = document.createElement('div'); box.className = 'mm-st faint';
      box.textContent = `в ветке: сделано ${c.done}, частично ${c.partial}, не сделано ${c.todo}`;
      st.append(box);
    }
    $('mmText').textContent = n.text || '';
    const stand = $('mmStand'); stand.replaceChildren();
    if (n.stand) { const b = document.createElement('b'); b.textContent = 'На стенде: '; stand.append(b, document.createTextNode(n.stand)); }
    const list = $('mmLinksList'); list.replaceChildren();
    if (n.page) list.append(panelLink(`Страница ${n.page} в ТЗ →`, PDF ? `${PDF}#page=${n.page}` : '#', !!PDF));
    (n.links || []).forEach(l => list.append(panelLink(l.label + ' →', l.url, false)));
    if (n.children.length && !n.open) toggle(n, true);
    if (center) centerOn(n);
    if (window.matchMedia('(max-width: 980px)').matches && !center) $('mmPanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function matches(n) {
    const okQ = !query || norm(n.title + ' ' + n.text + ' ' + n.stand).includes(query);
    const okF = !filter || n.status === filter;
    return okQ && okF && (query || filter);
  }
  function refilter() {
    const hits = nodes.filter(n => n.depth > 0 && matches(n));
    const keep = new Set();
    hits.forEach(h => { keep.add(h); ancestors(h).forEach(a => { keep.add(a); a.open = true; }); });
    nodes.forEach(n => {
      n.el.classList.toggle('is-match', hits.includes(n) && !!query);
      n.el.classList.toggle('is-dim', !!(query || filter) && !keep.has(n));
    });
    $('mmFound').textContent = query || filter ? `найдено: ${hits.length}` : '';
    layout();
    return hits;
  }
  let timer = 0;
  $('mmSearch').addEventListener('input', e => {
    clearTimeout(timer);
    timer = setTimeout(() => { query = norm(e.target.value.trim()); const hits = refilter(); if (query && hits.length === 1) select(hits[0], true); }, 160);
  });
  $('mmSearch').addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    query = norm(e.target.value.trim());
    const hits = refilter();
    if (hits.length) select(hits[0], true);
  });
  document.querySelectorAll('.mm-tile[data-filter]').forEach(b => b.addEventListener('click', () => {
    filter = filter === b.dataset.filter ? '' : b.dataset.filter;
    document.querySelectorAll('.mm-tile[data-filter]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.filter === filter)));
    if (page.classList.contains('is-list')) toggleList(false);
    refilter();
    fit();
  }));
  $('mmExpand').addEventListener('click', () => setAll(true));
  $('mmCollapse').addEventListener('click', () => { nodes.forEach(n => { n.open = n.depth === 0; }); layout(); fit(); });
  $('mmZoomIn').addEventListener('click', () => zoomAt(view.clientWidth / 2, view.clientHeight / 2, 1.25));
  $('mmZoomOut').addEventListener('click', () => zoomAt(view.clientWidth / 2, view.clientHeight / 2, 1 / 1.25));
  $('mmFit').addEventListener('click', fit);
  function toggleList(on) {
    page.classList.toggle('is-list', on);
    $('mmList').setAttribute('aria-pressed', String(on));
    if (!on) { layout(false); fit(); }
  }
  $('mmList').addEventListener('click', () => toggleList(!page.classList.contains('is-list')));

  let resizeTimer = 0;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { layout(false); }, 150); });

  layout(false);
  fit();
  select(tree, false);
  window.__mindmap = { nodes: () => nodes.length, visible: () => nodes.filter(n => !n.el.hidden).length, T, select: i => select(nodes[i], true),
                       selected: () => selected && selected.title, fit };
})();
