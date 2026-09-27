"""Страница /download и раздача файлов /downloads на стенде (#161, #162)."""
import json
import os
import sys


def test_download_page_and_files(client):
    app = sys.modules["dxaqc.web.app"]
    root = os.path.join(app.DATA, "downloads")
    os.makedirs(os.path.join(root, "9.9.9"), exist_ok=True)
    for n in ("DXAQC-9.9.9-setup.exe", "DXAQC-9.9.9.msi", "dxaqc_9.9.9_amd64.deb"):
        open(os.path.join(root, "9.9.9", n), "wb").write(b"x" * 2048)
    json.dump(dict(version="9.9.9", date="2026-09-27", files=[dict(name=n, size=2048, sha256="ab" * 32) for n in
              ("DXAQC-9.9.9-setup.exe", "DXAQC-9.9.9.msi", "dxaqc_9.9.9_amd64.deb")]), open(os.path.join(root, "latest.json"), "w"))
    win = client.get("/download", headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}).text
    assert "Windows — установщик .exe" in win.split("Все варианты")[0], "главная кнопка — под систему посетителя"
    lin = client.get("/download", headers={"user-agent": "Mozilla/5.0 (X11; Linux x86_64)"}).text
    assert "Linux — пакет .deb" in lin.split("Все варианты")[0] and "Claude" not in lin
    r = client.get("/downloads/9.9.9/dxaqc_9.9.9_amd64.deb", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206 and len(r.content) == 100, "докачка"
    assert client.get("/downloads/../app.db").status_code == 404
    assert client.get("/downloads/latest.json").json()["version"] == "9.9.9"
    assert 'href="/download"' in client.get("/").text, "тихая ссылка на главной"
