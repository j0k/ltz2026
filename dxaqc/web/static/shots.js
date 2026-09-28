// Галерея скриншотов: смена слайдов по таймеру с прогрессом на точке, пауза при наведении, фокусе,
// скрытой вкладке и по кнопке; свайп и стрелки. prefers-reduced-motion — без автопролистывания.
(function () {
  const root = document.getElementById('shots');
  if (!root) return;
  const slides = [...root.querySelectorAll('.sh-slide')], caps = [...root.querySelectorAll('.sh-text')];
  const dots = [...root.querySelectorAll('.sh-dots [role=tab]')], play = root.querySelector('.sh-play');
  const DELAY = 5500, calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = 0, timer = null, hold = false, user = calm;

  function load(i) {
    const img = slides[i] && slides[i].querySelector('img[data-src]');
    if (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); }
  }
  function show(i) {
    i = (i + slides.length) % slides.length;
    slides.forEach((s, k) => { s.classList.toggle('on', k === i); s.setAttribute('aria-hidden', k === i ? 'false' : 'true'); });
    caps.forEach((c, k) => c.classList.toggle('on', k === i));
    dots.forEach((d, k) => { d.setAttribute('aria-selected', k === i ? 'true' : 'false'); d.classList.remove('run'); });
    cur = i; load(i); load(i + 1);
    arm();
  }
  function arm() {
    clearTimeout(timer);
    const d = dots[cur];
    d.classList.remove('run'); void d.offsetWidth;          // перезапуск анимации прогресса
    if (user || hold || document.hidden) { root.classList.add('paused'); return; }
    root.classList.remove('paused'); d.classList.add('run');
    timer = setTimeout(() => show(cur + 1), DELAY);
  }
  function setUser(v) { user = v; play.dataset.state = v ? 'pause' : 'play'; play.textContent = v ? '▶' : '❚❚';
    play.setAttribute('aria-label', v ? 'листать автоматически' : 'пауза'); arm(); }

  root.querySelector('.prev').onclick = () => show(cur - 1);
  root.querySelector('.next').onclick = () => show(cur + 1);
  dots.forEach((d, k) => d.onclick = () => show(k));
  play.onclick = () => setUser(!user);
  root.addEventListener('mouseenter', () => { hold = true; arm(); });
  root.addEventListener('mouseleave', () => { hold = false; arm(); });
  root.addEventListener('focusin', () => { hold = true; arm(); });
  root.addEventListener('focusout', (e) => { if (!root.contains(e.relatedTarget)) { hold = false; arm(); } });
  document.addEventListener('visibilitychange', arm);
  root.addEventListener('keydown', (e) => { if (e.key === 'ArrowLeft') show(cur - 1); if (e.key === 'ArrowRight') show(cur + 1); });
  let x0 = null;
  root.addEventListener('touchstart', (e) => { x0 = e.touches[0].clientX; hold = true; arm(); }, { passive: true });
  root.addEventListener('touchend', (e) => {
    const dx = e.changedTouches[0].clientX - (x0 ?? 0); hold = false;
    if (Math.abs(dx) > 40) show(cur + (dx < 0 ? 1 : -1)); else arm();
  });
  if (calm) setUser(true);
  // слайды грузим, только когда галерея видна
  new IntersectionObserver((es, ob) => { if (es.some(e => e.isIntersecting)) { load(1); ob.disconnect(); } }).observe(root);
  show(0);
})();
