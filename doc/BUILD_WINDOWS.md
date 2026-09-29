# Сборка Kostik под Windows: `.exe` и `.msi`

Установщики для Windows собираются **на Linux** — Windows для сборки не нужна, она нужна только для подписи
и проверки. Скрипт [`packaging/build_windows.sh`](../packaging/build_windows.sh) собирает папку приложения
и упаковывает её в два установщика:

| файл | что это | куда ставит |
|---|---|---|
| `Kostik-1.0-beta-setup.exe` | установщик NSIS, интерфейс на русском | `C:\Program Files\Kostik-1.0`, нужны права администратора |
| `Kostik-1.0-beta.msi` | пакет Windows Installer (wixl) | та же папка; тихо: `msiexec /i … /qn` |

Внутри обоих — одна и та же папка: свой Python 3.12, библиотеки под `win_amd64`, код `dxaqc` и два запускателя.
На машине пользователя ничего доустанавливать не нужно, кроме WebView2 — он есть во всех современных Windows.

Пакет для Linux собирает [`packaging/build_deb.sh`](../packaging/build_deb.sh) на той же машине и теми же средствами.

## Версия

Версия для человека — `Kostik 1.0-Beta-<дата-время сборки>`, например `Kostik 1.0-Beta-20260930-0015`.
Метку (`ГГГГММДД-ЧЧММ`, московское время) ставит сборка: пишет `dxaqc/desktop/_build.py` в папку приложения,
в коде это `dxaqc.desktop.APP_VERSION_FULL`. Её показывают `--version`, самопроверка, страница «О программе»,
свойства `.exe` и установщики. Задать метку вручную: `BUILD_STAMP=20260930-0015 packaging/build_windows.sh`.

`APP_VERSION` остаётся `1.0-Beta`: по ней сравниваются обновления и называются файлы установщиков.
При запуске из исходников метки нет — версия показывается как `1.0-Beta`.

## Что нужно на сборочной машине

- Linux: проверено на Ubuntu 24.04, на ней же собирает CI;
- Python **3.12** — ровно эта версия: она же кладётся в приложение, и ею заранее компилируется байт-код,
  а `.pyc` разных версий Python несовместимы;
- пакеты `nsis` (makensis), `msitools` и `wixl` — в Ubuntu 24.04 это два разных пакета, — `rsync`, `curl`, `unzip`;
- для запускателей — `gcc-mingw-w64-x86-64` или Docker: без компилятора образ `kostik-mingw` соберётся сам;
- интернет — только на время сборки: качаются embed-Python с python.org и колёса с PyPI.

```bash
sudo apt-get update && sudo apt-get install -y nsis msitools wixl gcc-mingw-w64-x86-64 rsync curl unzip python3.12-venv
python3.12 -m venv .venv && .venv/bin/pip install -U pip     # скрипт берёт pip именно отсюда
packaging/build_windows.sh                                    # сборка → ../build-desktop, результат → ../dist-desktop/<версия>
```

Пути можно задать аргументами: `packaging/build_windows.sh <папка сборки> <папка результатов>`.

### Если под рукой только Windows

Linux берётся контейнером — результат тот же. Нужен запущенный Docker Desktop.

```bash
docker build -t kostik-winbuild - <<'EOF'
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq \
    python3.12 python3.12-venv python3-pip nsis msitools wixl gcc-mingw-w64-x86-64 rsync curl unzip ca-certificates \
 && rm -rf /var/lib/apt/lists/*
EOF
```

Репозиторий, склонированный на Windows с `core.autocrlf=true`, лежит на диске с окончаниями строк CRLF. Linux
на таком скрипте отвечает `/usr/bin/env: 'bash\r': No such file or directory`, поэтому собираем из копии
с окончаниями LF внутри контейнера:

