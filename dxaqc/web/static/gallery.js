// Галерея: фильтры, просмотр на весь экран, листание (стрелки, клавиши, свайп) и наш анализ по кнопке.
(function () {
  const raw = document.getElementById('glData');
  if (!raw) return;
  const all = JSON.parse(raw.textContent);
  const $ = id => document.getElementById(id);
  const grid = $('glGrid'), box = $('glBox'), img = $('glImg'), panel = $('glPanel'), mode = $('glMode');
  const filters = {ds: '', ex: '', region: '', type: ''};
  const results = {};
  let list = all, idx = -1, showAtlas = false;

  const verdictOf = e => !e.labeled ? 'none' : e.bad ? 'bad' : 'ok';
  const VERDICT = {bad: ['✕', 'нарушение'], ok: ['✓', 'норма'], none: ['—', 'нет разметки']};
  const el = (tag, cls, text) => { const x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; };
  const icon = kind => { const i = el('i', 'gl-ic ' + kind, VERDICT[kind][0]); i.setAttribute('aria-hidden', 'true'); return i; };

  function apply() {
    list = all.filter(it => (!filters.ds || it.ds === filters.ds) && (!filters.ex || verdictOf(it.expert) === filters.ex)
      && (!filters.region || it.region === filters.region) && (!filters.type || (it.expert.types || []).includes(filters.type)));
    grid.innerHTML = '';
    list.forEach((it, i) => {
      const b = el('button', 'gl-tile'); b.type = 'button';
      const v = verdictOf(it.expert);
      b.setAttribute('aria-label', `${it.region_ru}, ${it.ds_title}, эксперты: ${VERDICT[v][1]}`);
      const im = el('img'); im.loading = 'lazy'; im.alt = ''; im.src = `/gallery/thumb/${it.key}.jpg`;
      b.appendChild(im);
      if (it.ds === 'test') b.appendChild(el('span', 'ds', '«Для теста»'));
      const cap = el('span', 'cap'); cap.appendChild(icon(v));
      cap.appendChild(el('span', null, it.study_no ? `№${it.study_no} · ${it.region_ru}` : it.region_ru));
      b.appendChild(cap);
      b.addEventListener('click', () => open(i));
      grid.appendChild(b);
    });
    $('glCount').textContent = `показано ${list.length} из ${all.length}`;
  }

  function section(title) { panel.appendChild(el('h3', null, title)); }

  function renderPanel(it) {
    panel.innerHTML = '';
    panel.appendChild(el('h2', null, it.region_ru.charAt(0).toUpperCase() + it.region_ru.slice(1)));
    panel.appendChild(el('p', 'where', it.study_no ? `${it.ds_title} · исследование № ${it.study_no}` : it.ds_title));

    section('Заключение экспертов');
    const e = it.expert, v = verdictOf(e);
    const vd = el('div', 'gl-verdict'); vd.appendChild(icon(v)); vd.appendChild(el('span', null, VERDICT[v][1])); panel.appendChild(vd);
    if (e.labeled && e.types_ru && e.types_ru.length) {
      const ul = el('ul'); e.types_ru.forEach(t => ul.appendChild(el('li', null, t))); panel.appendChild(ul);
    }
    if (!e.labeled) panel.appendChild(el('p', 'gl-note', it.ds === 'test' ? 'Во фрагменте «Для теста» экспертной разметки нет.'
      : 'Для этой области у исследования нет разметки.'));
    if (e.comment) panel.appendChild(el('p', 'gl-note', `Комментарий эксперта ко всему исследованию: «${e.comment}»`));

    section('Наш анализ');
    const r = results[it.key];
    if (!r) {
      const btn = el('button', 'gl-run', 'Запустить наш анализ'); btn.type = 'button';
      btn.addEventListener('click', () => run(it, btn));
      panel.appendChild(btn);
      panel.appendChild(el('p', 'gl-note', 'Текущая версия сервиса, около секунды. Клавиша R.'));
    } else {
      const kind = r.quality_class === 1 ? 'bad' : r.quality_class === 0 ? 'ok' : 'none';
      const label = r.quality_class === 1 ? 'нарушение' : r.quality_class === 0 ? 'качественный' : 'не оценено';
      const vr = el('div', 'gl-verdict'); vr.appendChild(icon(kind)); vr.appendChild(el('span', null, label)); panel.appendChild(vr);
      const shown = r.violations.filter((x, i) => r.violation_codes[i] !== 'hip_not_evaluated_v0');
      if (shown.length) { const ul = el('ul'); shown.forEach(t => ul.appendChild(el('li', null, t))); panel.appendChild(ul); }
      panel.appendChild(el('div', 'gl-agree ' + r.agreement.kind, r.agreement.text));
      if (r.explanations.length) {
        section('Пояснения');
        const ul = el('ul'); r.explanations.forEach(t => ul.appendChild(el('li', null, t))); panel.appendChild(ul);
      }
      panel.appendChild(el('p', 'gl-note', `версия ${r.version} · ${r.cached ? 'из кеша' : r.seconds.toString().replace('.', ',') + ' с'} · клавиша A — атлас`));
    }
    if (it.card) {
      const p = el('p', 'gl-links'); const a = el('a', null, 'Карточка снимка в прогоне →'); a.href = it.card; p.appendChild(a); panel.appendChild(p);
    }
  }

  async function run(it, btn) {
    btn.disabled = true; btn.textContent = 'Анализирую…';
    try {
      const resp = await fetch(`/api/gallery/${it.key}/analyze`, {method: 'POST'});
      if (!resp.ok) throw new Error(resp.status);
      results[it.key] = await resp.json();
      showAtlas = true;
    } catch (err) {
      btn.disabled = false; btn.textContent = 'Не получилось — ещё раз'; return;
    }
    if (list[idx] && list[idx].key === it.key) show(idx);
  }

  function setMode(atlas) {
    showAtlas = atlas;
    mode.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String((b.dataset.mode === 'atlas') === atlas)));
    const it = list[idx], r = results[it.key];
    img.src = atlas && r ? r.atlas : `/gallery/img/${it.key}.png`;
    img.alt = (atlas && r ? 'наш атлас: ' : 'снимок: ') + it.region_ru;
  }

  function show(i) {
    idx = (i + list.length) % list.length;
    const it = list[idx];
    $('glCounter').textContent = `${idx + 1} / ${list.length}`;
    $('glWhat').textContent = `${it.ds_title} · ${it.region_ru}`;
    mode.hidden = !results[it.key];
    setMode(showAtlas && !!results[it.key]);
    renderPanel(it);
    [idx + 1, idx - 1].forEach(j => { const n = list[(j + list.length) % list.length]; if (n) new Image().src = `/gallery/img/${n.key}.png`; });
    history.replaceState(null, '', '#g=' + it.key);
  }

  function open(i) { box.hidden = false; document.body.classList.add('gl-open'); show(i); $('glClose').focus(); }
  function close() { box.hidden = true; document.body.classList.remove('gl-open'); history.replaceState(null, '', location.pathname); }

  $('glPrev').addEventListener('click', () => show(idx - 1));
  $('glNext').addEventListener('click', () => show(idx + 1));
  $('glClose').addEventListener('click', close);
  mode.querySelectorAll('button').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode === 'atlas')));
  document.addEventListener('keydown', ev => {
    if (box.hidden || ev.target.tagName === 'SELECT') return;
    if (ev.key === 'ArrowRight') show(idx + 1);
    else if (ev.key === 'ArrowLeft') show(idx - 1);
    else if (ev.key === 'Escape') close();
    else if ((ev.key === 'a' || ev.key === 'ф') && results[list[idx].key]) setMode(!showAtlas);
    else if ((ev.key === 'r' || ev.key === 'к') && !results[list[idx].key]) { const b = panel.querySelector('.gl-run'); if (b) b.click(); }
  });
  let x0 = null;
  $('glStage').addEventListener('touchstart', ev => { x0 = ev.touches[0].clientX; }, {passive: true});
  $('glStage').addEventListener('touchend', ev => {
    if (x0 === null) return;
    const dx = ev.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1));
  });

  document.querySelectorAll('.gl-seg button').forEach(b => b.addEventListener('click', () => {
    b.parentElement.querySelectorAll('button').forEach(o => o.setAttribute('aria-pressed', String(o === b)));
    filters[b.dataset.f] = b.dataset.v; apply();
  }));
  $('glRegion').addEventListener('change', e => { filters.region = e.target.value; apply(); });
  $('glType').addEventListener('change', e => { filters.type = e.target.value; apply(); });

  apply();
  const m = location.hash.match(/g=([0-9a-f]{12})/);
  if (m) { const i = list.findIndex(it => it.key === m[1]); if (i >= 0) open(i); }
})();
