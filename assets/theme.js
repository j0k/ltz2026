/* Переключатель Modern ⇄ Classic: выбор запоминается в браузере, ссылка ?theme=classic|modern задаёт его явно. */
(function () {
  var KEY = 'ltzTheme', btn = document.querySelector('.tt');
  if (!btn) return;
  var modern = document.documentElement.getAttribute('data-theme') !== 'classic';
  btn.setAttribute('data-mode', modern ? 'modern' : 'classic');
  btn.setAttribute('aria-checked', String(modern));
  btn.addEventListener('click', function () {
    var next = modern ? 'classic' : 'modern';
    try { localStorage.setItem(KEY, next); sessionStorage.setItem('ltzArrive', '1'); } catch (e) {}
    var f = document.createElement('div'); f.className = 'tt-fade'; f.style.background = next === 'classic' ? '#f6f5f2' : '#07080d';
    document.body.appendChild(f); requestAnimationFrame(function () { f.style.opacity = 1; });
    var to = next === 'classic' ? new URL('classic.html', location.href).href : new URL('./', location.href).href;
    setTimeout(function () { location.href = to + location.hash; }, 300);
  });
})();


/* Фильтр карточек «Что мы пробовали»: работает на обеих версиях страницы, с GSAP — с плавным появлением. */
(function () {
  var tabs = document.querySelectorAll('.af'), cards = document.querySelectorAll('.al');
  if (!tabs.length) return;
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      var f = t.getAttribute('data-f'), shown = [];
      tabs.forEach(function (x) { x.setAttribute('aria-pressed', String(x === t)); });
      cards.forEach(function (c) {
        var on = f === 'all' || c.getAttribute('data-g') === f || c.getAttribute('data-v') === f;
        c.classList.toggle('hide', !on); if (on) shown.push(c);
      });
      if (window.gsap) { window.gsap.fromTo(shown, { y: 24, opacity: 0, scale: .97 }, { y: 0, opacity: 1, scale: 1, duration: .5, stagger: .035, ease: 'power3.out', overwrite: true, clearProps: 'transform' }); }
    });
  });
})();
