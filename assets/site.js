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

    /* ---------- роудмап: у каждого этапа своя сцена, закреплённая на экране и управляемая прокруткой ---------- */
    const stages = $$('.rmx');
    stages.forEach(st => {
      const h = $('h3', st);
      SplitText.create(h, { type: 'lines,words', mask: 'lines', autoSplit: true, onSplit: self =>
        gsap.from(self.words, { yPercent: 115, rotate: 3, duration: .9, stagger: .05, ease: 'power4.out', scrollTrigger: { trigger: st, start: 'top 72%' } }) });
      gsap.from($$('.rmx-meta > *, .tags > *', st), { y: 26, opacity: 0, stagger: .08, duration: .7, ease: 'power3.out', scrollTrigger: { trigger: st, start: 'top 72%' } });
      gsap.from($$('li', st), { x: -22, opacity: 0, stagger: .1, duration: .7, ease: 'power2.out', scrollTrigger: { trigger: st, start: 'top 62%' } });
      gsap.from($$('.algos a', st), { y: 16, opacity: 0, stagger: .05, duration: .6, ease: 'power3.out', scrollTrigger: { trigger: st, start: 'top 55%' } });
      gsap.fromTo($('.ghost', st), { yPercent: -44, opacity: .2 }, { yPercent: -56, opacity: .7, ease: 'none', scrollTrigger: { trigger: st, start: 'top bottom', end: 'bottom top', scrub: true } });
    });
    const SCENES = [
      (st, tl) => {                                                        // 1 · терминал: команды печатаются, деплой заполняется
        tl.fromTo($$('.term .ln', st), { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', stagger: .11, duration: .11 }, 0.04)
          .to($('.dp i', st), { scaleX: 1, duration: .32 }, 0.42)
          .fromTo($('.live', st), { scale: .3, opacity: 0 }, { scale: 1, opacity: 1, duration: .12, ease: 'back.out(2.4)' }, 0.78);
      },
      (st, tl) => {                                                        // 2 · 499 квадратов схлопываются в 252
        const grid = $('.dgrid', st); grid.innerHTML = '';
        const dots = Array.from({ length: 499 }, () => grid.appendChild(document.createElement('i')));
        const dup = new Set(gsap.utils.shuffle(dots.map((_, i) => i)).slice(0, 247));
        const dead = dots.filter((_, i) => dup.has(i)), live = dots.filter((_, i) => !dup.has(i));
        const n = { v: 499 }, out = $('.dn', st); out.textContent = 499;
        tl.to(live, { backgroundColor: getComputedStyle(st).getPropertyValue('--c').trim(), stagger: { amount: .25, from: 'random' }, duration: .05 }, 0.12)
          .to(dead, { scale: 0, opacity: 0, stagger: { amount: .42, from: 'random' }, duration: .1 }, 0.34)
          .to(n, { v: 252, duration: .42, onUpdate: () => out.textContent = Math.round(n.v) }, 0.34)
          .from($('.dd .cap', st), { opacity: 0, y: 14, duration: .1 }, 0.8);
      },
      (st, tl) => {                                                        // 3 · чужие файлы получают понятный ответ, ошибки 135 → 0
        const rows = $$('.rb', st), n = { v: 135 }, en = $('.en', st); en.textContent = 135;
        rows.forEach((r, i) => {
          const at = 0.04 + i * .14;
          tl.from($('.ch', r), { x: -50, opacity: 0, duration: .09 }, at).from($('.ar2', r), { scaleX: 0, duration: .07 }, at + .07)
            .from($('.pl', r), { scale: .7, opacity: 0, duration: .09, ease: 'back.out(2)' }, at + .12);
        });
        tl.to(n, { v: 0, duration: .5, onUpdate: () => { en.textContent = Math.round(n.v); if (n.v < 1) en.style.color = 'var(--ok)'; else en.style.color = ''; } }, 0.3);
      },
      (st, tl) => {                                                        // 4 · кривые ROC рисуются, AUC растёт 0,55 → 0,85
        const p1 = $('.r1', st), p2 = $('.r2', st), l1 = p1.getTotalLength(), l2 = p2.getTotalLength(), a = { v: .55 }, an = $('.an', st); an.textContent = '0,55';
        gsap.set(p1, { strokeDasharray: l1, strokeDashoffset: l1 }); gsap.set(p2, { strokeDasharray: l2, strokeDashoffset: l2 });
        tl.to(p1, { strokeDashoffset: 0, duration: .3 }, 0.04)
          .to(p2, { strokeDashoffset: 0, duration: .42 }, 0.36)
          .to($('.ra', st), { opacity: 1, duration: .2 }, 0.62)
          .to(a, { v: .85, duration: .42, onUpdate: () => an.textContent = fmt(a.v, 2) }, 0.36)
          .fromTo($('.roc svg', st), { scale: 1 }, { scale: 1.035, yoyo: true, repeat: 1, duration: .04, transformOrigin: '50% 50%' }, 0.86);
      },
      (st, tl) => {                                                        // 5 · три пакета падают в коробку, шкала AUC бедра заполняется
        const ga = $('.ga', st), len = ga.getTotalLength(), g = { v: 0 }, gn = $('.gn', st); gn.textContent = '0,00';
        gsap.set(ga, { strokeDasharray: len, strokeDashoffset: len });
        tl.from($$('.t', st), { yPercent: -260, opacity: 0, stagger: .1, duration: .14, ease: 'bounce.out' }, 0.05)
          .to($$('.t', st), { yPercent: 190, opacity: 0, stagger: .05, duration: .12 }, 0.36)
          .from($('.lid', st), { yPercent: -70, opacity: 0, duration: .1 }, 0.5)
          .to(ga, { strokeDashoffset: len * (1 - .66), duration: .42 }, 0.36)
          .to(g, { v: .66, duration: .42, onUpdate: () => gn.textContent = fmt(g.v, 2) }, 0.36);
      },
      (st, tl) => {                                                        // 6 · гипотезы против границы 0,66 и доверительного интервала
        tl.from($('.band', st), { opacity: 0, scaleY: 0, transformOrigin: '50% 100%', duration: .16 }, 0.03)
          .from($('.base', st), { scaleY: 0, transformOrigin: '50% 100%', duration: .14 }, 0.08);
        $$('.hr', st).forEach((r, i) => {
          const at = .24 + i * .28;
          tl.from($('b', r), { opacity: 0, y: 12, duration: .08 }, at).from($('.bar i', r), { scaleX: 0, duration: .22 }, at + .04)
            .from($('.bar em', r), { opacity: 0, x: -14, duration: .08 }, at + .2).from($('.vd', r), { scale: .6, opacity: 0, duration: .1, ease: 'back.out(2)' }, at + .24);
        });
      },
      (st, tl) => {                                                        // 7 · чек-лист закрывается, конфетти
        const items = $$('.ck li', st), fin = $('.fin', st), conf = $('.conf', st);
        conf.innerHTML = '';
        const cols = ['#ff5a5f', '#ffb84d', '#5aa7ff', '#3fe0b0', '#a78bfa', '#fff'];
        const bits = Array.from({ length: 70 }, () => { const i = document.createElement('i'); i.style.background = gsap.utils.random(cols); conf.appendChild(i); return i; });
        let fired = false;
        const burst = () => { if (fired) return; fired = true;
          gsap.fromTo(bits, { x: 0, y: 0, opacity: 1, rotation: 0, scale: 1 }, { x: () => gsap.utils.random(-320, 320), y: () => gsap.utils.random(-300, 60), rotation: () => gsap.utils.random(-540, 540), opacity: 0, duration: 1.8, ease: 'power3.out', stagger: .004,
            }); };
        items.forEach((li, i) => tl.from($('i', li), { scale: .4, duration: .06, ease: 'back.out(3)' }, 0.06 + i * .11));
        tl.fromTo(fin, { scale: .6, opacity: 0 }, { scale: 1, opacity: 1, duration: .14, ease: 'back.out(2.4)' }, 0.72);
        // отметки и конфетти считаем по прогрессу, а не колбэками: при быстрой прокрутке колбэки теряются
        tl.eventCallback('onUpdate', () => {
          const p = tl.progress();
          items.forEach((li, i) => li.classList.toggle('done', p >= .06 + i * .11));
          if (p >= .8) burst(); else if (p < .7) fired = false;
        });
      }
    ];
    const mm2 = gsap.matchMedia();
    mm2.add('(min-width: 900px) and (min-height: 680px)', () => {
      stages.forEach((st, i) => {
        const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: st, start: 'top top', end: '+=110%', pin: true, scrub: .6, anticipatePin: 1 } });
        SCENES[i](st, tl); tl.to({}, { duration: .12 }, 0.9);
      });
    });
    mm2.add('(max-width: 899px), (max-height: 679px)', () => {
      stages.forEach((st, i) => {
        const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: $('.rmx-viz', st), start: 'top 82%', end: 'bottom 48%', scrub: .5 } });
        SCENES[i](st, tl);
      });
    });
    // было → сейчас: точка едет по шкале
    $$('.db').forEach(db => {
      const a = +db.dataset.a, b = +db.dataset.b, s = { p: 0 };
      place(db, a, b, 0);
      gsap.to(s, { p: 1, ease: 'none', onUpdate: () => place(db, a, b, s.p), scrollTrigger: { trigger: db, start: 'top 88%', end: 'top 48%', scrub: .6 } });
    });
    gsap.from('.chart', { y: 70, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.chart', start: 'top 88%' } });

    /* ---------- алгоритмы: столбцы растут, линия «нашей модели» выезжает, карточки появляются ---------- */
    $$('.ab').forEach(r => {
      const bar = $('.ab-t i', r), num = $('b', r), v = +r.dataset.v, o = { v: 0.5 };
      gsap.from(bar, { scaleX: 0, duration: 1.3, ease: 'power3.out', scrollTrigger: { trigger: r, start: 'top 92%', once: true } });
      gsap.to(o, { v, duration: 1.3, ease: 'power3.out', onUpdate: () => num.textContent = fmt(o.v, Math.round(v * 1000) % 10 ? 3 : 2), scrollTrigger: { trigger: r, start: 'top 92%', once: true } });
    });
    gsap.from('.al-line', { scaleY: 0, transformOrigin: '50% 100%', duration: .9, delay: .5, ease: 'power3.out', scrollTrigger: { trigger: '.al-bars', start: 'top 85%', once: true } });
    gsap.from('.al-chart', { y: 60, opacity: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.al-chart', start: 'top 90%' } });
    gsap.from('.al-grid .al', { y: 60, opacity: 0, stagger: .05, duration: .8, ease: 'power3.out', scrollTrigger: { trigger: '.al-grid', start: 'top 88%', once: true }, clearProps: 'transform' });

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

    /* ---------- «Развитие», пятый пункт: подход за подходом — шаги зажигаются по кругу, пока блок на экране ---------- */
    const rounds = $('.rounds');
    if (rounds) {
      const steps = $$('.rd-step', rounds);
      gsap.from(steps, { y: 40, opacity: 0, stagger: .14, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: rounds, start: 'top 84%' } });
      gsap.from($('.rd-loop', rounds), { opacity: 0, duration: 1, delay: .5, scrollTrigger: { trigger: rounds, start: 'top 80%' } });
      const loop = gsap.timeline({ repeat: -1, paused: true });
      steps.forEach((st, i) => loop.call(() => steps.forEach((x, k) => x.classList.toggle('on', k === i)), null, i * 1.5));
      loop.to({}, { duration: steps.length * 1.5 });
      ScrollTrigger.create({ trigger: rounds, start: 'top 85%', end: 'bottom 10%', onToggle: s => s.isActive ? loop.play() : loop.pause() });
    }

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
    ScrollTrigger.sort();                                   // порядок как на странице: закреплённые сцены сдвигают всё, что ниже них
    ScrollTrigger.refresh();
    addEventListener('load', () => { ScrollTrigger.sort(); ScrollTrigger.refresh(); });
  }
  (document.fonts && document.fonts.ready ? Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 1800))]) : Promise.resolve()).then(start);
})();