```bash
git ls-files --eol | grep "w/crlf" | cut -f2 > ../crlf.txt        # какие файлы git отдал с CRLF
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/repo" -v "$PWD/..:/host" -v kostik-build:/build kostik-winbuild bash -c '
  set -e
  [ -d /repo/.venv ] || python3.12 -m venv /repo/.venv
  rsync -a --delete --exclude .git --exclude .venv /repo/ /tmp/repo/ && ln -sfn /repo/.venv /tmp/repo/.venv && cd /tmp/repo
  tr -d "\r" < /host/crlf.txt | while IFS= read -r f; do [ -f "$f" ] && sed -i "s/\r$//" "$f"; done
  chmod +x packaging/*.sh packaging/windows/launcher/build.sh
  packaging/build_windows.sh /build /host/dist-desktop'
```

- `MSYS_NO_PATHCONV=1` нужен в Git Bash: без него пути вида `/repo` превращаются в пути Windows.
- Папку сборки держим в томе Docker (`kostik-build`), а не на смонтированном диске Windows: там распаковка тысяч
  мелких файлов идёт в разы медленнее. Том хранит и скачанные колёса — повторная сборка занимает пару минут.
- Другой путь — склонировать репозиторий с `git config core.autocrlf input`: тогда копия не нужна.

WSL подойдёт, если в нём есть Python 3.12 и права ставить пакеты; в свежих Ubuntu Python 3.12 уже нет.

## Что происходит по шагам

Версии берутся из `dxaqc/desktop/__init__.py`: `APP_VERSION` (`1.0-Beta`), `WIN_VERSION`
(`1.0.0`, только цифры — требование MSI и свойств файла), `DEB_VERSION` (для `.deb`).

**1. Библиотеки под Windows.** Скачивается `python-3.12.10-embed-amd64.zip` и колёса:
`pip download --platform win_amd64 --python-version 3.12 --only-binary=:all:` по
`packaging/requirements-desktop.txt`. Отдельно — `cffi` и `pycparser`, отдельно — пакеты на чистом Python:
`pywebview`, `pythonnet`, `clr_loader`, `proxy_tools`, `bottle`. Папка `pure-win` каждый раз очищается:
старые версии `pythonnet` ломают подбор зависимостей.

**2. Папка приложения** `stage-win/Kostik`:

```
Kostik/
  Kostik.exe          оконный запускатель: ярлыки, «Открыть с помощью»
  Kostik-cli.exe      консольный запускатель: командная строка, сценарии, сервер MCP
  python/             embed-Python 3.12 + Lib/site-packages с колёсами
  app/dxaqc/          код сервиса и desktop/_build.py с меткой сборки
  icon.ico            значок программы
  dcm.ico             значок файлов .dcm: лист со значком Kostik
  LICENSE.txt         лицензионное соглашение — оно же на странице установщика
  selftest.cmd  verbose.cmd  dxaqc-mcp.cmd
```

`python312._pth` переписывается так, чтобы Python видел `..\app` и `Lib\site-packages`. Из `site-packages`
убираются `__pycache__`, `tests`, `testing`, `bin` и `.agents` — программе они не нужны.

**3. Байт-код заранее.** `compileall --invalidation-mode unchecked-hash` по `app` и `python/Lib`.
Без этого каждый запуск из `C:\Program Files` холодный: обычный пользователь не может писать `.pyc`
рядом с исходниками.

**4. Запускатели** — пара, как `pythonw.exe` и `python.exe`, из одного исходника
[`packaging/windows/launcher/kostik_launcher.c`](../packaging/windows/launcher/kostik_launcher.c):

| файл | подсистема | что делает |
|---|---|---|
| `Kostik.exe` | оконная | без параметров — окно программы, чёрного окна нет. С параметрами из консоли — печатает в неё же |
| `Kostik-cli.exe` | консольная | вывод в консоль и код возврата — как у обычной команды. Без параметров открывает окно и отпускает консоль |

