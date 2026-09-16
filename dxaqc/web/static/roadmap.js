// Роудмап: выбор инициативы, стрелки зависимостей и рекомендуемого пути, фильтр по направлению.
(function () {
  const board = document.getElementById('rmBoard'), svg = document.getElementById('rmArrows');
  const panel = document.getElementById('rmPanel'), raw = document.getElementById('rmData');
  if (!board || !svg || !panel || !raw) return;
  const data = JSON.parse(raw.textContent);
  const byId = Object.fromEntries(data.items.map(i => [i.id, i]));
  const dirs = Object.fromEntries(data.directions.map(d => [d.id, d]));
  const phases = Object.fromEntries(data.phases.map(p => [p.id, p]));
  const pathBtn = document.getElementById('rmPath');
  let selected = null, pathOn = true;

  const card = id => document.getElementById('rm-' + id);
  const NS = 'http://www.w3.org/2000/svg';

  function link(src, dst, cls) {
    const a = card(src), b = card(dst);
    if (!a || !b || a.offsetParent === null || b.offsetParent === null) return;
    const base = board.getBoundingClientRect(), ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    let x1, y1, x2, y2;
    if (rb.left >= ra.right - 4) {            // цель правее: от правого края к левому
      x1 = ra.right - base.left; y1 = ra.top + ra.height / 2 - base.top;
      x2 = rb.left - base.left - 2; y2 = rb.top + rb.height / 2 - base.top;
    } else if (rb.right <= ra.left + 4) {     // цель левее
      x1 = ra.left - base.left; y1 = ra.top + ra.height / 2 - base.top;
      x2 = rb.right - base.left + 2; y2 = rb.top + rb.height / 2 - base.top;
    } else {                                   // в одной колонке: сверху вниз или снизу вверх
      const down = rb.top > ra.top;
      x1 = ra.left + ra.width * 0.82 - base.left; y1 = (down ? ra.bottom : ra.top) - base.top;
      x2 = rb.left + rb.width * 0.82 - base.left; y2 = (down ? rb.top - 2 : rb.bottom + 2) - base.top;
    }
    const dx = Math.max(30, Math.abs(x2 - x1) / 2), vertical = Math.abs(x2 - x1) < 8;
    const d = vertical ? `M${x1},${y1} C${x1 + 26},${y1 + (y2 - y1) / 3} ${x2 + 26},${y2 - (y2 - y1) / 3} ${x2},${y2}`
      : `M${x1},${y1} C${x1 + Math.sign(x2 - x1) * dx},${y1} ${x2 - Math.sign(x2 - x1) * dx},${y2} ${x2},${y2}`;
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('d', d); p.setAttribute('class', cls);
    p.setAttribute('marker-end', cls === 'dep' ? 'url(#rm-ah-dep)' : 'url(#rm-ah)');
    svg.appendChild(p);
  }

  function draw() {
    svg.querySelectorAll('path:not(marker path)').forEach(p => { if (!p.closest('marker')) p.remove(); });
    if (pathOn) for (let i = 1; i < data.path.length; i++) link(data.path[i - 1], data.path[i], 'path');
    if (selected) {
      byId[selected].deps.forEach(dep => link(dep, selected, 'dep'));
      byId[selected].blocks.forEach(b => link(selected, b, 'blk'));
    }
  }

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  function chips(ids, title) {
    if (!ids.length) return null;
    const box = document.createDocumentFragment();
    box.appendChild(el('h3', null, title));
    const row = el('div', 'rm-links');
    ids.forEach(id => {
      const b = el('button', null, byId[id].title); b.type = 'button';
      b.addEventListener('click', () => select(id, true));
      row.appendChild(b);
    });
    box.appendChild(row);
    return box;
  }

  function render(it) {
    panel.innerHTML = '';
    panel.appendChild(el('h2', null, it.title));
    panel.appendChild(el('p', 'where', `${dirs[it.dir].title} · ${phases[it.phase].title} (${phases[it.phase].until})` +
      (it.step ? ` · шаг ${it.step} рекомендуемого пути` : '')));
    const dl = el('dl');
    [['статус', data.states[it.state]], ['ёмкость', `${it.size} — ${data.sizes[it.size]}`], ['агент', it.agent_text],
     ['вы', it.human_text], ['эффект', `${data.impact[it.impact].icon} ${data.impact[it.impact].label}`]].forEach(([k, v]) => {
      dl.appendChild(el('dt', null, k)); dl.appendChild(el('dd', null, v));
    });
    panel.appendChild(dl);
    panel.appendChild(el('h3', null, 'Что делаем')); panel.appendChild(el('p', null, it.what));
    panel.appendChild(el('h3', null, 'Зачем')); panel.appendChild(el('p', null, it.effect));
    if (it.risk) { panel.appendChild(el('h3', null, 'Риск')); panel.appendChild(el('p', 'rm-risk', it.risk)); }
    const deps = chips(it.deps, 'Сначала нужно'); if (deps) panel.appendChild(deps);
    const blocks = chips(it.blocks, 'Открывает дорогу'); if (blocks) panel.appendChild(blocks);
    if (it.tickets.length) {
      panel.appendChild(el('h3', null, 'Тикеты'));
      const row = el('p');
      it.tickets.forEach(t => {
        const a = el('a', 'rm-ticket ' + (t.closed === true ? 'closed' : t.closed === false ? 'open' : 'unknown'));
        a.href = data.trac_url + 'ticket/' + t.id; a.target = '_blank'; a.rel = 'noopener';
        a.appendChild(el('i')); a.appendChild(document.createTextNode(`#${t.id} ` +
          (t.closed === true ? 'закрыт' : t.closed === false ? 'открыт' : '')));
        row.appendChild(a);
      });
      panel.appendChild(row);
    }
  }

  function select(id, scroll) {
    if (!byId[id]) return;
    selected = id;
    document.querySelectorAll('.rm-card').forEach(c => c.setAttribute('aria-pressed', String(c.dataset.id === id)));
    render(byId[id]);
    draw();
    if (scroll) card(id).scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    history.replaceState(null, '', '#' + id);
  }

  document.querySelectorAll('.rm-card').forEach(c => c.addEventListener('click', () => select(c.dataset.id)));

  function setPath(on) {
    pathOn = on;
    pathBtn.setAttribute('aria-pressed', String(on));
    document.querySelectorAll('.rm-card.on-path').forEach(c => c.classList.toggle('path-mode', on));
    board.classList.toggle('path-mode', on);
    draw();
  }
  pathBtn.addEventListener('click', () => setPath(!pathOn));

  document.querySelectorAll('.rm-chip[data-dir]').forEach(chip => chip.addEventListener('click', () => {
    const active = chip.getAttribute('aria-pressed') === 'true';
    document.querySelectorAll('.rm-chip[data-dir]').forEach(c => c.setAttribute('aria-pressed', 'false'));
    const dir = active ? null : chip.dataset.dir;
    if (dir) chip.setAttribute('aria-pressed', 'true');
    document.querySelectorAll('.rm-lane,.rm-cell').forEach(e => e.classList.toggle('dim', !!dir && e.dataset.dir !== dir));
    draw();
  }));

  let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(draw, 120); });
  setPath(true);
  const hash = location.hash.slice(1);
  if (byId[hash]) select(hash, true);
})();
