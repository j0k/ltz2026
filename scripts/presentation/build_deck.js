// Презентация Kostik для ЛЦТ 2026 (задача 04), структура — по разделу 4 ТЗ и критериям раздела 8.
// Стиль 29.09: заголовки и крупные числа — Cambria, текст — Calibri; метка раздела над заголовком; заголовки-выводы;
// цвет результата: зелёный — сильный, янтарный — средний, коралловый — слабый.
// Слайды 1–6 и 12+ — свободная часть; 7–11 — содержание обязательных слайдов (до файла шаблона — в нашей вёрстке;
// при переносе в шаблон — только текст, сетку шаблона не менять). 3D-моделей нет: только снимки.
// Запуск: node build_deck.js → Kostik_presentation.pptx
const pptxgen = require('pptxgenjs');
const path = require('path');
const A = (f) => path.join(__dirname, 'assets', f);

const C = {
  ink: '0B1320', ink2: '3D4657', ink3: '7A8394', line: 'E4E8EF', soft: 'F4F6FA', white: 'FFFFFF',
  night: '0B1320', night2: '17233A', nightText: 'C9D4E6', nightMute: '8594AE',
  blue: '2E6BFF', blueSoft: 'E6EEFF',
  good: '0E9F6E', goodSoft: 'E3F6EE', mid: 'D98A00', midSoft: 'FDF1DB', weak: 'E0483E', weakSoft: 'FDE7E5',
};
const H = 'Cambria', B = 'Calibri';

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';                // 10 × 5.625 дюйма
pres.title = 'Kostik — контроль качества денситометрии';
pres.company = 'команда «Квантовый Скачок»';

const T = (s, text, o) => s.addText(text, { margin: 0, isTextBox: true, fontFace: B, ...o });
const shadow = () => ({ type: 'outer', color: '0B1320', blur: 8, offset: 2, angle: 90, opacity: 0.08 });

function eyebrow(s, text, dark = false, x = 0.55, y = 0.34) {
  T(s, text.toUpperCase(), { x, y, w: 6, h: 0.24, fontSize: 10, bold: true, charSpacing: 2, color: dark ? '7FA6FF' : C.blue });
}
function title(s, eye, text, sub, dark = false) {
  eyebrow(s, eye, dark);
  T(s, text, { x: 0.55, y: 0.6, w: 8.9, h: 0.62, fontFace: H, fontSize: 24, bold: true, color: dark ? C.white : C.ink, valign: 'middle' });
  if (sub) T(s, sub, { x: 0.55, y: 1.22, w: 8.9, h: 0.3, fontSize: 13, color: dark ? C.nightMute : C.ink3 });
}
function card(s, x, y, w, h, fill = C.soft, withShadow = false) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, rectRadius: 0.1, line: { color: fill },
    ...(withShadow ? { shadow: shadow() } : {}) });
}
function num(s, n, x, y, color = C.blue, d = 0.4) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color } });
  T(s, String(n), { x, y, w: d, h: d, fontFace: H, fontSize: 14, bold: true, color: C.white, align: 'center', valign: 'middle' });
}
function pill(s, text, x, y, color, soft, w = 1.3) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.28, fill: { color: soft }, rectRadius: 0.14, line: { color: soft } });
  T(s, text, { x, y, w, h: 0.28, fontSize: 10.5, bold: true, color, align: 'center', valign: 'middle' });
}
function img(s, f, x, y, w, ratio, opts = {}) { s.addImage({ path: A(f), x, y, w, h: w / ratio, ...opts }); }
function pageNo(s, dark = false) {
  T(s, String(pres.slides.length), { x: 9.1, y: 5.22, w: 0.5, h: 0.22, fontSize: 10, color: dark ? C.nightMute : 'A6ADBA', align: 'right' });
  T(s, 'Kostik', { x: 0.55, y: 5.22, w: 2, h: 0.22, fontFace: H, fontSize: 10, bold: true, color: dark ? C.nightMute : 'A6ADBA' });
}
const tone = (auc) => (auc >= 0.8 ? [C.good, C.goodSoft] : auc >= 0.7 ? [C.mid, C.midSoft] : [C.weak, C.weakSoft]);

// ------------------------------------------------------------------ 1. Титул
{
  const s = pres.addSlide(); s.background = { color: C.night };
  card(s, 5.45, 0.55, 4.05, 3.15, C.night2);
  img(s, 'atlas.png', 5.6, 0.68, 3.75, 1.314);
  T(s, 'Атлас снимка: позвонки Th12–L5, ось, найденный предмет · синтетический фантом',
    { x: 5.5, y: 3.78, w: 4.0, h: 0.3, fontSize: 9.5, color: C.nightMute });
  eyebrow(s, 'ЛЦТ 2026 · задача 04 · ДепЗдрав Москвы', true, 0.55, 0.62);
  T(s, 'Kostik', { x: 0.52, y: 0.95, w: 4.8, h: 1.1, fontFace: H, fontSize: 66, bold: true, color: C.white });
  T(s, 'Контроль качества снимков денситометрии — за доли секунды и прямо на снимке',
    { x: 0.55, y: 2.1, w: 4.6, h: 0.9, fontFace: H, fontSize: 19, color: C.nightText });
  const kpi = [['0,85', 'ROC-AUC\nпосторонние предметы'], ['0,31 с', 'на снимок\nбез видеокарты'], ['100 %', 'файлов обработано\nбез сбоев']];
  kpi.forEach(([b, t], i) => {
    const x = 0.55 + i * 1.62;
    T(s, b, { x, y: 3.35, w: 1.55, h: 0.6, fontFace: H, fontSize: 28, bold: true, color: i === 0 ? '5EE0A8' : C.white });
    T(s, t, { x, y: 3.95, w: 1.55, h: 0.45, fontSize: 10.5, color: C.nightMute });
  });
  T(s, 'Команда «Квантовый Скачок»: Юрий Коноплёв · Алексей Чуркин', { x: 0.55, y: 4.85, w: 6, h: 0.3, fontSize: 11, color: C.nightMute });
  s.addNotes('Мы — команда «Квантовый Скачок». Наш продукт — Kostik: имя от слова «кость». Kostik проверяет качество снимков денситометрии сразу после исследования: область, вердикт, тип нарушения и объяснение прямо на снимке. Работает локально, без интернета.');
}

