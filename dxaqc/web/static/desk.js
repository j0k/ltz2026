// Настольное приложение: мост к системным диалогам (pywebview) и сигнал «окно живо» для режима браузера.
(function () {
  const DX = window.DXAQC = window.DXAQC || {};
  DX.native = () => !!(window.pywebview && window.pywebview.api);
  function ready(fn) { if (DX.native()) fn(); else window.addEventListener('pywebviewready', fn, {once: true}); }
  DX.ready = ready;
  // выбрать файлы или папку в системном диалоге и сразу проверить — без копирования через браузер
  DX.pick = async function (kind) {
    if (!DX.native()) return false;
    const paths = kind === 'folder' ? await pywebview.api.pick_folder() : await pywebview.api.pick_files();
    if (!paths || !paths.length) return true;
    DX.busy && DX.busy('Готовлю файлы к проверке…');
    const r = await fetch('/desktop/run-local', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({paths})});
    const j = await r.json().catch(() => ({}));
    if (r.ok && j.url) location.href = j.url; else alert(j.detail || 'Не получилось открыть файлы');
    return true;
  };
  // скачивание результатов: в окне приложения — системный диалог «Сохранить как»
  document.addEventListener('click', async (e) => {
    const a = e.target.closest('a[data-save]');
    if (!a || !DX.native()) return;
    e.preventDefault();
    const res = await pywebview.api.save_file(a.dataset.run, a.dataset.save);
    if (res && res.error) alert(res.error);
  });
  document.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-open-run]');
    if (!a || !DX.native()) return;
    e.preventDefault();
    await pywebview.api.open_run_folder(a.dataset.openRun);
  });
  ready(() => document.documentElement.classList.add('native'));
  // режим браузера: сервер закрывается, когда окно закрыли и сигналы перестали приходить
  const ping = () => fetch('/desktop/ping', {cache: 'no-store'}).catch(() => {});
  ping(); setInterval(ping, 15000);
})();
