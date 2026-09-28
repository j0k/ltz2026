"""Страница /download и раздача файлов /downloads на стенде (#161, #162)."""
import json
import os
import sys


def test_download_page_and_files(client):
    app = sys.modules["dxaqc.web.app"]
    root = os.path.join(app.DATA, "downloads")
    os.makedirs(os.path.join(root, "9.9.9"), exist_ok=True)
    for n in ("Kostik-9.9.9-setup.exe", "Kostik-9.9.9.msi", "kostik_9.9.9_amd64.deb"):
        open(os.path.join(root, "9.9.9", n), "wb").write(b"x" * 2048)
    json.dump(dict(version="9.9.9", date="2026-09-27", files=[dict(name=n, size=2048, sha256="ab" * 32, crc32="1A2B3C4D") for n in
              ("Kostik-9.9.9-setup.exe", "Kostik-9.9.9.msi", "kostik_9.9.9_amd64.deb")]), open(os.path.join(root, "latest.json"), "w"))
    win = client.get("/download", headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}).text
    assert "Windows — установщик .exe" in win.split("Все варианты")[0], "главная кнопка — под систему посетителя"
    lin = client.get("/download", headers={"user-agent": "Mozilla/5.0 (X11; Linux x86_64)"}).text
    assert "Linux — пакет .deb" in lin.split("Все варианты")[0] and "Claude" not in lin
    r = client.get("/downloads/9.9.9/kostik_9.9.9_amd64.deb", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206 and len(r.content) == 100, "докачка"
    assert client.head("/downloads/9.9.9/Kostik-9.9.9.msi").headers["content-length"] == "2048", "HEAD для менеджеров загрузок"
    assert "github.com/j0k/ltz2026" in win
    assert "1A2B3C4D" in win and "2 048 байт" in win and "CRC32SUMS" in win, "CRC32 и точные размеры в таблице файлов"
    assert client.get("/downloads/../app.db").status_code == 404
    assert client.get("/downloads/latest.json").json()["version"] == "9.9.9"
    assert 'href="/download"' in client.get("/").text, "тихая ссылка на главной"


def test_download_page_has_screenshot_gallery(client):
    """Юрий, 28.09: на странице загрузки — галерея скриншотов с подписями и автопролистыванием."""
    html = client.get("/download").text
    assert 'id="shots"' in html and "/static/shots.js" in html
    assert html.count('class="sh-slide') == 9 and html.count('class="sh-text') == 9, "9 скриншотов с подписями"
    assert 'src="/static/shots/home.webp' in html and 'data-src="/static/shots/dashboard.webp' in html, "первый сразу, остальные лениво"
    for key in ("home", "dashboard", "card", "text", "control", "help", "mcp", "models", "history"):
        assert client.get(f"/static/shots/{key}.webp").status_code == 200, key
    assert "Kostik 1.0-Beta" in html
    js = client.get("/static/shots.js").text
    assert "prefers-reduced-motion" in js and "visibilitychange" in js


def test_linux_install_command_uses_real_file_name(client):
    """Алексей, 28.09: команда установки должна совпадать с именем файла (регистр важен в Linux)."""
    import re
    html = client.get("/download").text
    names = re.findall(r'href="/downloads/[^"]+/([^"/]+\.deb)"', html)
    if names:
        assert f"sudo apt install ./{names[0]}" in html
    assert "Алексей Чуркин и Юрий Коноплёв" in html
