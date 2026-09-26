# -*- coding: utf-8 -*-
"""Страница /tz/: карточки документов, просмотр и скачивание PDF, отсутствующий файл и чужие имена."""
from __future__ import annotations

import json

import pytest

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@pytest.fixture()
def tz_dir(tmp_path, monkeypatch):
    (tmp_path / "tz-04.pdf").write_bytes(PDF)
    (tmp_path / "tz-04.png").write_bytes(PNG)
    (tmp_path / "razbor.pdf").write_bytes(PDF)
    (tmp_path / "meta.json").write_text(json.dumps({"tz-04": {"pages": 12}}), encoding="utf-8")
    (tmp_path / "secret.pdf").write_bytes(PDF)
    monkeypatch.setenv("DXAQC_TZ_DIR", str(tmp_path))
    return tmp_path


def test_page_lists_documents(client, tz_dir):
    r = client.get("/tz", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/tz/"
    page = client.get("/tz/")
    assert page.status_code == 200
    html = page.text
    for title in ("ТЗ задачи 04", "выбор задачи и разбор задачи 04", "Команда «Квантовый Скачок»"):
        assert title in html
    assert "12 стр." in html and 'src="/tz/tz-04.png"' in html
    assert 'href="/tz/razbor/download"' in html
    assert "файл ещё не выложен" in html, "у команды файла в каталоге нет"
    assert 'href="/tz/"' in client.get("/").text, "ссылка в шапке"


def test_pdf_inline_and_download(client, tz_dir):
    r = client.get("/tz/tz-04.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content == PDF
    assert r.headers["content-disposition"].startswith("inline")
    d = client.get("/tz/tz-04/download")
    assert d.status_code == 200 and d.headers["content-disposition"].startswith("attachment")
    assert "filename*=utf-8''" in d.headers["content-disposition"].lower()
    assert client.get("/tz/tz-04.png").headers["content-type"] == "image/png"


def test_only_catalog_files_are_served(client, tz_dir):
    assert client.get("/tz/komanda.pdf").status_code == 404
    assert client.get("/tz/secret.pdf").status_code == 404
    assert client.get("/tz/meta.png").status_code == 404
    assert client.get("/tz/..%2Fsecret.pdf").status_code == 404
    assert client.get("/tz/razbor.png").status_code == 404