// ------------------------------------------------------------------ 2. Проблема
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Проблема', 'Каждый третий снимок поясницы — с браком',
    'Денситометрия — основной метод диагностики остеопороза, и её результат зависит от качества снимка');
  const stats = [['32 %', 'снимков поясничного отдела — с нарушением по оценке экспертов организатора', C.weak],
                 ['27 %', 'снимков бедра — с нарушением укладки или полей зоны интереса', C.mid],
                 ['0', 'автоматических проверок сегодня: качество смотрят вручную и выборочно', C.ink2]];
  stats.forEach(([big, txt, col], i) => {
    const x = 0.55 + i * 3.0;
    card(s, x, 1.75, 2.8, 2.2, C.soft);
    T(s, big, { x: x + 0.25, y: 1.9, w: 2.4, h: 0.95, fontFace: H, fontSize: 50, bold: true, color: col });
    T(s, txt, { x: x + 0.25, y: 2.9, w: 2.35, h: 0.95, fontSize: 13, color: C.ink2, valign: 'top' });
  });
  T(s, [{ text: 'Цена ошибки: ', options: { bold: true, color: C.ink } },
        { text: 'наклон оси, неполный охват или металл в кадре искажают плотность кости — остеопороз пропускают или лечат лишнее, пациента вызывают повторно.', options: { color: C.ink2 } }],
    { x: 0.55, y: 4.25, w: 8.9, h: 0.7, fontSize: 14 });
  pageNo(s);
  s.addNotes('В обучающем наборе организатора эксперты отметили нарушения у 32 из 99 исследований поясничного отдела и у 41 из 150 снимков бедра. Сейчас такие ошибки ищут вручную и выборочно.');
}

// ------------------------------------------------------------------ 3. Подход
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Подход', 'Правила для измерений, модель — для формы',
    'Выбор продиктован данными и требованием объяснимости для врача');
  const cols = [
    ['Поясничный отдел', 'правила по анатомическим ориентирам', C.blue,
     ['Критерии ТЗ — измерения: угол оси против 5°, охват, контраст пятна вне столба',
      'Брака мало (6, 10 и 17 случаев) — правило не переобучится',
      'Каждый вердикт — «измерение против нормы»']],
    ['Бедро', 'ExtraTrees по 47 признакам формы', C.ink,
     ['Диафиз, большой и малый вертел, шейка, поля вокруг зоны интереса',
      'Лучший из шести подходов, включая признаки нейросетей ResNet-50, DINOv2 и RAD-DINO',
      'Инференс на numpy — без GPU и без сети']],
  ];
  cols.forEach(([h, sub, col, items], i) => {
    const x = 0.55 + i * 4.5;
    card(s, x, 1.75, 4.3, 3.3, C.soft);
    num(s, i + 1, x + 0.25, 1.95, col);
    T(s, h, { x: x + 0.8, y: 1.9, w: 3.3, h: 0.34, fontFace: H, fontSize: 18, bold: true, color: C.ink });
    T(s, sub, { x: x + 0.8, y: 2.24, w: 3.3, h: 0.28, fontSize: 12, bold: true, color: col === C.ink ? C.ink3 : C.blue });
    T(s, items.map((t, k) => ({ text: t, options: { bullet: true, breakLine: k < items.length - 1 } })),
      { x: x + 0.3, y: 2.72, w: 3.8, h: 2.2, fontSize: 13, color: C.ink2, valign: 'top', paraSpaceAfter: 8 });
  });
  pageNo(s);
  s.addNotes('Для позвоночника критерии ТЗ геометрические, а примеров брака единицы, поэтому правила по ориентирам надёжнее и объяснимы. Для бедра укладка сложнее формализуется — там обученная модель ExtraTrees; мы сравнили шесть вариантов и выбрали лучший.');
}

