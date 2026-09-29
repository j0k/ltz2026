# -*- coding: utf-8 -*-
"""Настольное приложение Kostik: тот же сервис, что на стенде, локально и без сети (эпики D1–D7, #138–#170).

Окно — pywebview (WebView2 в Windows, WebKitGTK в Linux) или браузер в режиме приложения; внутри — сервер FastAPI
на 127.0.0.1. Режим DXAQC_MODE=desktop убирает аккаунты, админку, Telegram-бота, вопросы Claude и cookie.
"""
from __future__ import annotations

APP_NAME = "Kostik"
APP_VERSION = "1.0-Beta"          # версия приложения; версия анализа — dxaqc.__version__
WIN_VERSION = "1.0.0"             # Windows (MSI, свойства .exe): только цифры
DEB_VERSION = "1.0~beta"          # Debian: «~» — раньше будущей 1.0
APP_ID = "dxaqc"
DEFAULT_PORT = 8765
SITE = "https://ltz2026.ru"
AUTHORS = [
    dict(name="Юрий Коноплёв", role="руководитель проекта, продукт", url="https://juri-konoplev.pro/ltz2026/"),
    dict(name="Алексей Чуркин", role="стенд, Telegram-бот, проверка сервиса, обратная связь"),
]
TEAM = "команда «Квантовый Скачок»"
CONTEXT = "ЛЦТ 2026 · задача 04 Департамента здравоохранения Москвы: контроль качества денситометрии DXA"
CONTACTS = [
    dict(kind="Сайт", value="ltz2026.ru", url=SITE),
    dict(kind="Telegram · Юрий Коноплёв", value="@bimodaling", url="https://t.me/bimodaling"),
    dict(kind="Telegram · Алексей Чуркин", value="@lesha_cfc", url="https://t.me/lesha_cfc"),
]
LICENSE = "© 2026 авторы Kostik. Все права защищены. Сервис для контроля качества снимков, не для постановки диагноза."