Ограничение Windows, а не программы: `cmd.exe` и PowerShell **не ждут** оконные программы. После
`Kostik.exe --help` приглашение появляется раньше текста справки, а код возврата не выставляется.
Нужны порядок вывода и код возврата — берите `Kostik-cli.exe`.

**5. Установщики.**

- [`packaging/windows/installer.nsi`](../packaging/windows/installer.nsi) → `Kostik-<версия>-setup.exe`: ставит
  в `$PROGRAMFILES64\Kostik-<1.0>`, создаёт ярлыки в Пуске и на рабочем столе, запись в «Установка и удаление
  программ» и деинсталлятор. Прежнюю версию убирает сам.
- Галочка «Открывать файлы .dcm в Kostik» по умолчанию снята. Она делает тип `.dcm` нашим: файлы получают значок
  `dcm.ico` и открываются в Kostik двойным щелчком. Прежний тип запоминается и возвращается при удалении.
  Если человек сам выбрал программу для `.dcm` через «Открыть с помощью», Windows оставит её и её значок —
  установщикам менять этот выбор запрещено.
- Тихая установка: `Kostik-1.0-beta-setup.exe /S`, с привязкой файлов — `/S /DCM`.
- [`packaging/windows/make_wxs.py`](../packaging/windows/make_wxs.py) строит описание пакета, `wixl -a x64` собирает
  `.msi`. `UpgradeCode` постоянный. В `.msi` выбора компонентов нет, поэтому привязки `.dcm` там нет.

**В `.msi` все строки — только латиницей**: производитель, описание, имена ярлыков. `wixl` пишет таблицу строк
без кодовой страницы; с одной русской строкой Windows Installer читает имена папок со сдвигом, и установка
кончается ошибкой 1324 «путь содержит недопустимый символ» и кодом 1603 — каждый раз на новой папке.
`make_wxs.py` останавливает сборку, если в описании пакета есть не латиница или имя, негодное для `.msi`.

**Значки** рисует [`packaging/make_icon.py`](../packaging/make_icon.py), нужен Pillow: `icon.png`, `icon.ico`
и `dcm.ico` в `dxaqc/desktop/assets`. Запускать после изменения рисунка; готовые файлы лежат в репозитории.

**Лицензионное соглашение** — [`packaging/windows/license.txt`](../packaging/windows/license.txt); сборка
подставляет версию вместо `{VERSION}`.

## Подпись

Подписываются четыре файла: оба запускателя и оба установщика. Подпись ставится на Windows, средством `signtool`
из Windows SDK. Закрытый ключ остаётся в хранилище сертификатов Windows и никуда не копируется: `signtool` находит
его по отпечатку сертификата. **Ключ и файлы `.pfx` в репозиторий не кладутся.**

Запускатели лежат внутри установщиков, поэтому сборка идёт в три приёма:

```bash
# 1. Linux: только запускатели
packaging/windows/launcher/build.sh <папка> dxaqc/desktop/assets/icon.ico 1.0.0 "1.0-Beta-$BUILD_STAMP"
```

```powershell
# 2. Windows: подпись запускателей
signtool sign /sha1 <отпечаток сертификата> /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /d "Kostik" /du "https://ltz2026.ru" Kostik.exe Kostik-cli.exe
```

```bash
# 3. Linux: установщики с готовыми запускателями; метка сборки та же, что на шаге 1
BUILD_STAMP=<та же метка> KOSTIK_LAUNCHERS=<папка> packaging/build_windows.sh
```

```powershell
# 4. Windows: подпись установщиков и проверка
signtool sign /sha1 <отпечаток сертификата> /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /d "Kostik" /du "https://ltz2026.ru" Kostik-1.0-beta-setup.exe Kostik-1.0-beta.msi
Get-AuthenticodeSignature Kostik-1.0-beta-setup.exe, Kostik-1.0-beta.msi | Format-List Status, SignerCertificate, TimeStamperCertificate
```

