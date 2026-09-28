// Презентация DXA QC для ЛЦТ 2026 (задача 04), структура — по разделу 4 ТЗ и критериям раздела 8.
// Слайды 1–6 и 12+ — свободная часть; 7–11 — содержание обязательных слайдов, до получения файла шаблона
// в нейтральной вёрстке (при переносе в шаблон — только текст, сетку шаблона не менять). 3D-моделей нет: только снимки.
// Запуск: node build_deck.js → DXA_QC_presentation.pptx
const pptxgen = require('pptxgenjs');
const path = require('path');
const A = (f) => path.join(__dirname, 'assets', f);

const C = { navy: '0F1B2D', navy2: '1C2B44', blue: '2A78D6', ice: 'DCE9F8', ok: '1BAF7A', bad: 'E34948', warn: 'C98500',
            ink: '1A1F2B', ink2: '4A5263', ink3: '7C8494', card: 'F2F5F9', white: 'FFFFFF', bone: 'F3EFE7' };
const H = 'Calibri', B = 'Calibri';

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';                // 10 × 5.625 дюйма
pres.title = 'DXA QC — контроль качества денситометрии';
pres.company = 'команда «Квантовый Скачок»';

const W = 10, HH = 5.625;
const shadow = () => ({ type: 'outer', color: '000000', blur: 6, offset: 1.5, angle: 90, opacity: 0.12 });

function title(s, text, sub, dark = false) {
  s.addText(text, { x: 0.5, y: 0.32, w: 9, h: 0.62, fontFace: H, fontSize: 30, bold: true, color: dark ? C.white : C.ink, margin: 0, isTextBox: true });
  if (sub) s.addText(sub, { x: 0.5, y: 0.92, w: 9, h: 0.34, fontFace: B, fontSize: 13, color: dark ? 'B9C6DA' : C.ink3, margin: 0, isTextBox: true });
}
function num(s, n, x, y, color = C.blue) {
  s.addShape(pres.shapes.OVAL, { x, y, w: 0.42, h: 0.42, fill: { color } });
  s.addText(String(n), { x, y, w: 0.42, h: 0.42, fontFace: H, fontSize: 14, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
}
function card(s, x, y, w, h, fill = C.card) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, rectRadius: 0.12, line: { color: fill } });
}
function img(s, f, x, y, w, ratio, opts = {}) {
  s.addImage({ path: A(f), x, y, w, h: w / ratio, ...opts });
}
function pageNo(s, _n, dark = false) {
  s.addText(String(pres.slides.length), { x: 9.3, y: 5.2, w: 0.4, h: 0.25, fontFace: B, fontSize: 10, color: dark ? '6F7F99' : 'A0A6B2', align: 'right', margin: 0, isTextBox: true });
}

