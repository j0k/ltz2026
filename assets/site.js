/* Страница проекта Kostik — анимации на GSAP + ScrollTrigger + SplitText (файлы в assets/vendor/gsap).
   Без GSAP или при prefers-reduced-motion страница остаётся статичной и полностью читаемой. */
(function () {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const fmt = (n, d) => n.toFixed(d).replace('.', ',');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finals = () => {                                   // конечные значения без анимации
    $$('[data-count]').forEach(el => el.textContent = fmt(+el.dataset.count, +el.dataset.dec || 0));
    $$('.mt i').forEach(i => i.style.transform = 'scaleX(' + i.dataset.v + ')');
    $$('.db').forEach(db => { const a = +db.dataset.a, b = +db.dataset.b; place(db, a, b, 1); });
    $$('.rs').forEach(r => r.classList.add('on'));
    $$('.flow .fs').forEach(c => c.classList.add('on'));
  };
  function place(db, a, b, p) {                            // «было → сейчас»: точка едет от a к b
    const v = a + (b - a) * p;
    $('.pb', db).style.left = v * 100 + '%';
    $('.ln', db).style.left = a * 100 + '%';
    $('.ln', db).style.width = (b - a) * p * 100 + '%';
    $('.pb em', db).textContent = fmt(v, 2);
  }
  if (!window.gsap || !window.ScrollTrigger || reduce) { if (reduce) finals(); return; }
  document.documentElement.classList.add('js');
  gsap.registerPlugin(ScrollTrigger, window.SplitText);
  const fine = matchMedia('(hover:hover) and (pointer:fine)').matches;

  function start() {
    /* ---------- прогресс чтения, навигация ---------- */
    gsap.to('.progress i', { scaleX: 1, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: 0.2 } });

    /* ---------- курсор и магнитные кнопки ---------- */
    if (fine) {
      const dot = $('.cur'), ring = $('.cur-ring');
      const dx = gsap.quickTo(dot, 'x', { duration: .08 }), dy = gsap.quickTo(dot, 'y', { duration: .08 });
      const rx = gsap.quickTo(ring, 'x', { duration: .45, ease: 'power3' }), ry = gsap.quickTo(ring, 'y', { duration: .45, ease: 'power3' });
      addEventListener('pointermove', e => { dx(e.clientX); dy(e.clientY); rx(e.clientX); ry(e.clientY); gsap.to([dot, ring], { opacity: 1, duration: .3, overwrite: 'auto' }); });
      $$('a,button,.card,.pn').forEach(el => {
        el.addEventListener('pointerenter', () => gsap.to(ring, { scale: 1.9, borderColor: 'rgba(90,167,255,.9)', duration: .3 }));
        el.addEventListener('pointerleave', () => gsap.to(ring, { scale: 1, borderColor: 'rgba(255,255,255,.45)', duration: .3 }));
      });
      $$('.btn,.nav .go,.links a').forEach(el => {
        const k = el.classList.contains('btn') || el.classList.contains('go') ? .32 : .05;
        const x = gsap.quickTo(el, 'x', { duration: .5, ease: 'power3' }), y = gsap.quickTo(el, 'y', { duration: .5, ease: 'power3' });
        el.addEventListener('pointermove', e => { const r = el.getBoundingClientRect(); x((e.clientX - r.left - r.width / 2) * k); y((e.clientY - r.top - r.height / 2) * k); });
        el.addEventListener('pointerleave', () => { x(0); y(0); });
      });
    }
    $$('.card,.links a').forEach(el => el.addEventListener('pointermove', e => {          // подсветка под курсором
      const r = el.getBoundingClientRect(); el.style.setProperty('--mx', (e.clientX - r.left) + 'px'); el.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }));

    /* ---------- hero ---------- */
    const h1 = $('.hero h1');
    gsap.set(h1, { visibility: 'visible' });
    const intro = gsap.timeline({ defaults: { ease: 'power4.out' } });
    intro.from('.nav', { yPercent: -160, opacity: 0, duration: 1 }, 0)
      .from('.hero .eyebrow', { y: 24, opacity: 0, duration: .9 }, .1);
    SplitText.create(h1, { type: 'lines,words', mask: 'lines', autoSplit: true, onSplit: self =>
      gsap.from(self.words, { yPercent: 118, rotate: 4, duration: 1.15, stagger: .06, ease: 'power4.out', delay: .2 }) });
    intro.from('.hero .lead', { y: 36, opacity: 0, duration: 1 }, .9)
      .from('.hero .btns > *', { y: 30, opacity: 0, stagger: .1, duration: .9 }, 1.05)
      .from('.hc-in', { y: 90, rotateX: 18, rotateY: -14, scale: .86, opacity: 0, duration: 1.5, transformPerspective: 1200 }, .55)
      .from('.chip', { scale: .4, opacity: 0, stagger: .18, duration: .9, ease: 'back.out(2)' }, 1.5)
      .from('.hint', { opacity: 0, duration: 1 }, 2);
    gsap.to('.b1', { x: '9vw', y: '8vh', duration: 9, repeat: -1, yoyo: true, ease: 'sine.inOut' });
    gsap.to('.b2', { x: '-8vw', y: '10vh', duration: 11, repeat: -1, yoyo: true, ease: 'sine.inOut' });
    gsap.to('.b3', { x: '6vw', y: '-9vh', duration: 10, repeat: -1, yoyo: true, ease: 'sine.inOut' });
    const box = $('.dots');
    for (let i = 0; i < 48; i++) {
      const d = document.createElement('i'); d.style.left = gsap.utils.random(0, 100) + '%'; d.style.top = gsap.utils.random(0, 100) + '%';
      box.appendChild(d);
      gsap.to(d, { x: 'random(-50,50)', y: 'random(-70,70)', opacity: 'random(.1,.75)', duration: 'random(4,9)', repeat: -1, yoyo: true, ease: 'sine.inOut' });
    }
    if (fine) {
      const card = $('.hc-in'), rY = gsap.quickTo(card, 'rotationY', { duration: .8, ease: 'power3' }), rX = gsap.quickTo(card, 'rotationX', { duration: .8, ease: 'power3' });
      const bx = gsap.quickTo('.b1', 'xPercent', { duration: 1.6 }), by = gsap.quickTo('.b2', 'yPercent', { duration: 1.6 });
      $('.hero').addEventListener('pointermove', e => {
        const nx = e.clientX / innerWidth - .5, ny = e.clientY / innerHeight - .5;
        rY(nx * 16); rX(-ny * 12); bx(nx * 22); by(ny * 22);
      });
    }
    gsap.to('.hero-in', { yPercent: -14, opacity: .1, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true } });
    gsap.to('.hero .gridbg', { yPercent: 25, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true } });

    /* ---------- бегущая строка: скорость и направление зависят от прокрутки ---------- */
    const mt = $('.marq-t'); mt.innerHTML += mt.innerHTML;
    const mtw = gsap.to(mt, { xPercent: -50, ease: 'none', duration: 46, repeat: -1 });
    ScrollTrigger.create({ start: 0, end: 'max', onUpdate: s => {
      const dir = s.direction, boost = 1 + Math.min(Math.abs(s.getVelocity()) / 260, 9);
      gsap.to(mtw, { timeScale: dir * boost, duration: .25, overwrite: true });
      gsap.to(mtw, { timeScale: dir, duration: 1.2, delay: .25 });
    } });

    /* ---------- заголовки разделов ---------- */
    $$('h2.rv').forEach(h => {
      gsap.set(h, { visibility: 'visible' });
      SplitText.create(h, { type: 'lines,words', mask: 'lines', autoSplit: true, onSplit: self =>
        gsap.from(self.words, { yPercent: 115, rotate: 3, duration: 1, stagger: .05, ease: 'power4.out', scrollTrigger: { trigger: h, start: 'top 86%' } }) });
    });
    $$('.sec .eyebrow').forEach(e => gsap.from(e, { x: -30, opacity: 0, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: e, start: 'top 90%' } }));
    $$('.sub').forEach(e => gsap.from(e, { y: 30, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: e, start: 'top 90%' } }));

    /* ---------- задача: слова проявляются по мере прокрутки ---------- */
    const big = $('.big');
    if (big) SplitText.create(big, { type: 'words', wordsClass: 'w', autoSplit: true, onSplit: self =>
      gsap.to(self.words, { opacity: 1, stagger: .12, ease: 'none', scrollTrigger: { trigger: big, start: 'top 82%', end: 'bottom 46%', scrub: true } }) });
    $$('.cards').forEach(c => gsap.from($$('.card', c), { y: 80, opacity: 0, stagger: .13, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: c, start: 'top 86%' } }));

    /* ---------- адаптивные сцены ---------- */
    const mm = gsap.matchMedia();
    mm.add('(min-width: 900px)', () => {
      // денситометрия: карточки ложатся стопкой
      const st = $$('.stack .st');
      st.forEach((c, i) => {
        gsap.from(c.querySelector('.n'), { yPercent: 30, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: c, start: 'top 80%' } });
        if (st[i + 1]) gsap.to(c, { scale: .9, opacity: .32, ease: 'none', scrollTrigger: { trigger: st[i + 1], start: 'top 82%', end: 'top 24%', scrub: true } });
      });
      // снимки: горизонтальная прокрутка с закреплением
      const track = $('.hs-track'), hs = $('.hs');
      if (track && hs) {
        const dist = () => Math.max(track.scrollWidth - innerWidth, 0);
        const tween = gsap.to(track, { x: () => -dist(), ease: 'none', scrollTrigger: { trigger: hs, pin: true, scrub: .7, start: 'top top', end: () => '+=' + dist(), invalidateOnRefresh: true, anticipatePin: 1 } });
        gsap.to('.hs-bar i', { scaleX: 1, ease: 'none', scrollTrigger: { trigger: hs, start: 'top top', end: () => '+=' + dist(), scrub: true, invalidateOnRefresh: true } });
        $$('.pn').forEach(p => {
          const img = $('img', p);
          gsap.fromTo(img, { xPercent: -6, scale: 1.16 }, { xPercent: 6, scale: 1.16, ease: 'none', scrollTrigger: { trigger: p, containerAnimation: tween, start: 'left right', end: 'right left', scrub: true } });
          gsap.from($('.cap', p), { y: 40, opacity: 0, duration: .8, ease: 'power3.out', scrollTrigger: { trigger: p, containerAnimation: tween, start: 'left 78%' } });
        });
      }
    });
    mm.add('(max-width: 899px)', () => {
      $$('.pn,.hs-intro,.hs-out').forEach(el => gsap.from(el, { y: 60, opacity: 0, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: el, start: 'top 88%' } }));
    });

    /* ---------- роудмап: линия рисуется, шаги вспыхивают ---------- */
    gsap.to('.rm-line i', { scaleY: 1, ease: 'none', scrollTrigger: { trigger: '.rm', start: 'top 60%', end: 'bottom 62%', scrub: true } });
    $$('.rs').forEach((r, i) => {
      ScrollTrigger.create({ trigger: r, start: 'top 62%', onEnter: () => r.classList.add('on'), onLeaveBack: () => r.classList.remove('on') });
      const wide = innerWidth > 900;
      gsap.from($('.bx', r), { x: wide ? (i % 2 ? 110 : -110) : 0, y: wide ? 0 : 50, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: r, start: 'top 84%' } });
      gsap.from($$('li', r), { x: -18, opacity: 0, stagger: .09, duration: .6, ease: 'power2.out', scrollTrigger: { trigger: r, start: 'top 76%' } });
    });
    // было → сейчас: точка едет по шкале
    $$('.db').forEach(db => {
      const a = +db.dataset.a, b = +db.dataset.b, s = { p: 0 };
      place(db, a, b, 0);
      gsap.to(s, { p: 1, ease: 'none', onUpdate: () => place(db, a, b, s.p), scrollTrigger: { trigger: db, start: 'top 88%', end: 'top 48%', scrub: .6 } });
    });
    gsap.from('.chart', { y: 70, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.chart', start: 'top 88%' } });

    /* ---------- решение ---------- */
    const chips = $$('.flow .fs');
    if (chips.length) ScrollTrigger.create({ trigger: '.flow', start: 'top 80%', end: 'bottom 38%', scrub: true,
      onUpdate: s => { const n = Math.round(s.progress * chips.length); chips.forEach((c, i) => c.classList.toggle('on', i < n)); } });
    gsap.from('.flow > *', { y: 24, opacity: 0, stagger: .06, duration: .7, ease: 'power3.out', scrollTrigger: { trigger: '.flow', start: 'top 88%' } });
    gsap.from('pre .ln', { x: -34, opacity: 0, stagger: .2, duration: .8, ease: 'power3.out', scrollTrigger: { trigger: 'pre', start: 'top 88%' } });

    /* ---------- результаты ---------- */
    $$('[data-count]').forEach(el => {
      const v = +el.dataset.count, d = +el.dataset.dec || 0, s = { v: 0 };
      el.textContent = fmt(0, d);
      gsap.to(s, { v, duration: 2, ease: 'power2.out', onUpdate: () => el.textContent = fmt(s.v, d), scrollTrigger: { trigger: el, start: 'top 90%', once: true } });
    });
    gsap.from('.stat', { y: 70, scale: .94, opacity: 0, stagger: .12, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.stats', start: 'top 86%' } });
    gsap.from('tbody tr', { y: 26, opacity: 0, stagger: .1, duration: .7, ease: 'power2.out', scrollTrigger: { trigger: 'table', start: 'top 86%' } });
    $$('.mt i').forEach(i => gsap.to(i, { scaleX: +i.dataset.v, duration: 1.5, ease: 'power3.out', scrollTrigger: { trigger: i, start: 'top 94%', once: true } }));

    /* ---------- команда ---------- */
    $$('.team-big span').forEach(s => SplitText.create(s, { type: 'chars', autoSplit: true, onSplit: self =>
      gsap.from(self.chars, { yPercent: () => gsap.utils.random(-140, 140), rotate: () => gsap.utils.random(-25, 25), opacity: 0, stagger: { each: .03, from: 'random' }, duration: 1.1, ease: 'expo.out', scrollTrigger: { trigger: s, start: 'top 88%' } }) }));
    gsap.from('.links a', { y: 60, opacity: 0, stagger: .09, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: '.links', start: 'top 88%' } });
    gsap.from('.qf', { y: 60, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.qf', start: 'top 94%' } });

    // подсветка пункта меню: создаётся последней, чтобы учесть сдвиг страницы закреплённой секцией «Снимки»
    $$('.nav a.l').forEach(a => {
      const sec = $(a.getAttribute('href'));
      if (sec) ScrollTrigger.create({ trigger: sec, start: 'top 55%', end: 'bottom 55%', onToggle: s => a.classList.toggle('on', s.isActive) });
    });

    // высота секций зависит от картинок: пересчитать позиции, когда они загрузятся
    $$('img').forEach(img => { if (!img.complete) img.addEventListener('load', () => ScrollTrigger.refresh(), { once: true }); });
    addEventListener('load', () => ScrollTrigger.refresh());
  }
  (document.fonts && document.fonts.ready ? Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 1800))]) : Promise.resolve()).then(start);
})();
