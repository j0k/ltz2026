# -*- coding: utf-8 -*-
"""Скачать приложение с сайта (#161, #162): страница /download и файлы /downloads/…

Раскладка на диске стенда (DATA/downloads): latest.json — текущая версия и её файлы с размером и SHA-256,
<версия>/ — установщики (.exe, .msi, .deb) и SHA256SUMS, models/ — каталог моделей manifest.json и сами модели.
FileResponse отдаёт Range — большие файлы докачиваются.
"""
from __future__ import annotations

import json
import os
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(include_in_schema=False)
ctx: dict = {}
KINDS = {
    ".exe": dict(os="windows", title="Windows — установщик .exe", hint="Для Windows 10 и 11: установка для текущего пользователя, права администратора не нужны."),
    ".msi": dict(os="windows", title="Windows — пакет .msi", hint="Для администраторов и больниц: тихая установка msiexec /i … /qn на все компьютеры."),
    ".deb": dict(os="linux", title="Linux — пакет .deb", hint="Ubuntu 22.04 и 24.04, Debian 12: sudo apt install ./dxaqc_….deb"),
}


def setup(**kw):
    ctx.update(kw)


def root() -> str:
    return os.path.join(ctx["data"], "downloads")


def latest() -> dict | None:
    try:
        with open(os.path.join(root(), "latest.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    for f in data.get("files", []):
        ext = os.path.splitext(f["name"])[1].lower()
        f.update(KINDS.get(ext, dict(os="other", title=f["name"], hint="")))
        f["url"] = f"/downloads/{data['version']}/{f['name']}"
    return data


@router.get("/download", response_class=HTMLResponse)
def download_page(request: Request):
    ua = (request.headers.get("user-agent") or "").lower()
    guess = "windows" if "windows" in ua else "linux" if ("linux" in ua and "android" not in ua) else "other"
    return ctx["templates"].TemplateResponse(request, "download.html", dict(rel=latest(), guess=guess,
                                                                            og_title="Скачать приложение DXA QC"))


@router.api_route("/downloads/{path:path}", methods=["GET", "HEAD"])
def download_file(path: str):
    if not re.fullmatch(r"[A-Za-z0-9._/+-]{1,200}", path) or ".." in path.split("/"):
        raise HTTPException(404)
    full = os.path.join(root(), path)
    if not os.path.isfile(full):
        raise HTTPException(404, "файла нет")
    media = "application/json" if path.endswith(".json") else "text/plain; charset=utf-8" if path.endswith("SHA256SUMS") else "application/octet-stream"
    return FileResponse(full, media_type=media, filename=os.path.basename(full) if media == "application/octet-stream" else None)
