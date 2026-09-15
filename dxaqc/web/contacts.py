# -*- coding: utf-8 -*-
"""Контакты организаторов задачи 04: поддержка ЛЦТ, модератор задачи и эксперты ДепЗдрава.

Со страницы задачи на leaders.mos.ru. Показываются только в админке: это персональные данные живых людей,
поэтому в публичную часть стенда и в трекер они не попадают.
"""
from __future__ import annotations

ORG = "ГБУЗ «НПКЦ ДиТ ДЗМ»"

SUPPORT = dict(
    title="Поддержка ЛЦТ",
    tg="@help_lct", tg_url="https://t.me/help_lct",
    email="info.leaders@develop.mos.ru",
    note="Помогут найти чат по выбранной задаче и ответят на вопросы по участию и решению.",
)
MODERATOR = dict(
    title="Модератор задачи",
    name="Зеленский Антон", tg="@treker_antonzel", tg_url="https://t.me/treker_antonzel",
)
EXPERTS = [
    dict(name="Омелянская Ольга", role="Заместитель директора по перспективному развитию", org=ORG),
    dict(name="Ананьев Дмитрий", role="Начальник управления по развитию информационных систем инноваций в здравоохранении", org=ORG),
    dict(name="Борисов Александр", role="Младший научный сотрудник", org=ORG),
]
ALL = dict(support=SUPPORT, moderator=MODERATOR, experts=EXPERTS)