// ------------------------------------------------------------------ 4. Архитектура
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Архитектура', 'Один конвейер для стенда, API и приложения',
    'От файла DICOM до таблицы по ТЗ и атласа на снимке');
  const steps = [['Вход', 'DICOM, папка или zip; сжатые форматы; дубли по пикселям'],
                 ['Область', 'поясница, левое или правое бедро'],
                 ['Проверки', 'поясница — правила; бедро — ExtraTrees'],
                 ['Пояснение', 'атлас на снимке, граф решения, текст и голос'],
                 ['Выход', 'CSV / XLSX по ТЗ 2.5, ZIP разметки']];
  steps.forEach(([h, t], i) => {
    const x = 0.55 + i * 1.8, hl = i === 2;
    card(s, x, 1.8, 1.6, 2.0, hl ? C.blueSoft : C.soft);
    num(s, i + 1, x + 0.18, 1.98, hl ? C.blue : C.ink, 0.38);
    T(s, h, { x: x + 0.15, y: 2.5, w: 1.4, h: 0.34, fontFace: H, fontSize: 13, bold: true, color: C.ink });
    T(s, t, { x: x + 0.18, y: 2.86, w: 1.32, h: 0.9, fontSize: 11, color: C.ink2, valign: 'top' });
    if (i < steps.length - 1) T(s, '→', { x: x + 1.6, y: 2.55, w: 0.2, h: 0.3, fontSize: 14, color: C.ink3, align: 'center' });
  });
  const stack = [['Стенд', 'ltz2026.ru · FastAPI, Docker, nginx'], ['Контейнер по ТЗ', 'build.sh · run.sh · serve.sh, без сети'],
                 ['Приложение 1.0-Beta', 'Windows, Ubuntu, Debian · офлайн'], ['Интеграции', 'HTTP API · MCP · Telegram-бот']];
  stack.forEach(([h, t], i) => {
    const x = 0.55 + i * 2.25;
    T(s, [{ text: h, options: { bold: true, color: C.ink, breakLine: true } }, { text: t, options: { color: C.ink3 } }],
      { x, y: 4.15, w: 2.1, h: 0.75, fontSize: 12, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Один конвейер обработки обслуживает всё: стенд, API, контейнер и настольное приложение. Поясницу проверяют правила, бедро — обученная модель ExtraTrees.');
}

// ------------------------------------------------------------------ 5. Данные
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Данные', 'Честная оценка — без утечки данных',
    'Ни один снимок не попал одновременно в обучение и в проверку');
  const st = [['100', 'исследований'], ['252', 'уникальных снимка'], ['247', 'дублей убрано'], ['99 / 150', 'поясниц / бёдер с оценкой']];
  st.forEach(([b, t], i) => {
    const x = 0.55 + i * 2.25;
    T(s, b, { x, y: 1.7, w: 2.15, h: 0.75, fontFace: H, fontSize: 38, bold: true, color: C.blue });
    T(s, t, { x, y: 2.45, w: 2.1, h: 0.3, fontSize: 12.5, color: C.ink2 });
  });
  const rows = [['Без утечки', 'фолды — по исследованиям; общие снимки нескольких исследований — всегда в одной группе'],
                ['Честная оценка', '5 фолдов × 50 повторов; пороги подбираются только на обучающей части'],
                ['Дисбаланс', 'брак 32 % и 27 %: веса классов, порог по F1, метрики F1 и ROC-AUC'],
                ['Интервалы', '95 % — по повторам и бутстрепом по исследованиям']];
  rows.forEach(([h, t], i) => {
    const y = 3.05 + i * 0.47;
    T(s, h, { x: 0.55, y, w: 1.9, h: 0.4, fontFace: H, fontSize: 14, bold: true, color: C.ink, valign: 'middle' });
    T(s, t, { x: 2.5, y, w: 7.0, h: 0.4, fontSize: 13, color: C.ink2, valign: 'middle' });
  });
  pageNo(s);
  s.addNotes('100 исследований, 252 уникальных снимка после удаления 247 дублей. Главное — отсутствие утечки: фолды по исследованиям, общие снимки в одной группе, пороги только на обучающей части.');
}

// ------------------------------------------------------------------ 6. Таксономия
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Таксономия', 'Пять нарушений ТЗ — пять проверок',
    'Снимок с несколькими нарушениями получает все их коды');
  const hd = (t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.ink }, fontSize: 11.5 } });
  const code = (t) => ({ text: t, options: { bold: true, color: C.blue, fontFace: 'Consolas' } });
  const rows = [
    [hd('Код'), hd('Область'), hd('Критерий ТЗ'), hd('Как проверяем'), hd('Брак в данных')],
    [code('coverage'), 'поясница', 'охват от гребней подвздошных костей до Th12', 'яркость гребней в нижних углах', '6'],
    [code('axis_tilt'), 'поясница', 'ось отклонена не больше 5°', 'угол осевой линии столба', '10'],
    [code('artifact'), 'поясница', 'нет посторонних предметов', 'локальный контраст вне столба', '17'],
    [code('hip_positioning'), 'бедро', 'укладка и ротация по малому вертелу', 'ExtraTrees, 47 признаков', '36'],
    [code('hip_roi'), 'бедро', 'поля вокруг зоны интереса', 'та же модель', '7'],
  ];
  s.addTable(rows, { x: 0.55, y: 1.75, w: 8.9, colW: [1.85, 0.95, 2.6, 2.4, 1.1], fontFace: B, fontSize: 11.5, color: C.ink2,
                     border: { type: 'solid', pt: 0.75, color: C.line }, fill: { color: C.white }, rowH: 0.38, valign: 'middle' });
  card(s, 0.55, 4.25, 8.9, 0.75, C.blueSoft);
  T(s, [{ text: 'Несколько нарушений: ', options: { bold: true, color: C.ink } },
        { text: 'quality_class = 1, violation_type перечисляет все коды через «;», а граф решения показывает каждую проверку с измерением и нормой.', options: { color: C.ink2 } }],
    { x: 0.8, y: 4.25, w: 8.5, h: 0.75, fontSize: 13, valign: 'middle' });
  pageNo(s);
  s.addNotes('Пять кодов нарушений по ТЗ. Если нарушений несколько, снимок получает класс 1 и все коды; граф решения показывает каждое отдельно.');
}

