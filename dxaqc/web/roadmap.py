# -*- coding: utf-8 -*-
"""Роудмап развития стенда: направления, инициативы, оценки в режиме вайбкодинга и рекомендуемый путь.

Оценки двух видов. Время агента — сколько работает Claude: код, тесты, деплой, проверка в браузерах, пока человек
занят своим. Время человека — решения, просмотр результатов, разметка спорных случаев, репетиции. В вайбкодинге
узкое место не код, а человеческое внимание и данные, поэтому второе число важнее первого.

Статус инициативы — по фактам на стенде, а не по трекеру: часть тикетов эпика MVP в трекере открыта, хотя работа
сделана. Статусы тикетов показываются рядом отдельно и берутся из трекера вживую.
"""
from __future__ import annotations

import time

DIRECTIONS = [
    dict(id="quality", title="Качество анализа", sub="точность вердиктов и честная оценка"),
    dict(id="tz", title="Требования ТЗ и сдача", sub="то, без чего решение не примут"),
    dict(id="defense", title="Презентация и защита", sub="как решение увидит жюри"),
    dict(id="doctor", title="Работа врача", sub="сервис в руках медорганизации"),
    dict(id="ops", title="Эксплуатация", sub="надёжность стенда"),
    dict(id="integr", title="Интеграции", sub="каналы и внешние системы"),
]
PHASES = [
    dict(id="now", title="Сейчас", until="до 20.09", deadline="2026-09-20"),
    dict(id="final", title="К финальной версии", until="до 29.09", deadline="2026-09-29"),
    dict(id="defense", title="К защите", until="до 23.10", deadline="2026-10-23"),
    dict(id="later", title="Перспектива", until="после защиты", deadline=None),
]
SIZES = {"S": "до часа агента", "M": "1–3 часа агента", "L": "3–8 часов агента", "XL": "больше рабочего дня"}
IMPACT = {"high": ("высокий", "▲"), "mid": ("средний", "◆"), "low": ("низкий", "▽")}
STATE = {"done": "сделано", "partial": "частично", "todo": "не начато"}

I = dict  # короткая запись инициативы

