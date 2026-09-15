# -*- coding: utf-8 -*-
"""ЛЦТ 2026 — инфографика по выбору задачи + разбор задачи 04 (денситометрия)."""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

FONT_DIR = "/usr/share/fonts/truetype/noto/"
pdfmetrics.registerFont(TTFont("NS", FONT_DIR + "NotoSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("NS-B", FONT_DIR + "NotoSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("ND-B", FONT_DIR + "NotoSansDisplay-Bold.ttf"))

W, H = A4
M = 42.0
CW = W - 2 * M

SURFACE = HexColor("#fcfcfb")
INK = HexColor("#0b0b0b")
INK2 = HexColor("#52514e")
INK3 = HexColor("#8a8983")
RULE = HexColor("#e2e1dc")
EMPTY = HexColor("#e8e7e3")
TINT = HexColor("#eef4fd")

# ordinal blue ramp (steps 250 / 450 / 550 — все выше порога 2:1 к светлой подложке)
ORD = [HexColor("#86b6ef"), HexColor("#2a78d6"), HexColor("#1c5cab")]
BLUE = HexColor("#2a78d6")
DEEP = HexColor("#104281")
RED = HexColor("#e34948")

TASKS = [
    ("02", "Трассировка тепловых сетей", "ДИТ · коммуникации", 3, 2, 3),
    ("10", "Изменения между стадиями проекта", "Стройнадзор · градмоделирование", 3, 2, 3),
    ("05", "Объекты в тоннеле метро по лидару", "Мостранспорт · транспорт", 3, 3, 3),
    ("08", "Прогноз аварий коллекторов", "ДЖКХ · ЖКХ", 3, 3, 3),
    ("09", "Симулятор диспетчеров службы 112", "ДГОЧСиПБ · социальные", 2, 1, 2),
    ("04", "Качество исследований плотности костей", "Депздрав · социальные", 2, 3, 3),
    ("03", "Автопроектирование озеленения", "Природа Москвы · социальные", 2, 2, 2),
    ("07", "Мониторинг стройплощадки", "Депстрой · строительство", 1, 1, 2),
    ("01", "Подбор роботизированных решений", "ДПИИР и ФЦ БАС · промышленность", 1, 1, 1),
    ("06", "Финансовая грамотность молодёжи", "Депфин · финансы", 1, 1, 1),
]

c = canvas.Canvas("/home/jk/exp/LTZ2026/LCT2026_analysis.pdf", pagesize=A4)
c.setTitle("ЛЦТ 2026 — выбор задачи и разбор задачи 04")
c.setAuthor("анализ подготовлен в Claude Code")


def y(off):
    return H - off


def bg():
    c.setFillColor(SURFACE)
    c.rect(0, 0, W, H, stroke=0, fill=1)


def txt(x, yy, s, font="NS", size=9, color=INK, align="l"):
    c.setFont(font, size)
    c.setFillColor(color)
    if align == "l":
        c.drawString(x, yy, s)
    elif align == "r":
        c.drawRightString(x, yy, s)
    else:
        c.drawCentredString(x, yy, s)


def wrap(s, font, size, width):
    words, lines, cur = s.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if pdfmetrics.stringWidth(t, font, size) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def para(x, yy, s, width, font="NS", size=8.6, color=INK2, lead=11.5):
    for i, ln in enumerate(wrap(s, font, size, width)):
        txt(x, yy - i * lead, ln, font, size, color)
    return yy - (len(wrap(s, font, size, width)) - 1) * lead


def fit(s_, font, size, width):
    if pdfmetrics.stringWidth(s_, font, size) <= width:
        return s_
    while s_ and pdfmetrics.stringWidth(s_ + "…", font, size) > width:
        s_ = s_[:-1]
    return s_.rstrip() + "…"


def ladder(x, yy, level, w=7.0, gap=3.0):
    """Ординальный глиф: три столбика, залито ровно level штук."""
    hs = (6.0, 10.5, 15.0)
    for i in range(3):
        c.setFillColor(ORD[i] if i < level else EMPTY)
        c.roundRect(x + i * (w + gap), yy, w, hs[i], 2, stroke=0, fill=1)


def page1():
    bg()
    txt(M, y(58), "ХАКАТОН «ЛИДЕРЫ ЦИФРОВОЙ ТРАНСФОРМАЦИИ» · 2026", "NS-B", 8, BLUE)
    txt(M, y(84), "Какую задачу брать", "ND-B", 27, INK)
    para(M, y(103), "Десять городских задач из личного кабинета, оценённые по трём осям: шанс взять приз, "
                    "риск остаться без данных и польза после хакатона. Оценка сделана по карточкам задач, "
                    "тексты «Подробнее» не раскрывались.", CW * 0.82, size=8.8, lead=11.4)

    # дедлайн
    top = y(146)
    c.setFillColor(HexColor("#fdeceb"))
    c.roundRect(M, top - 30, CW, 30, 5, stroke=0, fill=1)
    c.setFillColor(RED)
    c.roundRect(M, top - 30, 3.2, 30, 1.6, stroke=0, fill=1)
    txt(M + 14, top - 19.5, "Приём заявок закрывается 14 сентября", "NS-B", 10, HexColor("#8f2624"))
    txt(W - M - 14, top - 19.5, "осталось 4 дня", "NS", 9, HexColor("#8f2624"), align="r")

    # таймлайн
    ty = y(206)
    c.setStrokeColor(RULE)
    c.setLineWidth(2)
    c.line(M + 6, ty, W - M - 6, ty)
    miles = [("14 сен", "заявки"), ("15–29 сен", "разработка"), ("30 сен – 14 окт", "экспертиза"),
             ("23 окт", "защита"), ("30 окт", "награда")]
    step = CW / (len(miles) - 1)
    for i, (d, lab) in enumerate(miles):
        x = M + 6 + i * (CW - 12) / (len(miles) - 1)
        c.setFillColor(RED if i == 0 else BLUE)
        c.circle(x, ty, 4.2, stroke=0, fill=1)
        al = "c"
        if i == 0:
            al, x2 = "l", x - 4
        elif i == len(miles) - 1:
            al, x2 = "r", x + 4
        else:
            x2 = x
        txt(x2, ty + 12, d, "NS-B", 8.4, INK if i else HexColor("#8f2624"), align=al)
        txt(x2, ty - 16, lab, "NS", 7.6, INK3, align=al)

    # шапка таблицы
    hy = y(266)
    txt(M, hy, "ЗАДАЧА", "NS-B", 7.4, INK3)
    cols = [("ШАНС ПРИЗА", 330), ("РИСК ДАННЫХ", 396), ("ПОЛЬЗА ПОСЛЕ", 462)]
    for name, cx in cols:
        txt(cx + 13.5, hy, name, "NS-B", 6.8, INK3, align="c")
    txt(W - M, hy, "ИТОГ", "NS-B", 7.4, INK3, align="r")
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(M, hy - 8, W - M, hy - 8)

    row_h = 31.0
    ry = hy - 8
    for num, title, cust, prize, risk, val in TASKS:
        score = prize + val - risk
        if num == "04":
            c.setFillColor(TINT)
            c.roundRect(M - 6, ry - row_h + 3, CW + 12, row_h - 2, 4, stroke=0, fill=1)
        txt(M, ry - 15, num, "ND-B", 13, HexColor("#c9c8c2") if num != "04" else BLUE)
        txt(M + 26, ry - 13, fit(title, "NS-B", 9.2, 252), "NS-B", 9.2, INK)
        txt(M + 26, ry - 23.5, fit(cust, "NS", 7.4, 252), "NS", 7.4, INK3)
        for lvl, (_, cx) in zip((prize, risk, val), cols):
            ladder(cx, ry - 23, lvl)
        txt(W - M, ry - 17, str(score), "ND-B", 12, DEEP if score >= 3 else HexColor("#a9a8a2"), align="r")
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(M, ry - row_h, W - M, ry - row_h)
        ry -= row_h

    # легенда
    ly = ry - 20
    txt(M, ly, "ШКАЛА", "NS-B", 7.4, INK3)
    lx = M + 46
    for i, lab in enumerate(("низкий", "средний", "высокий")):
        ladder(lx, ly - 4, i + 1, w=5.0, gap=2.2)
        txt(lx + 26, ly, lab, "NS", 8, INK2)
        lx += 92
    txt(W - M, ly, "итог = шанс приза + польза после - риск по данным", "NS", 7.6, INK3, align="r")

    # выводы
    by = ly - 34
    c.setFillColor(HexColor("#f4f3f0"))
    c.roundRect(M, by - 96, CW, 96, 6, stroke=0, fill=1)
    txt(M + 16, by - 20, "ЧТО ИЗ ЭТОГО СЛЕДУЕТ", "NS-B", 7.6, INK3)
    picks = [
        ("Хочешь приз", "Теплосети и лидар в метро: измеримый критерий и высокий порог входа, случайных команд там мало."),
        ("Хочешь внедрение", "Коллекторы и стадии проектирования: операционная боль города с понятным владельцем бюджета."),
        ("Не бери без причины", "Роботы, финграмотность и стройплощадка: прототип за выходные, побеждает презентация, а не код."),
    ]
    py = by - 36
    for head, body in picks:
        c.setFillColor(BLUE)
        c.circle(M + 19, py + 3, 2.4, stroke=0, fill=1)
        txt(M + 28, py, head, "NS-B", 8.6, INK)
        w0 = pdfmetrics.stringWidth(head + "  ", "NS-B", 8.6)
        avail = CW - 44 - w0
        lines = wrap(body, "NS", 8.6, avail)
        txt(M + 28 + w0, py, lines[0], "NS", 8.6, INK2)
        for k, ln in enumerate(lines[1:]):
            txt(M + 28, py - 11 * (k + 1), ln, "NS", 8.6, INK2)
        py -= 20 + 11 * (len(lines) - 1)

    txt(M, 30, "ЛЦТ 2026 · i.moscow/lct", "NS", 7.2, INK3)
    txt(W - M, 30, "1 / 3", "NS", 7.2, INK3, align="r")
    c.showPage()


def head(title, sub, page):
    bg()
    txt(M, y(52), "РАЗБОР ЗАДАЧИ 04 · ДЕПЗДРАВ", "NS-B", 8, BLUE)
    txt(M, y(76), title, "ND-B", 20, INK)
    para(M, y(94), sub, CW * 0.86, size=8.8, lead=11.4)
    txt(M, 30, "ЛЦТ 2026 · задача 04", "NS", 7.2, INK3)
    txt(W - M, 30, f"{page} / 3", "NS", 7.2, INK3, align="r")


def page2():
    head("Оценка качества исследований плотности костей",
         "Денситометрия DXA. Ключевое различие: заказчику нужна не диагностика остеопороза, "
         "а вердикт о пригодности самого исследования и названная причина брака.", 2)

    yy = y(140)
    txt(M, yy, "ЧТО ПРОВЕРЯЕТ АУДИТОР DXA", "NS-B", 7.6, INK3)
    yy -= 16
    checks = [
        ("Укладка поясничного отдела", "L1–L4 по центру и без наклона, в кадре половина Т12 и половина L5."),
        ("Укладка бедра", "Внутренняя ротация 15–25°, малый вертел почти не виден, шейка по центру."),
        ("Артефакты", "Металл, украшения, пуговицы, остатки контраста, смазывание от движения."),
        ("Разметка областей", "Границы позвонков и линия шейки бедра, корректность автоконтуров аппарата."),
        ("Исключение позвонков", "Деформации и остеофиты, разница T-score с соседним позвонком больше 1,0 по ISCD."),
        ("Отчёт и шкала", "T или Z по возрасту и полу, референсная база, соответствие заключения цифрам."),
    ]
    col_w = (CW - 18) / 2
    for i, (h_, b_) in enumerate(checks):
        cx = M + (i % 2) * (col_w + 18)
        cy = yy - (i // 2) * 62
        c.setFillColor(HexColor("#f4f3f0"))
        c.roundRect(cx, cy - 52, col_w, 52, 5, stroke=0, fill=1)
        c.setFillColor(BLUE)
        c.roundRect(cx, cy - 52, 2.6, 52, 1.3, stroke=0, fill=1)
        txt(cx + 12, cy - 17, h_, "NS-B", 9, INK)
        para(cx + 12, cy - 29, b_, col_w - 24, size=7.8, lead=10)

    # конвейер
    py = yy - 3 * 62 - 22
    txt(M, py, "КАК СОБИРАТЬ РЕШЕНИЕ", "NS-B", 7.6, INK3)
    py -= 14
    stages = [
        ("Вход", "DICOM или вторичный снимок отчёта, анонимизация тегов"),
        ("Три ветки", "геометрия укладки · артефакты и контуры · правила по метаданным и тексту"),
        ("Агрегатор", "чек-лист превращается в один вердикт с весами"),
        ("Выход", "карточка качества: годно или нет, причина, тепловая карта, что переснять"),
    ]
    bw = (CW - 3 * 20) / 4
    for i, (h_, b_) in enumerate(stages):
        bx = M + i * (bw + 20)
        c.setFillColor(HexColor("#eef4fd") if i < 3 else HexColor("#e3edfb"))
        c.roundRect(bx, py - 74, bw, 74, 5, stroke=0, fill=1)
        txt(bx + 10, py - 20, h_, "NS-B", 9.4, DEEP)
        para(bx + 10, py - 33, b_, bw - 20, size=7.6, lead=9.6)
        if i < 3:
            c.setFillColor(HexColor("#b9c6d8"))
            ax = bx + bw + 7
            p = c.beginPath()
            p.moveTo(ax, py - 37 + 4.5)
            p.lineTo(ax + 6, py - 37)
            p.lineTo(ax, py - 37 - 4.5)
            p.close()
            c.drawPath(p, stroke=0, fill=1)

    ny = py - 92
    c.setFillColor(HexColor("#fdf6e8"))
    c.roundRect(M, ny - 46, CW, 46, 5, stroke=0, fill=1)
    txt(M + 14, ny - 18, "Где выигрывается эта задача", "NS-B", 9, HexColor("#7a5200"))
    para(M + 14, ny - 31, "Не долями процента точности, а полнотой чек-листа и объяснимостью: "
                          "врач должен увидеть причину брака и решение о пересъёмке, а не голую вероятность.",
         CW - 28, size=8.2, lead=10.4, color=HexColor("#7a5200"))

    qy = ny - 74
    c.setFillColor(HexColor("#f4f3f0"))
    c.roundRect(M, qy - 108, CW, 108, 6, stroke=0, fill=1)
    txt(M + 16, qy - 22, "СПРОСИТЬ У ЗАКАЗЧИКА ДО 14 СЕНТЯБРЯ", "NS-B", 7.6, INK3)
    qs = [
        "Объём датасета и есть ли экспертная разметка причин брака, а не только вердикт «годно / негодно»",
        "Что отдают: сырые DICOM со снимком или вторичный снимок отчёта с уже нанесённой разметкой",
        "Производители аппаратов: разметка и артефакты у GE Lunar и Hologic различаются",
        "Куда встраивается результат: ЕРИС, отдельный дашборд аудита или выгрузка отчётом",
    ]
    py2 = qy - 42
    for q in qs:
        c.setFillColor(DEEP)
        c.circle(M + 19, py2 + 3, 2.2, stroke=0, fill=1)
        txt(M + 28, py2, fit(q, "NS", 8.4, CW - 46), "NS", 8.4, INK2)
        py2 -= 17
    c.showPage()


def page3():
    head("План на две недели, метрика и риски",
         "Разработка идёт с 15 по 29 сентября. Разбивка оставляет три дня на демо, интеграцию и репетицию защиты.", 3)

    yy = y(146)
    txt(M, yy, "ПЛАН РАЗРАБОТКИ", "NS-B", 7.6, INK3)
    phases = [
        (1, 2, "Данные", "Инвентарь тегов DICOM, дисбаланс классов, схема валидации со сплитом по пациенту, а не по снимку"),
        (3, 5, "Базовая линия", "Классификатор брака на предобученном backbone плюс проверки по метаданным и тексту отчёта"),
        (6, 9, "Геометрия", "Сегментация и ключевые точки, метрики укладки как явные признаки: наклон, симметрия, ротация бедра"),
        (10, 12, "Продукт", "Агрегатор чек-листа, объяснимость через тепловые карты, веб-демо с загрузкой исследования"),
        (13, 14, "Сдача", "Формат обмена с ЕРИС, прогон на отложенной выборке, видео и репетиция защиты"),
    ]
    gx = M + 108
    gw = CW - 108
    day = gw / 14.0
    ry = yy - 16
    for d in (1, 4, 7, 10, 14):
        px = gx + (d - 1) * day
        txt(px, ry, "день 1" if d == 1 else str(d), "NS", 7, INK3)
    ry -= 12
    for i, (d0, d1, name, body) in enumerate(phases):
        bx = gx + (d0 - 1) * day
        bwid = (d1 - d0 + 1) * day - 3
        c.setFillColor(ORD[min(2, i // 2)])
        c.roundRect(bx, ry - 13, bwid, 13, 4, stroke=0, fill=1)
        txt(M, ry - 4, name, "NS-B", 9, INK)
        txt(M, ry - 14.5, "дни %d\u2013%d" % (d0, d1), "NS", 7.2, INK3)
        end = para(gx, ry - 26, body, gw - 4, size=7.9, lead=9.9)
        ry = min(ry - 44, end - 16)

    by = ry - 10
    col_w = (CW - 20) / 2
    txt(M, by, "ЧЕМ МЕРИТЬ", "NS-B", 7.6, INK3)
    txt(M + col_w + 20, by, "ГЛАВНЫЕ РИСКИ", "NS-B", 7.6, INK3)
    by -= 17
    metrics = [
        "Полнота по браку при зафиксированной доле ложных тревог, а не ROC-AUC в вакууме",
        "Macro-F1 по причинам брака: важен редкий класс, а не среднее по выборке",
        "Доля исследований, где причина названа верно. Именно это и есть польза для врача",
    ]
    risks = [
        "Датасет на сотни исследований и шумная разметка: согласие экспертов по укладке низкое",
        "Дисбаланс: брака обычно от 5 до 15 процентов, случайный сплит даёт утечку по пациенту",
        "Персональные данные в тегах DICOM: анонимизация нужна до первого эксперимента",
    ]
    bottom = by
    for col, items in ((0, metrics), (1, risks)):
        cx = M + col * (col_w + 20)
        cy = by
        for it in items:
            c.setFillColor(BLUE if col == 0 else RED)
            c.circle(cx + 3, cy + 3, 2.2, stroke=0, fill=1)
            end = para(cx + 12, cy, it, col_w - 16, size=8.2, lead=10.4)
            cy = end - 15
        bottom = min(bottom, cy)

    dy = bottom - 14
    txt(M, dy, "ЧТО ПОКАЗАТЬ НА ЗАЩИТЕ", "NS-B", 7.6, INK3)
    dy -= 17
    demo = [
        "Живую загрузку исследования и карточку качества за секунды, без слайда с архитектурой сети",
        "Две-три реальные ошибки укладки, которые сервис поймал, и честно одну, которую пропустил",
        "Сколько исследований в сутки закрывает сервис и сколько времени аудитора это экономит",
    ]
    for d_ in demo:
        c.setFillColor(DEEP)
        c.circle(M + 3, dy + 3, 2.2, stroke=0, fill=1)
        end = para(M + 12, dy, d_, CW - 16, size=8.2, lead=10.4)
        dy = end - 14

    fy = dy - 6
    c.setFillColor(HexColor("#eef4fd"))
    c.roundRect(M, fy - 92, CW, 92, 6, stroke=0, fill=1)
    txt(M + 16, fy - 22, "ВЕРДИКТ ПО ЗАДАЧЕ 04", "NS-B", 7.6, INK3)
    para(M + 16, fy - 40, "Задача берётся только вместе с данными. Если экспертной разметки причин брака нет, "
                          "за две недели выйдет демонстратор, а не решение, и приз уедет к тем, у кого метрика считается.",
         CW - 32, size=8.6, lead=11, color=INK)
    para(M + 16, fy - 68, "Если разметка есть, это лучшая задача в списке по соотношению «понятная метрика плюс "
                          "строчка в портфолио», и конкурентов там заметно меньше, чем в задачах без медицины.",
         CW - 32, size=8.6, lead=11, color=INK)
    c.showPage()


page1()
page2()
page3()
c.save()
print("ok")
