/* Запускатель Kostik для Windows (29.09, Юрий: Kostik.exe --help / --version / --author / --mcp / --verbose).
 *
 * Две сборки из одного файла:
 *   Kostik.exe      — оконная (-DGUI_BUILD): ярлыки и «Открыть с помощью», консоль не показывает; запущена из консоли
 *                     с параметром — подключается к ней и печатает туда (30.09, Юрий: Kostik.exe — оконный);
 *   Kostik-cli.exe  — консольная: cmd и PowerShell ждут её завершения, вывод и код выхода — как у любой команды.
 *
 * Команды с выводом (--help, --version, --author, --mcp, --verbose, --selftest, --mcp-stdio, --no-window)
 * идут в python\python.exe, обычный запуск — в python\pythonw.exe без ожидания.
 */
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdlib.h>

static wchar_t g_base[MAX_PATH * 2];

static void say(const wchar_t *text, int is_error)
{
#ifdef GUI_BUILD
    MessageBoxW(NULL, text, L"Kostik", MB_OK | (is_error ? MB_ICONERROR : MB_ICONINFORMATION));
#else
    HANDLE h = GetStdHandle(is_error ? STD_ERROR_HANDLE : STD_OUTPUT_HANDLE);
    DWORD n, mode;
    if (h && h != INVALID_HANDLE_VALUE && GetConsoleMode(h, &mode))
        WriteConsoleW(h, text, (DWORD)wcslen(text), &n, NULL);
    else
        MessageBoxW(NULL, text, L"Kostik", MB_OK | MB_ICONERROR);
#endif
}

static const wchar_t *rest_of_command_line(void)
{
    const wchar_t *c = GetCommandLineW();
    if (*c == L'"') {
        c++;
        while (*c && *c != L'"') c++;
        if (*c) c++;
    } else {
        while (*c && *c != L' ' && *c != L'\t') c++;
    }
    while (*c == L' ' || *c == L'\t') c++;
    return c;
}

/* любой параметр (--help, --version, --author, --mcp, --verbose, --selftest, --port …, даже неизвестный) — это команда:
 * её вывод должен попасть в консоль; имена файлов с «-» не начинаются */
static int is_console_flag(const wchar_t *a)
{
    return a[0] == L'-' || (a[0] == L'/' && a[1] == L'?' && a[2] == 0);
}

static int valid_handle(HANDLE h) { return h && h != INVALID_HANDLE_VALUE; }

static int run_child(const wchar_t *exe_rel, const wchar_t *rest, int wait, HANDLE hin, HANDLE hout, HANDLE herr)
{
    wchar_t exe[MAX_PATH * 2];
    swprintf(exe, MAX_PATH * 2, L"%ls\\%ls", g_base, exe_rel);
    if (GetFileAttributesW(exe) == INVALID_FILE_ATTRIBUTES) {
        wchar_t msg[MAX_PATH * 3];
        swprintf(msg, MAX_PATH * 3, L"Kostik: не найден %ls\r\nПереустановите программу.\r\n", exe);
        say(msg, 1);
        return 3;
    }
    size_t len = wcslen(exe) + wcslen(rest) + 64;
    wchar_t *cmd = (wchar_t *)calloc(len, sizeof(wchar_t));
    swprintf(cmd, len, L"\"%ls\" -X utf8 -m dxaqc.desktop %ls", exe, rest);

    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si); si.cb = sizeof si;
    DWORD flags = 0;
    BOOL inherit = FALSE;
    if (hout) {
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdInput = hin; si.hStdOutput = hout; si.hStdError = herr;
        inherit = TRUE;
    } else {
        flags = DETACHED_PROCESS;
    }
    BOOL ok = CreateProcessW(exe, cmd, NULL, NULL, inherit, flags, NULL, g_base, &si, &pi);
    free(cmd);
    if (!ok) {
        wchar_t msg[MAX_PATH * 3];
        swprintf(msg, MAX_PATH * 3, L"Kostik: не удалось запустить %ls (ошибка Windows %lu)\r\n", exe, GetLastError());
        say(msg, 1);
        return 4;
    }
    DWORD code = 0;
    if (wait) {
        WaitForSingleObject(pi.hProcess, INFINITE);
        GetExitCodeProcess(pi.hProcess, &code);
    }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return (int)code;
}