ITEMS = [
    # ------------------------------------------------------------ качество анализа
    I(id="q_dedup", dir="quality", phase="now", size="S", agent=(0.5, 1), human=(0, 0.3), impact="mid", state="todo", tickets=[3],
      title="Дубли снимков до разбиения",
      what="Убрать дубли по хешу пикселей до кросс-валидации.",
      effect="Нет утечки одного и того же снимка между обучением и проверкой — метрики не завышены."),
    I(id="q_cv", dir="quality", phase="now", size="M", agent=(1, 2), human=(0.5, 1), impact="high", state="todo", tickets=[13],
      deps=["q_dedup"], title="Честная оценка: кросс-валидация",
      what="Пять фолдов по исследованиям, F1 и ROC-AUC с 95% доверительными интервалами бутстрепом.",
      effect="Сейчас пороги подобраны на тех же 99 исследованиях, на которых меряем: F1 0.45 завышен. "
             "Без честной оценки любое «улучшение» неотличимо от подгонки.",
      risk="Реальные цифры окажутся ниже нынешних — это неприятно, но лучше узнать до защиты."),
    I(id="q_meta", dir="quality", phase="now", size="M", agent=(1, 3), human=(0.5, 1), impact="mid", state="todo", tickets=[],
      title="DICOM-метаданные: масштаб и область",
      what="PixelSpacing для углов и сантиметров, область и протокол по тегам DICOM вместо ширины кадра.",
      effect="Сейчас область определяется по ширине 300/280 px под GE Lunar — на другом аппарате сломается. "
             "Поля 3 и 2 см без масштаба не посчитать вовсе.",
      risk="Теги у обезличенных файлов организатора могут быть вычищены — тогда нужен запасной путь."),
    I(id="q_hip", dir="quality", phase="final", size="L", agent=(4, 8), human=(3, 4), impact="high", state="todo", tickets=[9, 16],
      deps=["q_cv", "q_meta"], title="Бёдра: признаки укладки и классификатор",
      what="Угол диафиза, видимость малого вертела, седалищная кость и большой вертел в кадре — признаки, сверху "
           "простой классификатор с кросс-валидацией.",
      effect="Самый большой выигрыш: 153 снимка из 252 (61%) сейчас без вердикта. У экспертов нарушений 41 из 150, "
             "36 из них — укладка. Ожидаемо F1 0.4–0.6 против нуля.",
      risk="Ротация по малому вертелу на кадре 280 px может быть плохо различима."),
    I(id="q_art", dir="quality", phase="final", size="L", agent=(3, 6), human=(2, 3), impact="high", state="partial", tickets=[8],
      deps=["q_cv"], title="Артефакты позвоночника",
      what="Сначала разобрать 17 положительных случаев глазами, затем детектор по локальному контрасту, резкости "
           "границы и форме пятна с порогом относительно яркости позвонков.",
      effect="Сейчас F1 0.13: найдено 2 из 17. Это 15 из 18 пропусков по позвоночнику — починка артефактов сама "
             "поднимет итоговый F1 позвоночника.",
      risk="Если «артефакты» у экспертов — кальцинаты и тени, а не металл, простым детектором не обойтись."),
    I(id="q_axis", dir="quality", phase="final", size="M", agent=(2, 4), human=(1, 1.5), impact="mid", state="partial", tickets=[6],
      deps=["q_cv", "q_meta"], title="Ось: наклон против сколиоза",
      what="Наклон — угол прямой через центры позвонков по устойчивой регрессии, изгиб — отклонение от неё.",
      effect="Сейчас F1 0.33 и 10 ложных тревог на 10 настоящих нарушений: сколиоз принимается за наклон."),
    I(id="q_hybrid", dir="quality", phase="final", size="M", agent=(2, 4), human=(1, 2), impact="high", state="todo", tickets=[10],
      deps=["q_cv", "q_art", "q_axis"], title="Правила → признаки → модель",
      what="Выходы правил становятся признаками, по каждому критерию — калиброванный классификатор, порог "
           "подбирает кросс-валидация.",
      effect="Пороги перестают быть ручными, появляются вероятности для ROC-AUC. Атлас и объяснения остаются."),
    I(id="q_th12", dir="quality", phase="defense", size="L", agent=(3, 6), human=(2, 3), impact="low", state="todo", tickets=[7],
      deps=["q_meta"], title="Охват до середины Th12",
      what="Найти уровень Th12 по рёбрам и телам позвонков, проверить верхнюю границу кадра.",
      effect="Требование ТЗ, сейчас не проверяется. Охват по подвздошным костям уже F1 0.77.",
      risk="Высокий: Th12 на DXA различим плохо, можно потратить дни без результата."),
    I(id="q_cnn", dir="quality", phase="defense", size="L", agent=(4, 8), human=(2, 3), impact="mid", state="todo", tickets=[],
      deps=["q_hybrid"], title="Предобученная сеть как признаки",
      what="Замороженная небольшая CNN на CPU, эмбеддинги в тот же классификатор. Веса — в образ, без интернета.",
      effect="Шанс поднять артефакты и ротацию бедра там, где правилам не хватает признаков.",
      risk="252 снимка — легко переобучиться; учить только голову, мерить кросс-валидацией."),
    I(id="q_labels", dir="quality", phase="defense", size="S", agent=(1, 2), human=(3, 6), impact="mid", state="partial", tickets=[],
      deps=["q_hybrid"], title="Разбор разногласий с экспертами",
      what="Список расхождений с разметкой по «правке вердикта» на стенде, разбор причин.",
      effect="Отделить ошибки сервиса от шума разметки — и объяснить жюри, где эксперты спорны."),
    # ------------------------------------------------------------ требования ТЗ и сдача
    I(id="t_org", dir="tz", phase="now", size="S", agent=(0.2, 0.5), human=(0.5, 1), impact="mid", state="todo", tickets=[1],
      title="Уточнить у организаторов дату и масштаб",
      what="Письмо модератору: дата промежуточной сдачи, масштаб снимков в см, трактовка критериев бедра.",
      effect="Контакты уже в админке. Ответ снимает риск промахнуться с форматом и сантиметрами."),
    I(id="t_batch", dir="tz", phase="now", size="S", agent=(0.5, 1), human=(0.5, 1), impact="high", state="partial", tickets=[14, 11],
      title="Пакетная обработка для организатора",
      what="Образ и одна команда: папка с DICOM на входе, таблица результатов по разделу 2.5 ТЗ на выходе.",
      effect="Стенд это уже умеет через веб и API; нужна сдаточная форма без браузера и сверка формата таблицы."),
    I(id="t_readme", dir="tz", phase="now", size="S", agent=(0.5, 1), human=(0.5, 1), impact="high", state="partial", tickets=[15],
      deps=["t_batch"], title="README: запуск, форматы, ограничения",
      what="Как запустить, что на входе и выходе, известные ограничения и план доработки.",
      effect="Первое, что откроет проверяющий."),
    I(id="t_offline", dir="tz", phase="final", size="M", agent=(1, 3), human=(1, 1), impact="high", state="partial", tickets=[],
      deps=["t_batch"], title="Офлайн-поставка в контур",
      what="Образ со всеми моделями без обращения в интернет, инструкция установки, проверка на чистой машине.",
      effect="ТЗ требует работу локально, снимки не покидают контур. Стенд это соблюдает, но поставку никто не проверял."),
    I(id="t_sr", dir="tz", phase="final", size="M", agent=(2, 4), human=(1, 1), impact="mid", state="todo", tickets=[18],
      title="Заключение в DICOM SR",
      what="Структурированный отчёт DICOM с областью, вердиктом и нарушениями по каждому снимку.",
      effect="Результат открывается в PACS рядом со снимком — шаг к реальному внедрению."),
    I(id="t_docs", dir="tz", phase="final", size="M", agent=(2, 3), human=(2, 3), impact="high", state="partial", tickets=[22],
      deps=["t_readme", "q_cv"], title="Полный комплект документации",
      what="Руководство пользователя, развёртывание, описание метода и честные метрики.",
      effect="Требование сдачи. Метрики в документе — после кросс-валидации, иначе придётся переписывать."),
    # ------------------------------------------------------------ презентация и защита
    I(id="p_demo", dir="defense", phase="defense", size="M", agent=(1, 3), human=(2, 4), impact="high", state="todo", tickets=[24],
      deps=["q_hip", "q_art"], title="Демо-сценарий и кейсы",
      what="Сколиоз, эндопротез, перелом, посторонний металл — готовые прогоны и путь по стенду за 3 минуты.",
      effect="Жюри запоминает демонстрацию, а не слайды."),
    I(id="p_deck", dir="defense", phase="defense", size="M", agent=(2, 3), human=(4, 6), impact="high", state="todo", tickets=[23],
      deps=["q_cv", "p_demo"], title="Презентация по разделу 4 ТЗ",
      what="Слайды по требованиям раздела 4 с честными метриками и планом развития — этот роудмап как основа.",
      effect="Время человека здесь главное: репетиции нельзя делегировать."),
    I(id="p_film", dir="defense", phase="defense", size="M", agent=(2, 4), human=(2, 3), impact="mid", state="partial", tickets=[35],
      deps=["p_demo"], title="Ролик про сервис",
      what="Короткий ролик по демо-сценарию.",
      effect="Показывает сервис без живого стенда.",
      risk="В кадры не должны попасть снимки организатора."),
    I(id="p_showcase", dir="defense", phase="later", size="S", agent=(0.5, 1), human=(0.5, 1), impact="low", state="todo", tickets=[36],
      title="Витрина исходных материалов", what="Страница с материалами задачи и описаниями.",
      effect="Удобство, на оценку влияет слабо."),
    # ------------------------------------------------------------ работа врача
    I(id="d_queue", dir="doctor", phase="final", size="M", agent=(2, 3), human=(1, 1), impact="mid", state="todo", tickets=[20],
      deps=["q_hybrid"], title="Очередь спорных исследований",
      what="Снимки с неуверенным вердиктом — в очередь на просмотр врачом внутри контура.",
      effect="Честный ответ на вопрос «а если модель ошибается»: сомнительное смотрит человек."),
    I(id="d_fix", dir="doctor", phase="defense", size="L", agent=(4, 6), human=(2, 2), impact="mid", state="todo", tickets=[21],
      deps=["d_queue"], title="Правка разметки с подтверждением врача",
      what="Врач двигает ориентиры на атласе, сервис пересчитывает вердикт, правка идёт в журнал.",
      effect="Замыкает цикл: ошибки становятся новой разметкой."),
    I(id="d_role", dir="doctor", phase="defense", size="L", agent=(3, 6), human=(2, 3), impact="mid", state="todo",
      tickets=[72, 73, 74], title="Роль «врач» и консультации",
      what="Заявка врача, подтверждение админом, запрос консультации из карточки, уведомления.",
      effect="Сценарий телемедицины из ТЗ. Решения по эпику ещё за командой."),
    I(id="d_call", dir="doctor", phase="later", size="XL", agent=(8, 14), human=(4, 6), impact="low", state="todo",
      tickets=[75, 76], deps=["d_role"], title="Звонок в портале",
      what="WebRTC-комната со снимком, TURN и STUN внутри контура.",
      effect="Эффектно, но далеко от сути задачи.", risk="Высокий: сети медорганизаций режут WebRTC."),
    I(id="d_monitor", dir="doctor", phase="defense", size="M", agent=(1, 3), human=(0.5, 1), impact="low", state="partial",
      tickets=[77, 78], title="Мониторинг для админов", what="Нагрузка, очередь, ошибки, использование.",
      effect="Частично уже есть: журнал, статистика MCP."),
    # ------------------------------------------------------------ эксплуатация
    I(id="o_autostart", dir="ops", phase="now", size="S", agent=(0.3, 0.5), human=(0.1, 0.2), impact="mid", state="todo", tickets=[],
      title="Автозапуск брокера вопросов",
      what="systemd-юнит вместо окна tmux.",
      effect="Сейчас после перезагрузки «Спросить Claude» молчит, пока брокер не запустят руками."),
    I(id="o_backup", dir="ops", phase="now", size="S", agent=(0.5, 1), human=(0.2, 0.5), impact="mid", state="todo", tickets=[],
      title="Резервные копии прогонов и учёток",
      what="Ночная копия тома стенда и базы учёток вне контейнера.",
      effect="Диск машины заполнен на 98%: сбой или случайное удаление сейчас необратимы."),
    I(id="o_mobile", dir="ops", phase="now", size="S", agent=(0.3, 0.5), human=(0.1, 0.2), impact="low", state="todo", tickets=[43],
      title="Страница прогона на телефоне",
      what="Тот же приём, что вылечил админку: min-width:0 у карточек в grid.",
      effect="Причина уже найдена, осталось применить."),
    I(id="o_whisper", dir="ops", phase="final", size="S", agent=(0.5, 1), human=(0.5, 1), impact="low", state="partial", tickets=[84],
      title="Голос: Whisper больше small",
      what="Medium по кнопке с проверкой свободной памяти.",
      effect="Точнее распознаёт медицинские термины. Нужно решение по памяти машины."),
    # ------------------------------------------------------------ интеграции
    I(id="i_group", dir="integr", phase="now", size="S", agent=(0.2, 0.5), human=(0.3, 0.5), impact="low", state="partial",
      tickets=[104], title="Бот в группе: проверка вживую",
      what="Команды, разворачивание ссылок и тикетов в командной группе.",
      effect="Бот подключён и поздоровался; осталось проверить команды."),
    I(id="i_pacs", dir="integr", phase="later", size="L", agent=(4, 8), human=(2, 3), impact="mid", state="todo", tickets=[],
      deps=["t_sr", "t_offline"], title="PACS по DICOMweb",
      what="Забирать исследования из Orthanc по DICOMweb и возвращать заключение DICOM SR.",
      effect="Показывает путь в реальную клинику без ручной выгрузки файлов."),
]