// ------------------------------------------------------------------ 7–11. Обязательные слайды (содержание)
function mandatoryTag(s, n) {
  T(s, `обязательный слайд ${n}`, { x: 7.2, y: 0.34, w: 2.3, h: 0.22, fontSize: 9, color: 'A6ADBA', align: 'right' });
}
{ // 7. Паспорт решения
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 7);
  title(s, 'Паспорт решения', 'Kostik — контроль DXA на месте исследования', 'Кейс 04 · Департамент здравоохранения Москвы');
  const rows = [['Задача', 'Оценивать качество снимков денситометрии (DXA) поясничного отдела и бедра по критериям ТЗ'],
                ['Решение', 'Область, класс качества 0/1 и типы нарушений — на снимке и в таблице по ТЗ 2.5'],
                ['Для кого', 'Рентгенолаборанты и врачи отделений денситометрии; руководители — отчёт о качестве'],
                ['Ценность', 'Брак виден, пока пациент в кабинете: меньше повторных исследований и ошибок диагноза'],
                ['Где работает', 'Локально: контейнер, приложение для Windows и Linux; стенд ltz2026.ru']];
  rows.forEach(([h, t], i) => {
    const y = 1.72 + i * 0.66;
    card(s, 0.55, y, 8.9, 0.56, C.soft);
    T(s, h, { x: 0.8, y, w: 1.8, h: 0.56, fontFace: H, fontSize: 15, bold: true, color: C.blue, valign: 'middle' });
    T(s, t, { x: 2.6, y, w: 6.7, h: 0.56, fontSize: 13, color: C.ink2, valign: 'middle' });
  });
  pageNo(s);
  s.addNotes('Обязательный слайд 7. Содержание подготовлено до получения файла шаблона: при переносе в шаблон вставить текст в его блоки, не меняя сетку.');
}
{ // 8. Соответствие ТЗ
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 8);
  title(s, 'Соответствие ТЗ', 'Все обязательные требования выполнены', 'Разделы 2, 2.6 и 2.7 технического задания');
  const mark = (sym, col, t) => [{ text: sym, options: { color: col, bold: true } }, { text: '   ' + t, options: { color: C.ink2 } }];
  const colL = [mark('✓', C.good, 'Области: поясничный отдел, левое и правое бедро'), mark('✓', C.good, 'Класс 0/1 и все типы нарушений через «;»'),
                mark('✓', C.good, 'Таблица CSV и XLSX по разделу 2.5'), mark('✓', C.good, 'Контейнер: build.sh, run.sh, API пакетной обработки'),
                mark('✓', C.good, 'До 3 минут на исследование — 0,31 с на снимок'), mark('✓', C.good, 'Без исключений: отказ — строкой с причиной'),
                mark('✓', C.good, 'Повторный прогон совпадает побайтно'), mark('✓', C.good, 'Локально, без передачи снимков вовне')];
  const colR = [mark('◐', C.mid, 'Визуализация нарушения: атласы PNG в ZIP'), mark('✓', C.good, 'Интерактивный веб-интерфейс'),
                mark('◐', C.mid, 'Коррекция врачом: правка вердикта и порогов'), mark('✕', C.weak, 'Описание в DICOM SR — в плане пилота')];
  T(s, 'Обязательно', { x: 0.55, y: 1.7, w: 4.6, h: 0.32, fontFace: H, fontSize: 15, bold: true, color: C.ink });
  colL.forEach((r, i) => T(s, r, { x: 0.55, y: 2.08 + i * 0.37, w: 4.6, h: 0.34, fontSize: 12.5, valign: 'middle' }));
  card(s, 5.45, 1.62, 4.0, 3.35, C.soft);
  T(s, 'Дополнительно (2.6)', { x: 5.7, y: 1.75, w: 3.6, h: 0.32, fontFace: H, fontSize: 15, bold: true, color: C.ink });
  colR.forEach((r, i) => T(s, r, { x: 5.7, y: 2.2 + i * 0.65, w: 3.6, h: 0.55, fontSize: 12.5, valign: 'middle' }));
  pageNo(s);
  s.addNotes('Обязательный слайд 8. Все обязательные требования выполнены. Из дополнительных: веб-интерфейс полностью, визуализация — атласами PNG, коррекция — правкой вердикта, DICOM SR пока нет — честно говорим.');
}
{ // 9. Ключевые результаты
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 9);
  title(s, 'Ключевые результаты', 'Сильнее всего — предметы и охват',
    'ROC-AUC по кросс-валидации по исследованиям, 95 % доверительный интервал');
  const k = [['0,88', 'Охват', '0,58–1,00'], ['0,85', 'Посторонние предметы', '0,76–0,94'], ['0,75', 'Поясничный отдел, итог', '0,64–0,84'],
             ['0,66', 'Бедро, итог', '0,62–0,69'], ['0,31 с', 'на снимок, 2 ядра CPU', 'ТЗ: до 3 минут'], ['100 %', 'файлов обработано', 'отказ — с причиной']];
  k.forEach(([b, t, ci], i) => {
    const x = 0.55 + (i % 3) * 3.0, y = 1.72 + Math.floor(i / 3) * 1.68;
    const v = parseFloat(b.replace(',', '.'));
    const [col, soft] = i < 4 ? tone(v) : [C.blue, C.blueSoft];
    card(s, x, y, 2.8, 1.5, soft);
    T(s, b, { x: x + 0.22, y: y + 0.1, w: 2.4, h: 0.8, fontFace: H, fontSize: 40, bold: true, color: col });
    T(s, [{ text: t, options: { bold: true, color: C.ink, breakLine: true } }, { text: ci, options: { color: C.ink3 } }],
      { x: x + 0.22, y: y + 0.88, w: 2.45, h: 0.55, fontSize: 12, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Обязательный слайд 9. Главные цифры: охват 0,88, посторонние предметы 0,85, позвоночник в целом 0,75, бедро 0,66; 0,31 секунды на снимок и 100 % обработанных файлов.');
}
{ // 10. Команда
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 10);
  title(s, 'Команда', '«Квантовый Скачок»', '');
  const team = [['ЮК', 'Юрий Коноплёв', 'капитан команды', '@bimodaling', C.blue],
                ['АЧ', 'Алексей Чуркин', 'участник команды', '@lesha_cfc', C.ink]];
  team.forEach(([ini, name, role, tg, col], i) => {
    const x = 1.2 + i * 4.0;
    card(s, x, 1.55, 3.6, 3.4, C.soft);
    s.addShape(pres.shapes.OVAL, { x: x + 1.2, y: 1.85, w: 1.2, h: 1.2, fill: { color: col } });
    T(s, ini, { x: x + 1.2, y: 1.85, w: 1.2, h: 1.2, fontFace: H, fontSize: 30, bold: true, color: C.white, align: 'center', valign: 'middle' });
    T(s, name, { x: x + 0.2, y: 3.25, w: 3.2, h: 0.45, fontFace: H, fontSize: 21, bold: true, color: C.ink, align: 'center' });
    T(s, role, { x: x + 0.2, y: 3.72, w: 3.2, h: 0.3, fontSize: 13, color: C.blue, align: 'center' });
    T(s, 'Telegram ' + tg, { x: x + 0.2, y: 4.25, w: 3.2, h: 0.3, fontSize: 12, color: C.ink3, align: 'center' });
  });
  pageNo(s);
  s.addNotes('Обязательный слайд 10. В шаблоне оставить две карточки, лишние удалить целиком.');
}
{ // 11. Материалы
  const s = pres.addSlide(); s.background = { color: C.white }; mandatoryTag(s, 11);
  title(s, 'Материалы', 'Всё для проверки — в комплекте сдачи', '');
  const items = [['Стенд', 'ltz2026.ru — загрузка DICOM, дашборд, готовые примеры'], ['Контейнер', 'build.sh · run.sh · serve.sh, запуск без сети'],
                 ['API', 'пакетная обработка архива, описание — ltz2026.ru/docs'], ['Приложение', '.exe · .msi · .deb 1.0-Beta — ltz2026.ru/download'],
                 ['Документация', 'README и руководства: пользователь, развёртывание, обучение'], ['Исходный код', 'репозиторий проекта — в комплекте сдачи']];
  items.forEach(([h, t], i) => {
    const y = 1.62 + i * 0.56;
    num(s, i + 1, 0.55, y + 0.04, C.ink, 0.36);
    T(s, [{ text: h + '  ', options: { bold: true, color: C.ink, fontFace: H } }, { text: t, options: { color: C.ink2 } }],
      { x: 1.08, y, w: 5.7, h: 0.44, fontSize: 13, valign: 'middle' });
  });
  card(s, 7.05, 1.62, 2.4, 2.95, C.soft);
  img(s, 'qr.png', 7.3, 1.8, 1.9, 1.0);
  T(s, 'ltz2026.ru', { x: 7.05, y: 3.85, w: 2.4, h: 0.4, fontFace: H, fontSize: 17, bold: true, color: C.blue, align: 'center' });
  pageNo(s);
  s.addNotes('Обязательный слайд 11. Ссылки на все материалы сдачи; QR ведёт на стенд.');
}

// ------------------------------------------------------------------ 12. Результаты — диаграмма
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Результаты', 'Позвоночник — уверенно, бедро — подсказка',
    'ROC-AUC по критериям · кросс-валидация по исследованиям · 0,5 — угадывание, 1,0 — идеал');
  const labels = ['Охват', 'Посторонние предметы', 'Поля зоны интереса (бедро)', 'Поясничный отдел, итог', 'Наклон оси', 'Бедро, итог', 'Укладка бедра'];
  const vals = [0.88, 0.85, 0.80, 0.75, 0.75, 0.66, 0.62];
  const series = (lo, hi) => vals.map((v) => (v >= lo && v < hi ? v : 0));
  s.addChart(pres.charts.BAR, [
    { name: 'сильный', labels, values: series(0.8, 2) },
    { name: 'средний', labels, values: series(0.7, 0.8) },
    { name: 'слабый', labels, values: series(0, 0.7) },
  ], { x: 0.4, y: 1.6, w: 6.1, h: 3.55, barDir: 'bar', barGrouping: 'stacked', barGapWidthPct: 45,
       chartColors: [C.good, C.mid, C.weak], showValue: true, dataLabelPosition: 'inEnd', dataLabelFormatCode: '0.00;;;',
       dataLabelColor: C.white, dataLabelFontSize: 12, dataLabelFontBold: true, dataLabelFontFace: B,
       valAxisMinVal: 0.5, valAxisMaxVal: 1.0, valAxisMajorUnit: 0.1, valAxisLabelColor: C.ink3, valAxisLabelFontSize: 10,
       catAxisLabelColor: C.ink, catAxisLabelFontSize: 12, catAxisLabelFontFace: B, catAxisOrientation: 'maxMin',
       valGridLine: { color: C.line, size: 0.5 }, catGridLine: { style: 'none' }, showLegend: false });
  const notes = [[C.good, C.goodSoft, '≥ 0,80', 'предметы и охват — можно доверять; поля ROI — мало примеров'],
                 [C.mid, C.midSoft, '0,70–0,80', 'итог по пояснице и наклон оси — сколиоз похож на наклон'],
                 [C.weak, C.weakSoft, '< 0,70', 'бедро — мало размеченного брака, вердикт стоит проверить глазами']];
  notes.forEach(([col, soft, h, t], i) => {
    const y = 1.72 + i * 1.12;
    card(s, 6.75, y, 2.75, 0.98, soft);
    T(s, h, { x: 6.95, y: y + 0.08, w: 2.4, h: 0.34, fontFace: H, fontSize: 16, bold: true, color: col });
    T(s, t, { x: 6.95, y: y + 0.42, w: 2.45, h: 0.52, fontSize: 11, color: C.ink2, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Где сервис силён и где слабее. Посторонние предметы, охват и поля ROI бедра — AUC 0,80–0,88. Поясница в целом и наклон оси — 0,75: мешает сколиоз. Бедро — 0,66: на 150 бёдрах всего 41 брак, вердикт — подсказка.');
}

// ------------------------------------------------------------------ 13. Метрики с ДИ
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Метрики', 'Метрики раздела 8.4 ТЗ с 95 % ДИ',
    '5 фолдов по исследованиям × 50 повторов; порог — только на обучающей части');
  const hd = (t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.ink }, fontSize: 10.5, align: 'center' } });
  const L = (t, b) => ({ text: t, options: { align: 'left', bold: !!b, color: b ? C.ink : C.ink2 } });
  const auc = (t, v) => { const [col, soft] = tone(v); return { text: t, options: { bold: true, color: col, fill: { color: soft } } }; };
  const rows = [
    [hd('Критерий'), hd('Брак / всего'), hd('Чувствит.'), hd('Специф.'), hd('Сбаланс. точность'), hd('F1 (95 % ДИ)'), hd('ROC-AUC (95 % ДИ)')],
    [L('Поясничный отдел, итог', 1), '32 / 99', '0,69', '0,67', '0,68', '0,58 (0,46–0,74)', auc('0,75 (0,64–0,84)', 0.75)],
    [L('   охват'), '6 / 99', '0,67', '0,98', '0,82', '0,69 (0,40–0,93)', auc('0,88 (0,58–1,00)', 0.88)],
    [L('   наклон оси'), '10 / 99', '0,41', '0,86', '0,63', '0,30 (0,11–0,60)', auc('0,75 (0,55–0,91)', 0.75)],
    [L('   посторонние предметы'), '17 / 99', '0,68', '0,84', '0,76', '0,55 (0,34–0,72)', auc('0,85 (0,76–0,94)', 0.85)],
    [L('Бедро, итог', 1), '41 / 150', '0,65', '0,57', '0,61', '0,47', auc('0,66 (0,62–0,69)', 0.66)],
    [L('   укладка и ротация'), '36 / 150', '—', '—', '—', '—', auc('0,62', 0.62)],
    [L('   поля зоны интереса'), '7 / 150', '—', '—', '—', '—', auc('0,80', 0.80)],
  ];
  s.addTable(rows, { x: 0.55, y: 1.68, w: 8.9, colW: [2.15, 1.0, 0.9, 0.9, 1.15, 1.4, 1.4], fontFace: B, fontSize: 11, color: C.ink2, align: 'center',
                     rowH: 0.33, valign: 'middle', border: { type: 'solid', pt: 0.75, color: C.line } });
  card(s, 0.55, 4.5, 8.9, 0.55, C.blueSoft);
  T(s, [{ text: 'Сводная фитнес-функция 0,58  ', options: { bold: true, color: C.ink, fontFace: H } },
        { text: '0,35·F1 + 0,35·ROC-AUC по областям + 0,30·macro-F1 типов; базовая линия 0,570 (0,477–0,644)', options: { color: C.ink2 } }],
    { x: 0.8, y: 4.5, w: 8.5, h: 0.55, fontSize: 12, valign: 'middle' });
  pageNo(s);
  s.addNotes('Метрики — как просит раздел 8.4 ТЗ: по областям и типам нарушений, чувствительность, специфичность, сбалансированная точность, F1 и ROC-AUC с 95 % ДИ. Цвет — сила результата.');
}

