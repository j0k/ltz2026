# -*- coding: utf-8 -*-
"""Текст команд командной строки: --help, --version, --author, --mcp (29.09, Юрий)."""
from __future__ import annotations

import os
import platform
import sys

from dxaqc.desktop import APP_NAME, AUTHORS, CONTACTS, CONTEXT, LICENSE, SITE, TEAM
from dxaqc.desktop import APP_VERSION_FULL as APP_VERSION        # человеку — с меткой сборки: 1.0-Beta-20260930-0015


def prog() -> str:
    return os.environ.get("KOSTIK_PROG") or ("Kostik.exe" if sys.platform.startswith("win") else "kostik")


def help_text() -> str:
    p = prog()
    return f"""{APP_NAME} {APP_VERSION} — контроль качества снимков денситометрии DXA
{CONTEXT}

Использование:
  {p}                          открыть окно программы
  {p} файл.dcm папка\\ архив.zip  открыть окно и сразу проверить файлы, папки, zip-архивы
  {p} --check папка\\            проверить и напечатать описание по каждому снимку в консоль — без окна
  {p} [параметр]

Параметры:
  --help, -h       показать эту справку и выйти
  --version, -V    версия программы, анализа, Python и пути установки
  --author         авторы, команда, контакты и сайт
  --mcp            как подключить ИИ-ассистента (Claude Desktop, Cursor, VS Code): готовая настройка и список инструментов
  --verbose        подробный журнал запуска: система, папки, каждая библиотека, окно и WebView2, порт, анализ,
                   старт движка. Пишется в консоль и в файл dxaqc-verbose.log в папке данных
  --selftest       проверка установки: библиотеки, анализ фантома, сервер, MCP; код возврата 0 — всё в порядке
                   (вместе с --verbose — с подробным журналом)
  --check ПУТЬ…    проверить файлы, папки, zip-архивы и напечатать по каждому снимку область, вердикт, нарушение,
                   пояснение, измерения и путь к картинке разметки. Окно открыто — проверку ведёт оно и показывает
                   её в истории; окна нет — движок поднимается на время команды. Код возврата: 0 — нарушений нет,
                   1 — есть снимки с нарушением, 2 — нет таких файлов, 3 — проверка не удалась
  --results [N]    описание уже сделанной проверки; без номера — последней
  --runs           последние проверки: номер, время, итог
  --json           вместе с --check, --results, --runs: ответ в JSON — для сценариев и ИИ-агентов
  --out ПАПКА      вместе с --check, --results: сложить в папку results.xlsx, results.csv и картинки разметки
  --open           вместе с --check: показать проверку в открытом окне программы
  --timeout СЕК    вместе с --check: сколько ждать результата (по умолчанию 600)
  --browser        открыть в браузере (Edge, Chrome), а не во встроенном окне
  --no-window      только сервер, без окна (для отладки); адрес печатается в консоль
  --port N         порт локального сервера (по умолчанию 8765; занят — берётся свободный)
  --host АДРЕС     адрес, на котором слушает сервер: 127.0.0.1 (по умолчанию) — только этот компьютер,
                   0.0.0.0 — все сетевые интерфейсы, или адрес одного интерфейса. Входа по паролю в программе нет:
                   другой адрес открывает снимки и результаты всем, кто до него достанет
  --show-all-hosts показать все адреса для --host с названиями сетевых интерфейсов и выйти
  --mcp-stdio      MCP-сервер по stdio для ИИ-ассистентов (его запускает сам ассистент)

Примеры:
  {p} --verbose                подробный журнал, если программа не запускается
  {p} --selftest --verbose     проверка установки с подробным журналом
  {p} --mcp                    настройка для Claude Desktop
  {p} --check D:\\снимки --json  проверка из сценария или ИИ-агента: ответ в JSON, окно не нужно
  {p} --results --out D:\\отчёт  таблицы и разметка последней проверки — в папку
  {p} --show-all-hosts         на каких адресах может слушать сервер
  {p} --host 0.0.0.0 --no-window   только сервер, доступен с других компьютеров сети

Данные и журналы: {_data()}
Сайт: {SITE} · автор: {AUTHORS[0]['name']} — {AUTHORS[0].get('url', SITE)}
"""


def _data() -> str:
    from dxaqc.desktop import paths
    return paths.data_dir()


def install_dir() -> str:
    """Каталог установки: в пакетах код лежит в <установка>/app/dxaqc, в исходниках — в корне репозитория."""
    from dxaqc.desktop import paths
    root = os.path.abspath(os.path.join(paths.HERE, "..", ".."))
    return os.path.dirname(root) if os.path.basename(root) == "app" else root


def version_text() -> str:
    from dxaqc import __version__
    from dxaqc.desktop import paths
    root = install_dir()
    return (f"{APP_NAME} {APP_VERSION} (анализ {__version__})\n"
            f"Python {platform.python_version()} · {platform.system()} {platform.release()} · {platform.machine()}\n"
            f"Каталог установки: {root}\nДанные пользователя: {paths.data_dir()}\n")


def author_text() -> str:
    lines = [f"{APP_NAME} {APP_VERSION} — {TEAM}", CONTEXT, ""]
    lines += ["Авторы:"] + [f"  {a['name']} — {a['role']}" + (f"\n    {a['url']}" if a.get("url") else "") for a in AUTHORS]
    lines += ["", "Контакты:"] + [f"  {c['kind']}: {c['value']}  {c['url']}" for c in CONTACTS]
    lines += ["", f"Страница проекта: {AUTHORS[0].get('url', SITE)}", "Исходный код: https://github.com/j0k/ltz2026", "Хакатон ЛЦТ 2026: https://i.moscow/lct", "", LICENSE, ""]
    return "\n".join(lines)


def mcp_text() -> str:
    import json
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-len("pythonw.exe")] + "python.exe"
    cfg = {"mcpServers": {"dxa-qc": {"command": exe, "args": ["-m", "dxaqc.desktop", "--mcp-stdio"]}}}
    from dxaqc.desktop import hosts
    base = hosts.url(int(os.environ.get("DXAQC_PORT") or 8765))
    try:
        from dxaqc.web import desktop, mcp
        desktop.patch_mcp(mcp)                       # в приложении набор инструментов свой: анализ по путям, без наборов организатора
        tools = [f"  {t['name']} — {t['title']}" for t in mcp.TOOLS]
    except Exception:  # noqa: BLE001
        tools = ["  (список инструментов появится после запуска программы)"]
    return f"""{APP_NAME} — локальный MCP-сервер для ИИ-ассистентов

1. Claude Desktop (через stdio, токен не нужен, работает и при закрытом окне Kostik).
   Настройки → Developer → Edit Config, вставьте в claude_desktop_config.json и перезапустите Claude:

{json.dumps(cfg, ensure_ascii=False, indent=2)}

2. Cursor, VS Code и другие клиенты с поддержкой MCP по HTTP: адрес {base}/mcp,
   токен — в программе на странице «ИИ-ассистент» (нужно запущенное окно Kostik).

3. Проверка без ассистента: «{prog()} --selftest» — в отчёте строка «MCP-сервер».

Инструменты (в приложении):
{chr(10).join(tools)}

Снимки пациентов и организатора не передавайте ассистентам без разрешения: сам ассистент может отправлять
ответы приложения своей модели в интернет.
"""
