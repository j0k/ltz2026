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
