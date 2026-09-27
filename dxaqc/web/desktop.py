# -*- coding: utf-8 -*-
"""Страницы и API настольного приложения (DXAQC_MODE=desktop): справка, о программе, модели, ИИ-ассистент,
настройки, история, проверка локальных файлов и папок, синтетическое демо (#139–#154)."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from dxaqc import __version__
from dxaqc import desktop as D
from dxaqc.desktop import models as M
from dxaqc.desktop import paths, synth

router = APIRouter(include_in_schema=False)
ctx: dict = {}
HELP_DIR = os.path.join(os.path.dirname(D.__file__), "help")
DEFAULTS = dict(welcomed=False, mcp_enabled=True, mcp_token="", check_updates=False)
_settings_lock = threading.Lock()


def setup(**kw):
    """read, new_run, write_status, submit, runs_dir, list_runs, has_archives, templates, example_id, port."""
    ctx.update(kw)


# ------------------------------------------------------------------ настройки

def settings() -> dict:
    try:
        with open(paths.settings_path(), encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(**kw) -> dict:
    with _settings_lock:
        s = {**settings(), **kw}
        tmp = paths.settings_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        os.replace(tmp, paths.settings_path())
        return s


def mcp_token() -> str | None:
    """Токен локального ассистента: создаётся при первом запуске, хранится в настройках пользователя."""
    from dxaqc.web import accounts as A
    s = settings()
    if not s["mcp_enabled"]:
        return None
    tok = A.resolve_api_token(s.get("mcp_token") or "")
    if tok and tok["status"] == "active":
        return s["mcp_token"]
    secret, _ = A.create_api_token("desktop", "Локальный ИИ-ассистент", scope="analyze", daily_limit=100000)
    save_settings(mcp_token=secret)
    return secret


def set_mcp(enabled: bool):
    from dxaqc.web import accounts as A
    s = settings()
    if not enabled and s.get("mcp_token"):
        tok = A.resolve_api_token(s["mcp_token"])
        if tok:
            A.revoke_api_token(tok["id"])
        save_settings(mcp_enabled=False, mcp_token="")
    elif enabled:
        save_settings(mcp_enabled=True)
        mcp_token()


def base_url() -> str:
    return f"http://127.0.0.1:{ctx.get('port', D.DEFAULT_PORT)}"


def stdio_command() -> list[str]:
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):              # для stdio нужен консольный python.exe
        exe = exe[:-len("pythonw.exe")] + "python.exe"
    return [exe, "-m", "dxaqc.desktop", "--mcp-stdio"]


# ------------------------------------------------------------------ справка

def help_topics() -> list[dict]:
    from markdown_it import MarkdownIt
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    out = []
    for p in sorted(glob.glob(os.path.join(HELP_DIR, "*.md"))):
        with open(p, encoding="utf-8") as f:
            text = f.read()
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), os.path.basename(p))
        body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("# "))
        slug = re.sub(r"^\d+-", "", os.path.splitext(os.path.basename(p))[0])
        out.append(dict(slug=slug, title=title, html=md.render(body), text=re.sub(r"\s+", " ", body).lower()))
    return out


def _page(request: Request, name: str, **kw):
    return ctx["templates"].TemplateResponse(request, name, dict(version=__version__, D=D, **kw))


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request):
    return _page(request, "desk_help.html", topics=help_topics())


@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    return _page(request, "desk_about.html", licenses=third_party())


def third_party() -> list[dict]:
    """Лицензии сторонних компонентов — из метаданных установленных пакетов (#151)."""
    from importlib import metadata
    names = ["fastapi", "starlette", "uvicorn", "jinja2", "python-multipart", "pydicom", "pylibjpeg", "pylibjpeg-libjpeg",
             "pylibjpeg-openjpeg", "numpy", "pillow", "openpyxl", "markdown-it-py", "pywebview", "piper-tts", "onnxruntime"]
    out = []
    for n in names:
        try:
            meta = metadata.metadata(n)
        except metadata.PackageNotFoundError:
            continue
        lic = meta.get("License-Expression") or meta.get("License") or ""
        if not lic or len(lic) > 60:
            lic = next((c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")), lic[:60])
        out.append(dict(name=meta.get("Name", n), version=meta.get("Version", ""), license=lic))
    out += [dict(name="three.js", version="r180", license="MIT"), dict(name="шрифт DejaVu Sans", version="2.37", license="Bitstream Vera / free")]
    return out


# ------------------------------------------------------------------ модели

@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request):
    return _page(request, "desk_models.html")


@router.get("/api/models")
def api_models(refresh: int = 0):
    if refresh:
        M.fetch_manifest(force=True)
    return M.listing()


@router.post("/api/models/{key}/{action}")
def api_model_action(key: str, action: str):
    try:
        if action == "download":
            M.start(key)
        elif action == "pause":
            M.pause(key)
        elif action == "delete":
            M.delete(key)
        else:
            raise HTTPException(404)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return M.listing()


@router.post("/api/models/{key}/import")
async def api_model_import(key: str, file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, dir=paths.models_dir(), suffix=".import") as tmp:
        shutil.copyfileobj(file.file, tmp)
    try:
        M.import_file(key, file.filename or "", tmp.name)
    except (LookupError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
    return M.listing()


# ------------------------------------------------------------------ ИИ-ассистент (локальный MCP)

@router.get("/assistant", response_class=HTMLResponse)
def assistant_page(request: Request):
    token = mcp_token()
    cmd = stdio_command()
    url = base_url() + "/mcp"
    cfg = dict(
        claude=json.dumps({"mcpServers": {"dxa-qc": {"command": cmd[0], "args": cmd[1:]}}}, ensure_ascii=False, indent=2),
        cursor=json.dumps({"mcpServers": {"dxa-qc": {"url": url, "headers": {"Authorization": f"Bearer {token}"}}}}, indent=2) if token else "",
        vscode=json.dumps({"servers": {"dxa-qc": {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {token}"}}}}, indent=2)
        if token else "")
    return _page(request, "desk_assistant.html", token=token, url=url, cmd=" ".join(f'"{c}"' if " " in c else c for c in cmd), cfg=cfg,
                 enabled=settings()["mcp_enabled"])


@router.post("/assistant/toggle")
def assistant_toggle(enabled: str = Form("")):
    set_mcp(enabled == "1")
    return RedirectResponse("/assistant", status_code=303)


@router.post("/api/assistant/check")
def assistant_check():
    """Проверка связи: тот же токен и те же инструменты, что увидит ассистент."""
    from dxaqc.web import accounts as A, mcp
    token = mcp_token()
    tok = A.resolve_api_token(token or "")
    if not tok or tok["status"] != "active":
        return dict(ok=False, text="ассистент выключен — включите его на этой странице")
    tools = [t["name"] for t in mcp.TOOLS if t["scope"] == "read" or tok["scope"] == "analyze"]
    return dict(ok=True, text=f"сервер работает: {len(tools)} инструментов, адрес {base_url()}/mcp", tools=tools)


# ------------------------------------------------------------------ настройки, история, первый запуск

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return _page(request, "desk_settings.html", s=settings(), data_dir=paths.data_dir(), log=paths.log_path())


@router.post("/settings")
def settings_save(check_updates: str = Form(""), welcome_again: str = Form("")):
    kw = dict(check_updates=check_updates == "1")
    if welcome_again == "1":
        kw["welcomed"] = False
    save_settings(**kw)
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.get("/api/updates")
def updates():
    """Проверка новой версии — только если пользователь включил её в настройках (по умолчанию выключено: работа без сети)."""
    if not settings()["check_updates"]:
        return dict(enabled=False)
    try:
        with urllib.request.urlopen(D.SITE + "/downloads/latest.json", timeout=10) as r:
            latest = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001
        return dict(enabled=True, error=f"сайт недоступен ({type(exc).__name__})")
    newer = _ver(latest.get("version", "0")) > _ver(__version__)
    return dict(enabled=True, current=__version__, latest=latest.get("version"), newer=newer, url=D.SITE + "/download")


def _ver(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


@router.post("/desktop/welcomed")
def welcomed():
    save_settings(welcomed=True)
    return dict(ok=True)


@router.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return _page(request, "desk_history.html", runs=ctx["list_runs"](500))


@router.post("/history/{run_id}/delete")
def history_delete(run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id) or run_id == ctx.get("example_id"):
        raise HTTPException(400, "этот прогон удалить нельзя")
    shutil.rmtree(os.path.join(ctx["runs_dir"], run_id), ignore_errors=True)
    return RedirectResponse("/history", status_code=303)


# ------------------------------------------------------------------ проверка локальных файлов и демо

def _copy_into(src: str, dest: str):
    name = os.path.basename(os.path.normpath(src)) or "input"
    target = os.path.join(dest, name)
    if os.path.isdir(src):
        shutil.copytree(src, target, dirs_exist_ok=True)
    else:
        shutil.copy2(src, target)


@router.post("/desktop/run-local")
async def run_local(request: Request):
    """Проверка файлов и папок с диска по пути — из диалога «Открыть» или «Открыть с помощью» (#140)."""
    body = await request.json()
    items = [p for p in (body.get("paths") or []) if isinstance(p, str)]
    missing = [p for p in items if not os.path.exists(p)]
    if not items or missing:
        raise HTTPException(400, "файлы не найдены: " + ", ".join(missing[:3]) if missing else "не выбрано ни одного файла")
    title = os.path.basename(os.path.normpath(items[0])) + (f" и ещё {len(items) - 1}" if len(items) > 1 else "")
    run_id = ctx["new_run"](f"Проверка: {title}")
    dest = os.path.join(ctx["runs_dir"], run_id, "input")
    try:
        for p in items:
            _copy_into(p, dest)
    except OSError as exc:
        ctx["write_status"](run_id, state="error", error=f"не удалось прочитать файлы: {exc}"[:300])
        return dict(run_id=run_id, url=f"/check/{run_id}")
    ctx["write_status"](run_id, has_archives=ctx["has_archives"](run_id))
    ctx["submit"](run_id)
    url = f"/check/{run_id}"
    if body.get("navigate") and ctx.get("navigate"):
        ctx["navigate"](base_url() + url)
    return dict(run_id=run_id, url=url)


DEMOS = [("ok", "Фантом без нарушений", "поясница и оба бедра — синтетический фантом"),
         ("artifact", "Фантом с посторонним предметом", "металлическая застёжка рядом с позвоночником")]


def demo_presets() -> list[dict]:
    return [dict(key=f"synth-{k}", title=t, sub=s, thumb=f"/desktop/demo-thumb/{k}.png", expert="синтетический фантом, не снимок пациента")
            for k, t, s in DEMOS]


def start_demo(variant: str, title: str | None = None, run_id: str | None = None, **status) -> str:
    run_id = ctx["new_run"](title or f"Демо: {dict((k, t) for k, t, _ in DEMOS).get(variant, variant)}", run_id)
    synth.study(os.path.join(ctx["runs_dir"], run_id, "input"), variant)
    ctx["write_status"](run_id, demo=variant, **status)   # всё до запуска: потом статус пишет поток анализа
    ctx["submit"](run_id)
    return run_id


@router.get("/desktop/demo-thumb/{variant}.png")
def demo_thumb(variant: str):
    from io import BytesIO
    from PIL import Image
    from fastapi.responses import Response
    if variant not in {k for k, _, _ in DEMOS}:
        raise HTTPException(404)
    im = Image.fromarray(synth.spine(artifact=variant == "artifact")).resize((240, 254))
    buf = BytesIO()
    im.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "max-age=86400"})


def seed_example():
    """Пример в приложении — синтетический фантом: данных организатора в установщике нет (#150)."""
    ex = ctx["example_id"]
    st = ctx["read"](ex, "status.json")
    if st and st.get("state") == "done" and st.get("version") == __version__:
        return
    shutil.rmtree(os.path.join(ctx["runs_dir"], ex), ignore_errors=True)
    start_demo("ok", "Демо: синтетический фантом", ex, version=__version__)


@router.get("/desktop/ping")
def ping():
    ctx["last_ping"] = time.time()
    return dict(ok=True)


def open_path(path: str):
    """Открыть папку в проводнике или файловом менеджере."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ------------------------------------------------------------------ MCP в приложении

def patch_mcp(mcp):
    """Инструменты для локальной работы: без наборов организатора, зато проверка файлов по пути на диске (#153)."""
    mcp.TOOLS[:] = [t for t in mcp.TOOLS if t["name"] not in ("list_datasets", "analyze_dataset")]
    if "analyze_paths" not in mcp.TOOL_BY_NAME:
        tool = dict(name="analyze_paths", scope="analyze", title="Проверить файлы и папки на диске",
                    description="Проверяет DICOM, zip-архивы и папки исследований по путям на этом компьютере — без пересылки "
                                "содержимого. wait=true ждёт результата до 170 секунд, иначе ответ сразу с run_id.",
                    inputSchema=mcp._schema({"paths": {"type": "array", "minItems": 1, "maxItems": 200, "items": {"type": "string"}},
                                             "wait": {"type": "boolean", "default": False}}, ["paths"]))
        mcp.TOOLS.insert(3, tool)
        mcp.TOOL_BY_NAME["analyze_paths"] = tool
        mcp.HANDLERS["analyze_paths"] = _t_analyze_paths
    mcp.INSTRUCTIONS = ("DXA QC — настольное приложение контроля качества денситометрии DXA, работает на этом компьютере. "
                        "analyze_paths проверяет файлы и папки по путям, analyze_files — переданные в base64; get_run показывает ход, "
                        "get_results и get_image — результаты. Не для клинических выводов.")


def _t_analyze_paths(args, token):
    from dxaqc.web import mcp
    items = [p for p in (args.get("paths") or []) if isinstance(p, str)]
    missing = [p for p in items if not os.path.exists(p)]
    if not items:
        raise mcp.ToolError("paths: список путей к файлам или папкам")
    if missing:
        raise mcp.ToolError("не найдены: " + ", ".join(missing[:5]))
    run_id = ctx["new_run"](f"ИИ-ассистент: {os.path.basename(os.path.normpath(items[0]))}")
    dest = os.path.join(ctx["runs_dir"], run_id, "input")
    for p in items:
        _copy_into(p, dest)
    ctx["write_status"](run_id, has_archives=ctx["has_archives"](run_id), started_by=f"mcp:{token['name']}")
    ctx["submit"](run_id)
    result = dict(run_id=run_id, state="queued", page=base_url() + f"/check/{run_id}")
    if args.get("wait"):
        t0 = time.time()
        while time.time() - t0 < mcp.WAIT_MAX:
            if (ctx["read"](run_id, "status.json") or {}).get("state") in ("done", "error", "cancelled"):
                break
            time.sleep(0.5)
        result.update(mcp.t_get_run({"run_id": run_id}, token))
    return result