- `/tr` с отметкой времени обязателен: без неё подпись перестанет считаться действительной, когда кончится срок
  сертификата.
- Сертификат, выпущенный самим автором, Windows доверяет только там, где его добавили в доверенные. На остальных
  машинах подпись есть, но издатель показывается как неизвестный, и SmartScreen предупреждает. Убирает
  предупреждение только сертификат от удостоверяющего центра.
- Деинсталлятор создаётся уже при установке, поэтому он не подписан.

## Проверка результата

Пакет `.msi` можно проверить, не трогая систему, — распаковать в папку:

```powershell
msiexec /a Kostik-1.0-beta.msi TARGETDIR=C:\tmp\kostik /qn     # код 0 и файлы в папке — пакет исправен
```

После установки:

```powershell
& "C:\Program Files\Kostik-1.0\Kostik-cli.exe" --selftest       # код 0 — всё в порядке
& "C:\Program Files\Kostik-1.0\Kostik-cli.exe" --version        # версия с меткой сборки
```

Полная проверка идёт в CI: [`.github/workflows/desktop.yml`](../.github/workflows/desktop.yml) собирает на
`ubuntu-24.04` и прогоняет на `windows-latest` тихую установку обоих установщиков, самопроверку, справку,
`--show-all-hosts`, запуск окна со скриншотом, запросы к страницам, MCP по stdio и удаление.
Запуск: вручную или по тегу `v*`.

## Командная строка

```
Kostik-cli.exe --help                                    все параметры
Kostik-cli.exe --version                                 Kostik 1.0-Beta-20260930-0015 (анализ 0.5.4)
Kostik-cli.exe --selftest                                проверка установки
Kostik-cli.exe --check D:\снимки\исследование            описание по каждому снимку — в консоль
Kostik-cli.exe --check D:\снимки --json --out D:\отчёт   ответ в JSON, таблицы и разметка — в папку
Kostik-cli.exe --results                                 описание последней проверки
Kostik-cli.exe --runs                                    список проверок
Kostik-cli.exe --show-all-hosts                          все адреса для --host
Kostik.exe --host 0.0.0.0                                окно программы, сервер слушает на всех интерфейсах
```

`--check` — тонкий клиент движка. Окно открыто — проверку ведёт его движок, она видна в истории. Окна нет —
движок поднимается на время команды. Код возврата: 0 — нарушений нет, 1 — есть снимки с нарушением,
2 — нет таких файлов, 3 — проверка не удалась.

`--host` — адрес, на котором слушает сервер программы. По умолчанию `127.0.0.1`: программа видна только с этого
компьютера. `0.0.0.0` — все интерфейсы, адрес интерфейса — только он, `::1` и `::` — то же для IPv6. Адрес, которого
на компьютере нет, — ошибка с кодом 2. То же задаёт переменная окружения `DXAQC_HOST`.

**Осторожно с сетью.** В настольном режиме нет входа по паролю. С любым адресом, кроме `127.0.0.1` и `::1`, снимки
и результаты видны всем, кто достанет до этого адреса; программа при запуске об этом предупреждает.

## Частые ошибки

| что видно | причина |
|---|---|
| `bash\r: No such file or directory` | окончания строк CRLF — собирайте из копии с LF, см. выше |
| `wixl: command not found` | поставлен только `msitools`; `.exe` при этом уже собран, `.msi` нет |
| `.msi` не ставится, код 1603, в журнале ошибка 1324 | в пакет попала русская строка; журнал: `msiexec /i … /l*v install.log` |
| `.msi` поставился второй записью в «Программах» | версия пакета та же — сначала удалите прежнюю: `msiexec /x {код продукта}` |
| программа каждый раз запускается медленно | сборка шла не на Python 3.12 — байт-код не подошёл |
| сборка падает на `pip download` | нет интернета или нет `.venv` в корне репозитория |