// ------------------------------------------------------------------ 14. Эксперименты
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Эксперименты', 'Главная победа — детектор предметов',
    'ROC-AUC 0,55 → 0,85 · что пробовали, что оставили и почему');
  const hd = { bold: true, color: C.white, fill: { color: C.ink }, fontSize: 11 };
  s.addTable([
    [{ text: 'Модель для бедра', options: hd }, { text: 'ROC-AUC', options: hd }],
    ['Логистическая регрессия, 21 признак', '0,60'], ['Признаки ResNet-50 / DINOv2', 'до 0,64'], ['Признаки RAD-DINO', '0,64'],
    ['Бустинг · каскадный лес · Viola–Jones', 'не выше 0,66'],
    [{ text: 'ExtraTrees, 47 признаков — выбрана', options: { bold: true, color: C.ink } }, { text: '0,66', options: { bold: true, color: C.blue } }],
    ['ExtraTrees + RAD-DINO', '0,67 — в пределах ДИ'],
  ], { x: 0.55, y: 1.72, w: 4.7, colW: [3.3, 1.4], fontFace: B, fontSize: 11.5, color: C.ink2, rowH: 0.4, border: { type: 'solid', pt: 0.75, color: C.line } });
  const lessons = [[C.good, C.goodSoft, 'Предметы: 0,55 → 0,85', 'локальный контраст пятна вместо порога яркости'],
                   [C.mid, C.midSoft, 'Ось: сколиоз', 'изгиб столба похож на наклон; три другие меры оси — хуже'],
                   [C.weak, C.weakSoft, 'Бедро: мало сигнала', 'нужна разметка ротации по малому вертелу и масштаб в мм']];
  lessons.forEach(([col, soft, h, t], i) => {
    const y = 1.72 + i * 1.12;
    card(s, 5.55, y, 3.9, 0.98, soft);
    T(s, h, { x: 5.8, y: y + 0.1, w: 3.5, h: 0.34, fontFace: H, fontSize: 15, bold: true, color: col });
    T(s, t, { x: 5.8, y: y + 0.46, w: 3.5, h: 0.48, fontSize: 11.5, color: C.ink2, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Сравнили семь вариантов для бедра — выбрали ExtraTrees; добавка признаков RAD-DINO даёт +0,01 в пределах интервала и требует PyTorch. Главная победа — детектор посторонних предметов: AUC с 0,55 до 0,85. Ошибки по оси связаны со сколиозом.');
}

// ------------------------------------------------------------------ 15. Скорость
{
  const s = pres.addSlide(); s.background = { color: C.night };
  title(s, 'Скорость', 'Секунда вместо допустимых 3 минут',
    'Замер в контейнере без сети: 2 ядра CPU, 4 ГБ памяти, без видеокарты', true);
  const st = [['0,31 с', 'на снимок\nТЗ: до 3 минут'], ['90 с', 'весь обучающий набор\n252 снимка'], ['100 %', 'файлов обработано\nбез сбоев'], ['191 МБ', 'пик памяти\nпроцесса']];
  st.forEach(([b, t], i) => {
    const x = 0.55 + i * 2.25;
    T(s, b, { x, y: 1.75, w: 2.2, h: 0.95, fontFace: H, fontSize: 36, bold: true, color: i === 0 ? '5EE0A8' : C.white });
    T(s, t, { x, y: 2.72, w: 2.05, h: 0.6, fontSize: 12.5, color: C.nightMute, valign: 'top' });
  });
  const req = [['Минимум', '2 ядра, 4 ГБ памяти, 64-битный Linux; образ контейнера 2,3 ГБ'],
               ['Сеть', 'не нужна: контейнер запускается с --network none'],
               ['Воспроизводимость', 'версии зафиксированы, повторный прогон побайтно совпадает']];
  req.forEach(([h, t], i) => {
    const y = 3.65 + i * 0.44;
    T(s, h, { x: 0.55, y, w: 2.5, h: 0.38, fontFace: H, fontSize: 14, bold: true, color: C.white, valign: 'middle' });
    T(s, t, { x: 3.1, y, w: 6.4, h: 0.38, fontSize: 13, color: C.nightText, valign: 'middle' });
  });
  pageNo(s, true);
  s.addNotes('На слабой машине без видеокарты — 0,31 секунды на снимок, исследование из трёх снимков — около секунды против 3 минут по ТЗ, весь набор за 90 секунд, 191 мегабайт памяти. Сеть не нужна, результаты воспроизводимы.');
}

// ------------------------------------------------------------------ 16. Кейс
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Кейс', 'Предмет найден за секунду — и объяснён',
    'Дашборд исследования и граф решения · синтетический фантом');
  card(s, 0.55, 1.68, 5.6, 3.4, C.soft);
  img(s, 'dash_gallery.png', 0.75, 1.82, 5.2, 1.986);
  const steps = [['Галерея', 'красная рамка — брак, причина под снимком'], ['Карточка', 'проверки по критериям ТЗ одним нажатием'], ['Выгрузка', 'XLSX / CSV по ТЗ 2.5 и атласы в ZIP']];
  steps.forEach(([h, t], i) => {
    const x = 0.75 + i * 1.8;
    T(s, [{ text: h, options: { bold: true, color: C.ink, fontFace: H, breakLine: true } }, { text: t, options: { color: C.ink3 } }],
      { x, y: 4.5, w: 1.7, h: 0.55, fontSize: 10.5, valign: 'top' });
  });
  card(s, 6.35, 1.68, 3.1, 3.4, C.soft);
  img(s, 'graph.png', 6.5, 1.82, 2.8, 1.176);
  T(s, [{ text: 'Граф решения', options: { bold: true, color: C.ink, fontFace: H, breakLine: true } },
        { text: 'измерение против нормы по каждой проверке → вердикт; сворачивается в текст', options: { color: C.ink3 } }],
    { x: 6.5, y: 4.3, w: 2.8, h: 0.75, fontSize: 11, valign: 'top' });
  pageNo(s);
  s.addNotes('Кейс на синтетическом фантоме: застёжка рядом с позвоночником. Результат виден сразу в галерее: красная рамка и причина. Карточка — проверки по ТЗ, граф — измеренный контраст против нормы 55.');
}

// ------------------------------------------------------------------ 17. На самом снимке
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Объяснимость', 'Результат — прямо на снимке',
    'Врач видит вердикт там, где привык: атлас с разметкой или чистый рентген');
  card(s, 0.55, 1.68, 4.75, 3.45, C.night);
  img(s, 'atlas.png', 0.7, 1.8, 4.45, 1.314);
  img(s, 'card_spine.png', 5.5, 1.68, 1.38, 0.4016);
  const pts = [['Разметка', 'позвонки, ось и зоны подписаны на снимке'], ['Причина', 'предмет в рамке, критерий ТЗ отмечен ✕'],
               ['Измерение', 'угол, контраст, вероятность — рядом с нормой'], ['Сомнение', '«предмет? или ребро» — честная пометка']];
  pts.forEach(([h, t], i) => {
    const y = 1.72 + i * 0.86;
    T(s, h, { x: 7.1, y, w: 2.4, h: 0.32, fontFace: H, fontSize: 15, bold: true, color: C.ink });
    T(s, t, { x: 7.1, y: y + 0.32, w: 2.35, h: 0.5, fontSize: 11.5, color: C.ink2, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Результаты — только на снимках: атлас с разметкой позвонков, оси и найденного предмета; переключатель показывает чистый рентген. Если пятна похожи на рёбра, сервис прямо пишет «проверьте».');
}

// ------------------------------------------------------------------ 18. Продукт
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Продукт', 'Готово к использованию уже сейчас', 'Стенд, контейнер, API и настольное приложение Kostik 1.0-Beta');
  card(s, 0.55, 1.68, 5.1, 3.4, C.soft);
  img(s, 'download2.png', 0.7, 1.82, 4.8, 1.714);
  const items = [['Веб-стенд', 'ltz2026.ru — загрузка, дашборд, примеры'], ['Приложение', '.exe · .msi · .deb, офлайн, подписанные суммы'],
                 ['Контейнер', 'сборка и запуск одной командой, как в ТЗ'], ['Интеграции', 'HTTP API · MCP · Telegram-бот'],
                 ['Чужой файл', 'объяснит, что загружено и что делать']];
  items.forEach(([h, t], i) => {
    const y = 1.7 + i * 0.68;
    num(s, '✓', 5.9, y + 0.04, C.good, 0.34);
    T(s, h, { x: 6.38, y, w: 3.1, h: 0.3, fontFace: H, fontSize: 14, bold: true, color: C.ink });
    T(s, t, { x: 6.38, y: y + 0.3, w: 3.1, h: 0.34, fontSize: 11.5, color: C.ink2, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Продукт можно попробовать прямо сейчас: стенд ltz2026.ru, приложение для Windows и Linux со страницы загрузки, контейнер по ТЗ.');
}

// ------------------------------------------------------------------ 19. Демонстрация
{
  const s = pres.addSlide(); s.background = { color: C.night };
  title(s, 'Демонстрация', 'Две минуты — от загрузки до таблицы', 'Сценарий показа на защите', true);
  const steps = [['Загрузка', 'на главной перетаскиваем архив DICOM или выбираем готовый пример'],
                 ['Дашборд', 'сводка: исследования, годные, с нарушениями, время на снимок'],
                 ['Снимок с браком', 'красная рамка в галерее → карточка: предмет в рамке на атласе'],
                 ['Пояснение', 'граф решения: контраст против нормы → вердикт; переключаем в текст'],
                 ['Выгрузка', 'таблица XLSX по ТЗ 2.5 и ZIP с атласами; то же — в приложении без интернета']];
  steps.forEach(([h, t], i) => {
    const y = 1.72 + i * 0.66;
    num(s, i + 1, 0.55, y + 0.06, C.blue, 0.38);
    T(s, h, { x: 1.15, y, w: 2.5, h: 0.5, fontFace: H, fontSize: 15, bold: true, color: C.white, valign: 'middle' });
    T(s, t, { x: 3.75, y, w: 5.75, h: 0.5, fontSize: 13, color: C.nightText, valign: 'middle' });
  });
  pageNo(s, true);
  s.addNotes('Сценарий живой демонстрации: загрузка, дашборд, снимок с браком, пояснение, выгрузка. Подробно — doc/DEMO.md.');
}

// ------------------------------------------------------------------ 20. Ограничения и внедрение
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, 'Внедрение', 'Честно о пределах и план пилота', '');
  const lim = ['Бедро — подсказка: ROC-AUC 0,66, нужна разметка ротации', 'Сколиоз путается с наклоном оси',
               'Th12 определяется приблизительно', 'Поля в сантиметрах: в DICOM нет масштаба'];
  card(s, 0.55, 1.6, 4.2, 3.45, C.weakSoft);
  T(s, 'Ограничения', { x: 0.8, y: 1.75, w: 3.8, h: 0.34, fontFace: H, fontSize: 16, bold: true, color: C.weak });
  T(s, lim.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lim.length - 1 } })),
    { x: 0.8, y: 2.2, w: 3.8, h: 2.7, fontSize: 13, color: C.ink2, valign: 'top', paraSpaceAfter: 10 });
  const plan = [['Пилот', '1–2 отделения: проверка каждого снимка в день исследования'], ['Разметка', 'врачи правят спорные вердикты в пульте — данные для дообучения'],
                ['Бедро и Th12', 'разметка малого вертела и уровней, масштаб от аппарата'], ['Масштаб', 'интеграция с PACS / ЕРИС, отчёт о качестве отделений']];
  plan.forEach(([h, t], i) => {
    const y = 1.62 + i * 0.86;
    num(s, i + 1, 5.05, y + 0.04, C.blue, 0.38);
    T(s, h, { x: 5.6, y, w: 3.9, h: 0.32, fontFace: H, fontSize: 15, bold: true, color: C.ink });
    T(s, t, { x: 5.6, y: y + 0.32, w: 3.85, h: 0.48, fontSize: 12, color: C.ink2, valign: 'top' });
  });
  pageNo(s);
  s.addNotes('Ограничения мы называем открыто. План: пилот в отделениях, сбор уточнённой разметки прямо в интерфейсе, дообучение бедра и Th12, затем интеграция с PACS и ЕРИС.');
}

