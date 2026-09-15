// Диаграмма Ганта: линейка дат, масштаб, сворачивание эпиков и фильтр незакрытых.
(function () {
  const chart = document.getElementById('gtChart');
  if (!chart) return;
  const inner = chart.querySelector('.gt-inner'), lane = chart.querySelector('.gt-ruler-lane');
  const start = +chart.dataset.start * 1000, end = +chart.dataset.end * 1000;
  const MSK = 3 * 3600 * 1000, DAY = 86400000, MONTHS = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
  let perDay = +(localStorage.getItem('dxaqc-gantt-zoom') || 0) || 26;

  const span = Math.max(end - start, DAY);
  const pct = t => (t - start) / span * 100;

  function ruler() {
    lane.innerHTML = '';
    const days = Math.round(span / DAY), step = perDay >= 22 ? 1 : perDay >= 12 ? 2 : 4;
    let month = -1;
    for (let i = 0; i <= days; i++) {
      const t = start + i * DAY, d = new Date(t + MSK), left = pct(t);
      const line = document.createElement('div');
      line.className = 'gt-grid-line' + (d.getUTCDate() === 1 ? ' month' : '');
      line.style.left = left + '%';
      if (d.getUTCDate() === 1 || i % step === 0) lane.appendChild(line);
      if (d.getUTCMonth() !== month) {
        month = d.getUTCMonth();
        const m = document.createElement('div');
        m.className = 'gt-month'; m.style.left = 'calc(' + left + '% + 6px)';
        m.textContent = MONTHS[month];
        lane.appendChild(m);
      }
      if (i % step) continue;
      const day = document.createElement('div');
      const weekend = d.getUTCDay() === 0 || d.getUTCDay() === 6;
      day.className = 'gt-day' + (weekend ? ' weekend' : '');
      day.style.left = left + '%';
      day.textContent = d.getUTCDate();
      lane.appendChild(day);
    }
  }

  function zoom(next) {
    perDay = Math.max(6, Math.min(80, next));
    try { localStorage.setItem('dxaqc-gantt-zoom', perDay); } catch (e) {}
    const label = parseInt(getComputedStyle(inner).getPropertyValue('--label')) || 300;
    inner.style.setProperty('--track', (label + Math.round(span / DAY * perDay)) + 'px');
    ruler();
  }

  chart.querySelectorAll('.gt-toggle').forEach(btn => btn.addEventListener('click', () => {
    const open = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!open));
    chart.querySelectorAll('.gt-row.task[data-of="' + btn.dataset.epic + '"]').forEach(r => { r.hidden = open; });
  }));

  function all(open) {
    chart.querySelectorAll('.gt-toggle').forEach(b => b.setAttribute('aria-expanded', String(open)));
    chart.querySelectorAll('.gt-row.task').forEach(r => { r.hidden = !open; });
  }
  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
  on('gtExpand', () => all(true));
  on('gtCollapse', () => all(false));
  on('gtZoomIn', () => zoom(Math.round(perDay * 1.35)));
  on('gtZoomOut', () => zoom(Math.round(perDay / 1.35)));
  on('gtToday', () => {
    const line = chart.querySelector('.gt-today');
    if (line) chart.querySelector('.gt-wrap').scrollLeft = line.offsetLeft - chart.clientWidth / 2;
  });
  on('gtOpenOnly', e => {
    const btn = e.currentTarget, pressed = btn.getAttribute('aria-pressed') === 'true';
    btn.setAttribute('aria-pressed', String(!pressed));
    chart.querySelectorAll('.gt-row[data-done="1"]').forEach(r => r.classList.toggle('hidden', !pressed));
  });

  zoom(perDay);
  const today = chart.querySelector('.gt-today'), wrap = chart.querySelector('.gt-wrap');
  if (today && wrap) wrap.scrollLeft = Math.max(0, today.offsetLeft - wrap.clientWidth * 0.6);
})();