# рекомендуемый путь: сначала мерить честно, затем самые большие дыры в точности, затем сдача и защита
PATH = ["q_dedup", "q_cv", "t_batch", "t_readme", "q_meta", "q_hip", "q_art", "q_axis", "q_hybrid", "t_offline",
        "t_docs", "p_demo", "p_deck"]


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}".replace(".", ",")


def _fmt_hours(lo: float, hi: float) -> str:
    if hi <= 0:
        return "—"
    if hi < 1:
        return f"{round(lo * 60)}–{round(hi * 60)} мин" if lo != hi else f"{round(hi * 60)} мин"
    return f"{_num(lo)}–{_num(hi)} ч" if lo != hi else f"{_num(hi)} ч"


def build(ticket_status: dict[int, bool] | None = None, now: float | None = None) -> dict:
    """Инициативы с живыми статусами тикетов, итоги по этапам и рекомендуемому пути."""
    ticket_status = ticket_status or {}
    now = now or time.time()
    by_id = {it["id"]: it for it in ITEMS}
    items = []
    for it in ITEMS:
        tickets = [dict(id=t, closed=ticket_status.get(t)) for t in it["tickets"]]
        items.append(dict(it, deps=it.get("deps", []), risk=it.get("risk", ""), tickets=tickets,
                          agent_text=_fmt_hours(*it["agent"]), human_text=_fmt_hours(*it["human"]),
                          step=PATH.index(it["id"]) + 1 if it["id"] in PATH else None,
                          blocks=[o["id"] for o in ITEMS if it["id"] in o.get("deps", [])]))
    phases, prev = [], now
    for ph in PHASES:
        mine = [i for i in items if i["phase"] == ph["id"] and i["state"] != "done"]
        days = None
        if ph["deadline"]:                     # длина самого этапа: от конца предыдущего (или сегодня) до его срока
            end = time.mktime(time.strptime(ph["deadline"], "%Y-%m-%d")) + 86400
            days = max(1, round((end - max(prev, now)) / 86400))
            prev = end
        human_hi = sum(i["human"][1] for i in mine)
        per_day = round(human_hi / days, 1) if days else None     # сколько часов в день нужно от человека
        phases.append(dict(ph, count=len(mine), days=days, human_per_day=per_day,
                           agent_text=_fmt_hours(sum(i["agent"][0] for i in mine), sum(i["agent"][1] for i in mine)),
                           human_text=_fmt_hours(sum(i["human"][0] for i in mine), sum(i["human"][1] for i in mine))))
    path = [by_id[p] for p in PATH]
    totals = dict(
        items=len(items), path=len(PATH),
        path_agent=_fmt_hours(sum(p["agent"][0] for p in path), sum(p["agent"][1] for p in path)),
        path_human=_fmt_hours(sum(p["human"][0] for p in path), sum(p["human"][1] for p in path)),
        high=sum(1 for i in items if i["impact"] == "high"))
    return dict(directions=DIRECTIONS, phases=phases, items=items, path=PATH, totals=totals,
                sizes=SIZES, impact={k: dict(label=v[0], icon=v[1]) for k, v in IMPACT.items()}, states=STATE)