// ------------------------------------------------------------------ 1. Титул
{
  const s = pres.addSlide(); s.background = { color: C.navy };
  card(s, 5.35, 0.55, 4.2, 3.4, '1C2B44');
  img(s, 'atlas.png', 5.5, 0.68, 3.9, 1.314);
  s.addText('Атлас снимка поясничного отдела: позвонки Th12–L5, ось, найденный предмет (синтетический фантом)',
    { x: 5.4, y: 4.1, w: 4.1, h: 0.5, fontFace: B, fontSize: 10.5, color: '8FA3C2', margin: 0, isTextBox: true });
  s.addText('DXA QC', { x: 0.55, y: 0.95, w: 4.6, h: 0.9, fontFace: H, fontSize: 54, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText('Сервис ИИ для контроля качества снимков денситометрии', { x: 0.55, y: 1.85, w: 4.6, h: 0.9, fontFace: H, fontSize: 22, color: 'CADCFC', margin: 0, isTextBox: true });
  s.addText([
    { text: 'Поясничный отдел и бедро: область, вердикт, тип нарушения и пояснение на самом снимке.', options: { breakLine: true } },
    { text: 'Работает локально — снимки не покидают медорганизацию.' },
  ], { x: 0.55, y: 2.95, w: 4.6, h: 0.9, fontFace: B, fontSize: 14, color: 'B9C6DA', margin: 0, paraSpaceAfter: 4, isTextBox: true });
  s.addText('ЛЦТ 2026 · задача 04 Департамента здравоохранения Москвы · команда «Квантовый Скачок»',
    { x: 0.55, y: 4.75, w: 4.7, h: 0.4, fontFace: B, fontSize: 11, color: '8FA3C2', margin: 0, isTextBox: true });
  s.addNotes('Мы — команда «Квантовый Скачок». DXA QC проверяет качество снимков денситометрии сразу после исследования: область, вердикт, тип нарушения и объяснение прямо на снимке. Работает локально, без интернета.');
}

// ------------------------------------------------------------------ 2. Проблема
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Брак укладки — это неверный диагноз', 'Денситометрия — основной метод диагностики остеопороза; её результат зависит от качества снимка');
  const stats = [['32 %', 'снимков поясничного отдела в обучающем наборе — с нарушением по оценке экспертов', C.bad],
                 ['27 %', 'снимков бедра — с нарушением укладки или полей зоны интереса', C.warn],
                 ['вручную', 'и выборочно — так качество проверяют сегодня; брак находят, когда пациент уже ушёл', C.ink2]];
  stats.forEach(([big, txt, col], i) => {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.55, 2.8, 2.35);
    s.addText(big, { x: x + 0.25, y: 1.72, w: 2.4, h: 0.85, fontFace: H, fontSize: 40, bold: true, color: col, margin: 0, isTextBox: true });
    s.addText(txt, { x: x + 0.25, y: 2.6, w: 2.35, h: 1.15, fontFace: B, fontSize: 13, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  });
  s.addText([
    { text: 'Последствия: ', options: { bold: true, color: C.ink } },
    { text: 'наклон оси, неполный охват или металл в кадре искажают минеральную плотность кости — остеопороз пропускают или назначают лишнее лечение, пациента вызывают на повторное исследование.', options: { color: C.ink2 } },
  ], { x: 0.5, y: 4.2, w: 9, h: 0.8, fontFace: B, fontSize: 14, margin: 0, isTextBox: true });
  pageNo(s);
  s.addNotes('В обучающем наборе организатора эксперты отметили нарушения у 32 из 99 исследований поясничного отдела и у 41 из 150 снимков бедра. Сейчас такие ошибки ищут вручную и выборочно.');
}


// ------------------------------------------------------------------ 3. Подход и обоснование
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Подход и его обоснование', 'Разные области — разные методы: выбор продиктован данными и требованием объяснимости');
  const cols = [
    ['Поясничный отдел', 'правила по анатомическим ориентирам',
     ['Позвонки Th12–L5, ось и гребни подвздошных костей находятся на снимке', 'Критерии ТЗ проверяются как измерения: угол оси против 5°, охват, контраст пятна вне столба',
      'Примеров брака мало (6, 10 и 17) — обучаемая модель переобучилась бы, правило — нет', 'Каждый вердикт можно показать врачу: измерение и норма']],
    ['Бедро', 'ExtraTrees на 47 признаках формы',
     ['Признаки ориентиров: диафиз, большой и малый вертел, шейка, поля вокруг зоны интереса', 'Лучшее из шести сравнённых решений, включая признаки нейросетей ResNet-50 и DINOv2',
      'Веса классов против дисбаланса, порог — только на обучающей части', 'Инференс на numpy, без GPU и без сети']],
  ];
  cols.forEach(([h, sub, items], i) => {
    const x = 0.5 + i * 4.6;
    card(s, x, 1.45, 4.35, 3.7);
    num(s, i + 1, x + 0.22, 1.62, i ? C.navy2 : C.blue);
    s.addText(h, { x: x + 0.78, y: 1.58, w: 3.4, h: 0.32, fontFace: H, fontSize: 17, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(sub, { x: x + 0.78, y: 1.9, w: 3.4, h: 0.28, fontFace: B, fontSize: 12, color: C.blue, margin: 0, isTextBox: true });
    s.addText(items.map((t, k) => ({ text: t, options: { bullet: true, breakLine: k < items.length - 1 } })),
      { x: x + 0.25, y: 2.35, w: 3.9, h: 2.7, fontFace: B, fontSize: 12, color: C.ink2, margin: 0, valign: 'top', paraSpaceAfter: 6, isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Для позвоночника критерии ТЗ геометрические, а примеров брака единицы, поэтому правила по ориентирам надёжнее и объяснимы. Для бедра укладка сложнее формализуется — там обученная модель ExtraTrees; мы сравнили шесть вариантов и выбрали лучший.');
}

// ------------------------------------------------------------------ 4. Архитектура
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Архитектура', 'Один конвейер — веб-стенд, API, MCP и настольное приложение');
  const steps = [['DICOM / zip / папка', 'чтение заголовка, сжатые форматы, дубли по хешу пикселей'],
                 ['Область', 'поясница · левое · правое бедро'],
                 ['Проверки', 'поясница — правила по яркости и геометрии; бедро — ExtraTrees, 47 признаков'],
                 ['Пояснение', 'атлас на снимке · граф решения · текст и голос'],
                 ['Выход', 'CSV / XLSX по ТЗ 2.5 · ZIP разметки · API · MCP']];
  steps.forEach(([h, t], i) => {
    const x = 0.5 + i * 1.84;
    card(s, x, 1.55, 1.66, 2.05, i === 2 ? C.ice : C.card);
    num(s, i + 1, x + 0.15, 1.7, i === 2 ? C.blue : C.navy2);
    s.addText(h, { x: x + 0.15, y: 2.2, w: 1.4, h: 0.5, fontFace: H, fontSize: 14, bold: true, color: C.ink, margin: 0, valign: 'top', isTextBox: true });
    s.addText(t, { x: x + 0.15, y: 2.7, w: 1.42, h: 0.85, fontFace: B, fontSize: 10.5, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
    if (i < steps.length - 1) s.addText('›', { x: x + 1.64, y: 2.3, w: 0.22, h: 0.4, fontFace: H, fontSize: 22, color: C.ink3, align: 'center', margin: 0, isTextBox: true });
  });
  const stack = [['Стенд', 'FastAPI, Docker, nginx — ltz2026.ru'], ['Приложение 1.0-Beta', 'pywebview · Windows 10/11, Ubuntu, Debian'],
                 ['Контейнер по ТЗ', 'build.sh · run.sh · serve.sh, без сети'], ['Интеграции', 'HTTP API, MCP-сервер, Telegram-бот']];
  stack.forEach(([h, t], i) => {
    const x = 0.5 + i * 2.3;
    s.addText([{ text: h, options: { bold: true, color: C.ink, breakLine: true } }, { text: t, options: { color: C.ink2 } }],
      { x, y: 3.95, w: 2.15, h: 0.75, fontFace: B, fontSize: 11.5, margin: 0, valign: 'top', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Один конвейер обработки обслуживает всё: стенд, API, MCP и настольное приложение. Поясницу проверяют правила, бедро — обученная модель ExtraTrees.');
}


// ------------------------------------------------------------------ 5. Данные и разбиение
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Данные и разбиение выборки', 'Обучающий набор организатора с оценкой экспертов');
  const st = [['100', 'исследований'], ['252', 'уникальных снимка'], ['247', 'дублей убрано по хешу пикселей'], ['99 / 150', 'снимков поясницы / бедра с оценкой']];
  st.forEach(([b, t], i) => {
    const x = 0.5 + i * 2.3;
    s.addText(b, { x, y: 1.45, w: 2.2, h: 0.7, fontFace: H, fontSize: 36, bold: true, color: C.blue, margin: 0, isTextBox: true });
    s.addText(t, { x, y: 2.12, w: 2.1, h: 0.45, fontFace: B, fontSize: 12, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  });
  const rows = [['Без утечки', 'Фолды — по исследованиям; снимки, общие у нескольких исследований, всегда в одной группе'],
                ['Честная оценка', '5 фолдов × 50 повторов; пороги подбираются только на обучающей части фолда'],
                ['Дисбаланс', 'брак — 32 % и 27 %: веса классов в модели бедра, порог по F1, метрики F1 и ROC-AUC'],
                ['Интервалы', '95 % доверительные интервалы — по повторам и бутстрепом по исследованиям'],
                ['Предобработка', 'DICOM → оттенки серого, проверка модальности до разбора пикселей, сжатые JPEG-LS/2000']];
  rows.forEach(([h, t], i) => {
    const y = 2.8 + i * 0.47;
    s.addText(h, { x: 0.5, y, w: 1.8, h: 0.4, fontFace: H, fontSize: 13, bold: true, color: C.ink, margin: 0, valign: 'middle', isTextBox: true });
    s.addText(t, { x: 2.3, y, w: 7.2, h: 0.4, fontFace: B, fontSize: 12, color: C.ink2, margin: 0, valign: 'middle', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('100 исследований, 252 уникальных снимка после удаления 247 дублей. Главное — отсутствие утечки: фолды по исследованиям, общие снимки в одной группе, пороги только на обучающей части.');
}


// ------------------------------------------------------------------ 6. Таксономия нарушений
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Таксономия нарушений', 'Критерии ТЗ — отдельные проверки; снимок с несколькими нарушениями получает все их коды');
  const head = { bold: true, color: C.white, fill: { color: C.navy2 }, fontSize: 11.5 };
  const rows = [
    [{ text: 'Код', options: head }, { text: 'Область', options: head }, { text: 'Критерий ТЗ', options: head }, { text: 'Как проверяем', options: head }, { text: 'Брак в данных', options: head }],
    ['coverage', 'поясница', 'охват от гребней подвздошных костей до Th12', 'яркость гребней в нижних углах', '6'],
    ['axis_tilt', 'поясница', 'ось отклонена не больше 5°', 'осевая линия столба, угол', '10'],
    ['artifact', 'поясница', 'нет посторонних предметов', 'локальный контраст вне столба', '17'],
    ['hip_positioning', 'бедро', 'укладка и ротация по малому вертелу', 'ExtraTrees, 47 признаков', '36'],
    ['hip_roi', 'бедро', 'поля вокруг зоны интереса', 'та же модель', '7'],
  ];
  s.addTable(rows, { x: 0.5, y: 1.45, w: 9, colW: [1.45, 1.0, 2.75, 2.6, 1.2], fontFace: B, fontSize: 11, color: C.ink2,
                     border: { type: 'solid', pt: 0.75, color: 'E3E7ED' }, fill: { color: C.white }, rowH: 0.36, valign: 'middle' });
  card(s, 0.5, 3.85, 9, 1.2, C.ice);
  s.addText([
    { text: 'Несколько нарушений на снимке: ', options: { bold: true, color: C.ink } },
    { text: 'quality_class = 1, если сработала любая проверка; violation_type перечисляет все коды через «;»; в графе решения каждая проверка — отдельный узел с измерением и нормой, поэтому видно, что именно не так.', options: { color: C.ink2 } },
  ], { x: 0.75, y: 3.95, w: 8.5, h: 1.0, fontFace: B, fontSize: 12.5, margin: 0, valign: 'middle', isTextBox: true });
  pageNo(s);
  s.addNotes('Пять кодов нарушений по ТЗ. Если нарушений несколько, снимок получает класс 1 и все коды; граф решения показывает каждое отдельно.');
}


// ------------------------------------------------------------------ 7–11. Обязательные слайды (содержание)
function mandatoryTag(s, n) {
  s.addText(`обязательный слайд ${n}`, { x: 7.3, y: 0.12, w: 2.4, h: 0.22, fontFace: B, fontSize: 9, color: 'A0A6B2', align: 'right', margin: 0, isTextBox: true });
}
{ // 7. Паспорт решения
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 7);
  title(s, 'DXA QC — паспорт решения', 'Кейс 04 · Департамент здравоохранения Москвы');
  const rows = [['Задача', 'Автоматически оценивать качество снимков денситометрии (DXA) поясничного отдела и бедра по критериям ТЗ'],
                ['Решение', 'Сервис определяет область, класс качества 0/1 и типы нарушений, показывает их на снимке и выгружает таблицу по ТЗ 2.5'],
                ['Для кого', 'Рентгенолаборанты и врачи отделений денситометрии; руководители — отчёт о качестве'],
                ['Ценность', 'Брак виден, пока пациент ещё в кабинете: меньше повторных исследований и ошибок в диагнозе остеопороза'],
                ['Где работает', 'Локально: контейнер, приложение для Windows и Linux; стенд ltz2026.ru для демонстрации']];
  rows.forEach(([h, t], i) => {
    const y = 1.45 + i * 0.74;
    card(s, 0.5, y, 9, 0.64);
    s.addText(h, { x: 0.7, y, w: 1.8, h: 0.64, fontFace: H, fontSize: 14, bold: true, color: C.blue, margin: 0, valign: 'middle', isTextBox: true });
    s.addText(t, { x: 2.5, y, w: 6.85, h: 0.64, fontFace: B, fontSize: 12.5, color: C.ink2, margin: 0, valign: 'middle', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Обязательный слайд 7. Содержание подготовлено до получения файла шаблона: при переносе в шаблон вставить текст в его блоки, не меняя сетку.');
}
{ // 8. Соответствие ТЗ
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 8);
  title(s, 'Соответствие требованиям ТЗ', 'Обязательные функции, технические требования и дополнительный функционал');
  const ok = (t) => [{ text: '✓', options: { color: C.ok, bold: true } }, { text: '  ' + t, options: { color: C.ink2 } }];
  const part = (t) => [{ text: '◐', options: { color: C.warn, bold: true } }, { text: '  ' + t, options: { color: C.ink2 } }];
  const no = (t) => [{ text: '✕', options: { color: C.bad, bold: true } }, { text: '  ' + t, options: { color: C.ink2 } }];
  const colL = [ok('Область: поясничный отдел, левое и правое бедро'), ok('quality_class 0/1 и все типы нарушений через «;»'),
                ok('Таблица CSV и XLSX по разделу 2.5'), ok('Контейнер: build.sh, run.sh, API пакетной обработки'),
                ok('До 3 минут на исследование — 0,31 с на снимок'), ok('Без исключений: 100 % файлов, отказ — с причиной'),
                ok('Воспроизводимость: повторный прогон побайтно совпадает'), ok('Локально, без передачи снимков вовне')];
  const colR = [part('Визуализация нарушения: атласы PNG в ZIP, не DICOM-серия'), ok('Интерактивный веб-интерфейс: загрузка, просмотр, пакет'),
                part('Коррекция врачом: правка вердикта и порогов, не контуров'), no('Текстовое описание в DICOM SR — в плане пилота')];
  const put = (list, x, w, y0, head, step = 0.4) => {
    s.addText(head, { x, y: y0, w, h: 0.32, fontFace: H, fontSize: 14, bold: true, color: C.ink, margin: 0, isTextBox: true });
    list.forEach((runs, i) => s.addText(runs, { x, y: y0 + 0.4 + i * step, w, h: step - 0.04, fontFace: B, fontSize: 12, margin: 0, valign: 'middle', isTextBox: true }));
  };
  put(colL, 0.5, 4.6, 1.4, 'Обязательно (разделы 2, 2.7)');
  card(s, 5.35, 1.35, 4.2, 3.55, C.card);
  put(colR, 5.55, 3.85, 1.45, 'Дополнительно (раздел 2.6)', 0.72);
  pageNo(s);
  s.addNotes('Обязательный слайд 8. Все обязательные требования выполнены. Из дополнительных: веб-интерфейс полностью, визуализация — атласами PNG, коррекция — правкой вердикта, DICOM SR пока нет — честно говорим.');
}
{ // 9. Ключевые результаты
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 9);
  title(s, 'Ключевые результаты', 'Кросс-валидация по исследованиям на обучающем наборе организатора, 95 % ДИ');
  const k = [['0,75', 'ROC-AUC, поясничный отдел', '95 % ДИ 0,64–0,84', C.blue], ['0,85', 'ROC-AUC, посторонние предметы', '0,76–0,94', C.blue],
             ['0,88', 'ROC-AUC, охват', '0,58–1,00', C.blue], ['0,66', 'ROC-AUC, бедро', '0,62–0,69', C.warn],
             ['0,31 с', 'на снимок, 2 ядра CPU', 'ТЗ: до 3 минут', C.ok], ['100 %', 'файлов обработано', 'без исключений', C.ok]];
  k.forEach(([b, t, ci, col], i) => {
    const x = 0.5 + (i % 3) * 3.05, y = 1.45 + Math.floor(i / 3) * 1.85;
    card(s, x, y, 2.85, 1.65);
    s.addText(b, { x: x + 0.22, y: y + 0.15, w: 2.5, h: 0.75, fontFace: H, fontSize: 36, bold: true, color: col, margin: 0, isTextBox: true });
    s.addText([{ text: t, options: { color: C.ink, bold: true, breakLine: true } }, { text: ci, options: { color: C.ink3 } }],
      { x: x + 0.22, y: y + 0.9, w: 2.5, h: 0.65, fontFace: B, fontSize: 12, margin: 0, valign: 'top', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Обязательный слайд 9. Главные цифры: позвоночник AUC 0,75, посторонние предметы 0,85, охват 0,88, бедро 0,66; 0,31 секунды на снимок и 100 % обработанных файлов.');
}
{ // 10. Команда
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 10);
  title(s, 'Команда «Квантовый Скачок»', '');
  const team = [['ЮК', 'Юрий Коноплёв', 'капитан команды', '', '@bimodaling'],
                ['АЧ', 'Алексей Чуркин', 'участник команды', '', '@lesha_cfc']];
  team.forEach(([ini, name, role, what, tg], i) => {
    const x = 1.2 + i * 4.0;
    card(s, x, 1.3, 3.6, 3.7);
    s.addShape(pres.shapes.OVAL, { x: x + 1.2, y: 1.6, w: 1.2, h: 1.2, fill: { color: i ? C.navy2 : C.blue } });
    s.addText(ini, { x: x + 1.2, y: 1.6, w: 1.2, h: 1.2, fontFace: H, fontSize: 28, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
    s.addText(name, { x: x + 0.2, y: 3.0, w: 3.2, h: 0.42, fontFace: H, fontSize: 20, bold: true, color: C.ink, align: 'center', margin: 0, isTextBox: true });
    s.addText(role, { x: x + 0.2, y: 3.42, w: 3.2, h: 0.32, fontFace: B, fontSize: 13, color: C.blue, align: 'center', margin: 0, isTextBox: true });
    s.addText(what, { x: x + 0.3, y: 3.78, w: 3.0, h: 0.6, fontFace: B, fontSize: 12, color: C.ink2, align: 'center', margin: 0, valign: 'top', isTextBox: true });
    s.addText('Telegram ' + tg, { x: x + 0.2, y: 4.45, w: 3.2, h: 0.3, fontFace: B, fontSize: 12, color: C.ink3, align: 'center', margin: 0, isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Обязательный слайд 10. В шаблоне оставить две карточки, лишние удалить целиком. Роли уточнить у команды перед сдачей.');
}
{ // 11. Материалы решения
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 11);
  title(s, 'Материалы решения', 'Всё, что передаём на проверку');
  const items = [['Стенд', 'ltz2026.ru — загрузка DICOM, дашборд, готовые примеры'], ['Контейнер', 'build.sh · run.sh · serve.sh, запуск без сети'],
                 ['API', 'пакетная обработка архива, документация ltz2026.ru/docs'], ['Приложение', '.exe · .msi · .deb, версия 1.0-Beta, ltz2026.ru/download'],
                 ['Документация', 'README: сборка, запуск, API, форматы, ограничения'], ['Исходный код', 'репозиторий проекта — в комплекте сдачи']];
  items.forEach(([h, t], i) => {
    const y = 1.45 + i * 0.6;
    num(s, i + 1, 0.5, y + 0.02, C.navy2);
    s.addText([{ text: h + ' — ', options: { bold: true, color: C.ink } }, { text: t, options: { color: C.ink2 } }],
      { x: 1.05, y, w: 5.6, h: 0.46, fontFace: B, fontSize: 13, margin: 0, valign: 'middle', isTextBox: true });
  });
  card(s, 7.0, 1.45, 2.55, 3.1);
  img(s, 'qr.png', 7.3, 1.62, 1.95, 1.0);
  s.addText('ltz2026.ru', { x: 7.0, y: 3.72, w: 2.55, h: 0.4, fontFace: H, fontSize: 16, bold: true, color: C.blue, align: 'center', margin: 0, isTextBox: true });
  pageNo(s);
  s.addNotes('Обязательный слайд 11. Ссылки на все материалы сдачи; QR ведёт на стенд.');
}

// ------------------------------------------------------------------ 13. Эксперименты и ошибки
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Эксперименты и анализ ошибок', 'Что пробовали, что оставили и почему');
  const head = { bold: true, color: C.white, fill: { color: C.navy2 }, fontSize: 11 };
  s.addTable([
    [{ text: 'Модель для бедра', options: head }, { text: 'AUC', options: head }],
    ['Логистическая регрессия, 21 признак', '0,60'], ['Признаки ResNet-50 / DINOv2', 'до 0,64'],
    ['Бустинг · каскадный лес · Viola–Jones', 'не выше 0,66'], [{ text: 'ExtraTrees, 47 признаков — выбрана', options: { bold: true, color: C.ink } }, { text: '0,66', options: { bold: true, color: C.blue } }],
    ['Подбор 60 настроек против переобучения', 'не лучше'],
  ], { x: 0.5, y: 1.45, w: 4.6, colW: [3.6, 1.0], fontFace: B, fontSize: 11, color: C.ink2, rowH: 0.36, border: { type: 'solid', pt: 0.75, color: 'E3E7ED' } });
  const lessons = [[C.ok, 'Посторонние предметы: AUC 0,55 → 0,85', 'новый детектор локального контраста вместо порога яркости'],
                   [C.warn, 'Наклон оси: сколиоз', 'изгиб столба сервис принимает за наклон; 3 альтернативные меры оси — хуже текущей'],
                   [C.bad, 'Бедро: мало сигнала', 'кривые обучения — переобучение; нужны данные с разметкой ротации и признаки рентгеновских моделей']];
  lessons.forEach(([col, h, t], i) => {
    const y = 1.45 + i * 1.2;
    card(s, 5.4, y, 4.1, 1.05);
    s.addShape(pres.shapes.OVAL, { x: 5.58, y: y + 0.2, w: 0.22, h: 0.22, fill: { color: col } });
    s.addText(h, { x: 5.95, y: y + 0.1, w: 3.45, h: 0.35, fontFace: H, fontSize: 13, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(t, { x: 5.95, y: y + 0.45, w: 3.45, h: 0.55, fontFace: B, fontSize: 11, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Сравнили шесть подходов для бедра — выбрали ExtraTrees. Главная победа — детектор посторонних предметов: AUC вырос с 0,55 до 0,85. Ошибки по оси связаны со сколиозом.');
}


// ------------------------------------------------------------------ 13. Метрики с доверительными интервалами
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Метрики качества и 95 % ДИ', 'Кросс-валидация: 5 фолдов по исследованиям × 50 повторов; порог — только на обучающей части');
  const hd = (t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.navy2 }, fontSize: 10.5, align: 'center' } });
  const L = (t, b) => ({ text: t, options: { align: 'left', bold: !!b, color: b ? C.ink : C.ink2 } });
  const rows = [
    [hd('Критерий'), hd('Брак / всего'), hd('Чувствит.'), hd('Специф.'), hd('Сбаланс. точность'), hd('F1 (95 % ДИ)'), hd('ROC-AUC (95 % ДИ)')],
    [L('Поясничный отдел, итог', 1), '32 / 99', '0,69', '0,67', '0,68', '0,58 (0,46–0,74)', '0,75 (0,64–0,84)'],
    [L('   охват'), '6 / 99', '0,67', '0,98', '0,82', '0,69 (0,40–0,93)', '0,88 (0,58–1,00)'],
    [L('   наклон оси'), '10 / 99', '0,41', '0,86', '0,63', '0,30 (0,11–0,60)', '0,75 (0,55–0,91)'],
    [L('   посторонние предметы'), '17 / 99', '0,68', '0,84', '0,76', '0,55 (0,34–0,72)', '0,85 (0,76–0,94)'],
    [L('Бедро, итог', 1), '41 / 150', '0,65', '0,57', '0,61', '0,47', '0,66 (0,62–0,69)'],
    [L('   укладка и ротация'), '36 / 150', '—', '—', '—', '—', '0,62'],
    [L('   поля зоны интереса'), '7 / 150', '—', '—', '—', '—', '0,80'],
  ];
  s.addTable(rows, { x: 0.5, y: 1.4, w: 9, colW: [2.2, 1.0, 0.9, 0.9, 1.1, 1.45, 1.45], fontFace: B, fontSize: 11, color: C.ink2, align: 'center',
                     rowH: 0.34, valign: 'middle', border: { type: 'solid', pt: 0.75, color: 'E3E7ED' } });
  card(s, 0.5, 4.3, 9, 0.8, C.ice);
  s.addText([{ text: 'Сводная фитнес-функция 0,58 ', options: { bold: true, color: C.ink } },
             { text: '= 0,35·F1 + 0,35·ROC-AUC по областям + 0,30·macro-F1 типов нарушений; базовая линия 0,570 (0,477–0,644). Время и доля обработанных файлов — на следующем слайде.', options: { color: C.ink2 } }],
    { x: 0.7, y: 4.33, w: 8.6, h: 0.74, fontFace: B, fontSize: 11.5, margin: 0, valign: 'middle', isTextBox: true });
  pageNo(s);
  s.addNotes('Метрики — как просит раздел 8.4 ТЗ: по областям и типам нарушений, чувствительность, специфичность, сбалансированная точность, F1 и ROC-AUC с 95 % ДИ. Сильные стороны — охват и посторонние предметы, слабые — наклон оси из-за сколиоза и бедро.');
}

// ------------------------------------------------------------------ 14. Скорость и требования
{
  const s = pres.addSlide(); s.background = { color: C.navy };
  title(s, 'Скорость и системные требования', 'Замер: 2 ядра CPU, 4 ГБ памяти, без видеокарты', true);
  const st = [['0,31 с', 'на снимок · ТЗ: до 3 минут'], ['80 с', 'весь обучающий набор, 252 снимка'], ['100 %', 'файлов обработано без сбоев'], ['191 МБ', 'пик памяти процесса']];
  st.forEach(([b, t], i) => {
    const x = 0.5 + i * 2.3;
    s.addText(b, { x, y: 1.55, w: 2.2, h: 0.85, fontFace: H, fontSize: 38, bold: true, color: C.white, margin: 0, isTextBox: true });
    s.addText(t, { x, y: 2.4, w: 2.05, h: 0.6, fontFace: B, fontSize: 12, color: 'B9C6DA', margin: 0, valign: 'top', isTextBox: true });
  });
  const req = [['Минимум', '2 ядра, 4 ГБ ОЗУ, 64-битная ОС; образ контейнера ~2 ГБ'], ['Рекомендуется', '4 ядра, 8 ГБ ОЗУ, 2 ГБ под проверки'],
               ['Сеть', 'не нужна: контейнер запускается с --network none'], ['Воспроизводимость', 'версии зафиксированы, повторный прогон побайтно совпадает']];
  req.forEach(([h, t], i) => {
    const y = 3.35 + i * 0.44;
    s.addText(h, { x: 0.5, y, w: 2.0, h: 0.38, fontFace: H, fontSize: 13, bold: true, color: C.white, margin: 0, valign: 'middle', isTextBox: true });
    s.addText(t, { x: 2.5, y, w: 7.0, h: 0.38, fontFace: B, fontSize: 12.5, color: 'CADCFC', margin: 0, valign: 'middle', isTextBox: true });
  });
  pageNo(s, 0, true);
  s.addNotes('На слабой машине без видеокарты — 0,31 секунды на снимок, весь набор за 80 секунд, 191 мегабайт памяти. Сеть не нужна, результаты воспроизводимы.');
}


// ------------------------------------------------------------------ 15. Кейс: галерея снимков и граф решения
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Кейс: посторонний предмет у позвоночника', 'Дашборд исследования: результат — прямо на снимках, пояснение — графом');
  card(s, 0.45, 1.4, 5.75, 3.75);
  img(s, 'dash_gallery.png', 1.125, 1.52, 4.4, 1.986);
  const steps = [['Галерея снимков', 'рамка красная — нарушение, зелёная — годен; причина под снимком'],
                 ['Карточка снимка', 'нажатие на снимок открывает проверки по критериям ТЗ'],
                 ['Выгрузка', 'таблица XLSX / CSV по ТЗ 2.5 и атласы одним ZIP']];
  steps.forEach(([h, t], i) => {
    const y = 3.9 + i * 0.42;
    num(s, i + 1, 0.6, y, C.navy2);
    s.addText([{ text: h + ': ', options: { bold: true, color: C.ink } }, { text: t, options: { color: C.ink2 } }],
      { x: 1.15, y, w: 4.95, h: 0.42, fontFace: B, fontSize: 11, margin: 0, valign: 'middle', isTextBox: true });
  });
  card(s, 6.4, 1.4, 3.15, 3.75);
  img(s, 'graph.png', 6.5, 1.55, 2.95, 1.176);
  s.addText('Граф решения: измерение против нормы по каждой проверке ТЗ → вердикт. Сворачивается в текст.', { x: 6.5, y: 4.15, w: 2.95, h: 0.85, fontFace: B, fontSize: 11, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  pageNo(s);
  s.addNotes('Живой кейс на синтетическом фантоме: застёжка рядом с позвоночником. Результат видно сразу в галерее снимков: красная рамка и причина. Нажатие открывает карточку, граф показывает измеренный контраст против нормы 55 — брак.');
}


// ------------------------------------------------------------------ 16. Всё — на самом снимке
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Всё — на самом снимке', 'Врач видит результат там, где привык: на изображении исследования');
  card(s, 0.45, 1.4, 4.9, 3.75, C.navy);
  img(s, 'atlas.png', 0.6, 1.55, 4.6, 1.314);
  img(s, 'card_spine.png', 5.55, 1.4, 1.5, 0.4016);
  const pts = [['Разметка', 'позвонки, ось и границы зон подписаны прямо на снимке'],
               ['Причина', 'предмет обведён рамкой, критерий ТЗ отмечен ✕'],
               ['Измерение', 'угол оси, контраст, вероятность — с нормой рядом'],
               ['Без лишнего', 'никаких схем вместо снимка: только то, что было на аппарате']];
  pts.forEach(([h, t], i) => {
    const y = 1.45 + i * 0.93;
    s.addText(h, { x: 7.3, y, w: 2.25, h: 0.32, fontFace: H, fontSize: 14, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(t, { x: 7.3, y: y + 0.32, w: 2.25, h: 0.55, fontFace: B, fontSize: 11, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Результаты показываем только на снимках: атлас с разметкой позвонков, оси и найденного предмета, рядом — карточка снимка с проверками по ТЗ. Врач смотрит на то же изображение, что получил с аппарата.');
}


// ------------------------------------------------------------------ 17. Продукт и поставка
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Готово к использованию уже сейчас', 'Стенд, API и настольное приложение DXA QC 1.0-Beta');
  card(s, 0.45, 1.4, 5.2, 3.75);
  img(s, 'download2.png', 0.55, 1.55, 5.0, 1.714);
  const items = [['Веб-стенд', 'ltz2026.ru — загрузка, дашборд, пример'], ['Приложение', '.exe · .msi · .deb, офлайн, подписанные суммы'],
                 ['Контейнер', 'сборка и запуск одной командой, как в ТЗ'], ['Интеграции', 'HTTP API · MCP · Telegram-бот'],
                 ['Если файл не тот', 'сервис объяснит, что загружено и что делать']];
  items.forEach(([h, t], i) => {
    const y = 1.45 + i * 0.73;
    num(s, i + 1, 5.9, y + 0.04, C.ok);
    s.addText(h, { x: 6.45, y, w: 3.1, h: 0.3, fontFace: H, fontSize: 13.5, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(t, { x: 6.45, y: y + 0.3, w: 3.1, h: 0.38, fontFace: B, fontSize: 11, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Продукт можно попробовать прямо сейчас: стенд ltz2026.ru, приложение для Windows и Linux со страницы загрузки, контейнер по ТЗ.');
}


// ------------------------------------------------------------------ 18. Сценарий демонстрации
{
  const s = pres.addSlide(); s.background = { color: C.navy };
  title(s, 'Демонстрация: 2 минуты', 'Сценарий показа на защите — на синтетических фантомах, без данных пациентов', true);
  const steps = [['Загрузка', 'на главной ltz2026.ru перетаскиваем архив DICOM или выбираем готовый пример'],
                 ['Дашборд', 'сводка: исследования, годные, с нарушениями, время на снимок'],
                 ['Снимок с браком', 'в галерее красная рамка — открываем карточку: предмет в рамке на атласе'],
                 ['Пояснение', 'граф решения: контраст против нормы → вердикт; переключаем в текст'],
                 ['Выгрузка', 'таблица XLSX по ТЗ 2.5 и ZIP с атласами; то же — в приложении без интернета']];
  steps.forEach(([h, t], i) => {
    const y = 1.45 + i * 0.73;
    num(s, i + 1, 0.5, y + 0.05, C.blue);
    s.addText(h, { x: 1.1, y, w: 2.2, h: 0.52, fontFace: H, fontSize: 15, bold: true, color: C.white, margin: 0, valign: 'middle', isTextBox: true });
    s.addText(t, { x: 3.3, y, w: 6.2, h: 0.52, fontFace: B, fontSize: 13, color: 'CADCFC', margin: 0, valign: 'middle', isTextBox: true });
  });
  pageNo(s, 0, true);
  s.addNotes('Сценарий живой демонстрации: загрузка, дашборд, снимок с браком, пояснение, выгрузка. Всё на синтетических фантомах.');
}

// ------------------------------------------------------------------ 18. Ограничения и внедрение
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Ограничения и план внедрения', 'Говорим прямо, где сервис пока слабее, и как это закрываем');
  const lim = ['Бедро — подсказка модели: AUC 0,66, нужна разметка ротации', 'Уровень Th12 определяется приблизительно и не проверяется',
               'Поля в сантиметрах не считаются: в DICOM нет масштаба', 'Сколиоз путается с наклоном оси'];
  card(s, 0.45, 1.4, 4.3, 3.75);
  s.addText('Ограничения', { x: 0.7, y: 1.55, w: 3.9, h: 0.35, fontFace: H, fontSize: 15, bold: true, color: C.ink, margin: 0, isTextBox: true });
  s.addText(lim.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lim.length - 1 } })),
    { x: 0.7, y: 2.0, w: 3.9, h: 2.9, fontFace: B, fontSize: 12.5, color: C.ink2, margin: 0, valign: 'top', paraSpaceAfter: 8, isTextBox: true });
  const plan = [['1', 'Пилот', '1–2 отделения: проверка каждого снимка в день исследования'], ['2', 'Разметка', 'врачи уточняют спорные снимки прямо в пульте — данные для дообучения'],
                ['3', 'Бедро и Th12', 'модели на рентгеновских признаках, разметка ротации и уровней'], ['4', 'Масштаб', 'интеграция с PACS / ЕРИС, отчёт по качеству отделений']];
  plan.forEach(([n, h, t], i) => {
    const y = 1.45 + i * 0.93;
    num(s, n, 5.05, y + 0.05, C.blue);
    s.addText(h, { x: 5.6, y, w: 3.9, h: 0.32, fontFace: H, fontSize: 14, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(t, { x: 5.6, y: y + 0.32, w: 3.9, h: 0.55, fontFace: B, fontSize: 11.5, color: C.ink2, margin: 0, valign: 'top', isTextBox: true });
  });
  pageNo(s);
  s.addNotes('Ограничения мы называем открыто. План: пилот в отделениях, сбор уточнённой разметки прямо в интерфейсе, дообучение бедра и Th12, затем интеграция с PACS и ЕРИС.');
}


// ------------------------------------------------------------------ 20. Финал
{
  const s = pres.addSlide(); s.background = { color: C.navy };
  card(s, 6.3, 1.0, 3.0, 3.55, C.white);
  img(s, 'qr.png', 6.55, 1.2, 2.5, 1.0);
  s.addText('ltz2026.ru', { x: 6.3, y: 3.85, w: 3.0, h: 0.5, fontFace: H, fontSize: 20, bold: true, color: C.navy, align: 'center', margin: 0, isTextBox: true });
  s.addText('Попробуйте сами', { x: 0.55, y: 1.0, w: 5.4, h: 0.7, fontFace: H, fontSize: 36, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText([
    { text: 'Проверка снимка, готовые примеры, приложение для Windows и Linux.', options: { breakLine: true } },
    { text: 'Работает без интернета — снимки не покидают медорганизацию.' },
  ], { x: 0.55, y: 1.85, w: 5.4, h: 0.9, fontFace: B, fontSize: 14, color: 'B9C6DA', margin: 0, paraSpaceAfter: 4, isTextBox: true });
  s.addText([
    { text: 'Команда «Квантовый Скачок»', options: { bold: true, color: C.white, breakLine: true } },
    { text: 'Юрий Коноплёв · Алексей Чуркин', options: { color: 'CADCFC', breakLine: true } },
    { text: 'Telegram: @bimodaling · @lesha_cfc', options: { color: '8FA3C2' } },
  ], { x: 0.55, y: 3.45, w: 5.4, h: 1.0, fontFace: B, fontSize: 14, margin: 0, isTextBox: true });
  s.addNotes('Спасибо! Всё можно попробовать на ltz2026.ru. Готовы ответить на вопросы.');
}

pres.writeFile({ fileName: path.join(__dirname, 'DXA_QC_presentation.pptx') }).then(f => console.log('готово:', f));