// ------------------------------------------------------------------ 21. Финал
{
  const s = pres.addSlide(); s.background = { color: C.night };
  card(s, 6.4, 1.0, 3.0, 3.55, C.white);
  img(s, 'qr.png', 6.65, 1.2, 2.5, 1.0);
  T(s, 'ltz2026.ru', { x: 6.4, y: 3.85, w: 3.0, h: 0.5, fontFace: H, fontSize: 21, bold: true, color: C.night, align: 'center' });
  eyebrow(s, 'Kostik', true, 0.55, 0.95);
  T(s, 'Попробуйте сами', { x: 0.52, y: 1.25, w: 5.7, h: 0.8, fontFace: H, fontSize: 36, bold: true, color: C.white });
  T(s, 'Проверка снимка, готовые примеры, приложение для Windows и Linux. Без интернета — снимки не покидают медорганизацию.',
    { x: 0.55, y: 2.15, w: 5.4, h: 0.85, fontSize: 15, color: C.nightText, valign: 'top' });
  T(s, [{ text: 'Команда «Квантовый Скачок»', options: { bold: true, color: C.white, fontFace: H, breakLine: true } },
        { text: 'Юрий Коноплёв · Алексей Чуркин', options: { color: C.nightText, breakLine: true } },
        { text: 'Telegram: @bimodaling · @lesha_cfc', options: { color: C.nightMute } }],
    { x: 0.55, y: 3.55, w: 5.4, h: 1.0, fontSize: 14 });
  s.addNotes('Спасибо! Всё можно попробовать на ltz2026.ru. Готовы ответить на вопросы.');
}

pres.writeFile({ fileName: path.join(__dirname, 'Kostik_presentation.pptx') }).then(f => console.log('готово:', f));