static HANDLE console_handle(const wchar_t *name, DWORD access)
{
    SECURITY_ATTRIBUTES sa = { sizeof sa, NULL, TRUE };
    HANDLE h = CreateFileW(name, access, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, NULL);
    return h == INVALID_HANDLE_VALUE ? NULL : h;
}

static int real_main(void)
{
    GetModuleFileNameW(NULL, g_base, MAX_PATH * 2);
    wchar_t *slash = wcsrchr(g_base, L'\\');
    if (slash) *slash = 0;
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    {
        wchar_t self[MAX_PATH * 2];
        GetModuleFileNameW(NULL, self, MAX_PATH * 2);
        wchar_t *n = wcsrchr(self, L'\\');
        SetEnvironmentVariableW(L"KOSTIK_PROG", n ? n + 1 : self);          /* для справки: как называется команда */
    }
    const wchar_t *rest = rest_of_command_line();

    int argc = 0, want_console = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    for (int i = 1; argv && i < argc; i++)
        if (is_console_flag(argv[i])) want_console = 1;
    if (argv) LocalFree(argv);

    if (!want_console) {
#ifndef GUI_BUILD
        FreeConsole();                            /* обычный запуск из консольной сборки: окно консоли не нужно */
#endif
        return run_child(L"python\\pythonw.exe", rest, 0, NULL, NULL, NULL);
    }

    int allocated = 0;
    /* дескрипторы берём ДО подключения к консоли: перенаправление (> файл, | канал) не должно потеряться */
    HANDLE hin = GetStdHandle(STD_INPUT_HANDLE), hout = GetStdHandle(STD_OUTPUT_HANDLE), herr = GetStdHandle(STD_ERROR_HANDLE);
#ifdef GUI_BUILD
    if (!valid_handle(hout) && !valid_handle(herr)) {
        if (!AttachConsole(ATTACH_PARENT_PROCESS)) {   /* оконная сборка: подключаемся к консоли, из которой запустили */
            AllocConsole();                            /* запуск не из консоли — покажем своё окно и дождёмся клавиши */
            allocated = 1;
        }
    }
#endif
    if (!valid_handle(hin)) hin = console_handle(L"CONIN$", GENERIC_READ | GENERIC_WRITE);
    if (!valid_handle(hout)) hout = console_handle(L"CONOUT$", GENERIC_READ | GENERIC_WRITE);
    if (!valid_handle(herr)) herr = hout;
    if (!valid_handle(hout)) hout = herr;

    DWORD mode; UINT old_cp = 0;
    if (GetConsoleMode(hout, &mode)) { old_cp = GetConsoleOutputCP(); SetConsoleOutputCP(65001); }
    SetConsoleCtrlHandler(NULL, TRUE);            /* Ctrl+C достаётся программе внутри, а не запускателю */
    int code = run_child(L"python\\python.exe", rest, 1, hin, hout, herr);
    if (old_cp) SetConsoleOutputCP(old_cp);
    if (allocated) {
        wchar_t buf[8]; DWORD n;
        WriteConsoleW(hout, L"\r\nНажмите Enter, чтобы закрыть окно…", 36, &n, NULL);
        ReadConsoleW(hin, buf, 1, &n, NULL);
    }
    return code;
}

#ifdef GUI_BUILD
int WINAPI wWinMain(HINSTANCE a, HINSTANCE b, LPWSTR c, int d) { (void)a; (void)b; (void)c; (void)d; return real_main(); }
#else
int wmain(void) { return real_main(); }
#endif
