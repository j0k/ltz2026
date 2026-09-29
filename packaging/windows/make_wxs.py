# -*- coding: utf-8 -*-
"""Описание .msi для wixl (WiX 3): все файлы папки приложения, ярлыки в Пуске, установка на компьютер (#157).

    python make_wxs.py <папка приложения> <версия> <out.wxs>

Все строки пакета — только латиницей. wixl (msitools) пишет таблицу строк без кодовой страницы: с одной русской строкой
Windows Installer читает имена папок со сдвигом, и установка кончается ошибкой 1324 «путь содержит недопустимый символ»
и кодом 1603 — каждый раз на новой папке. Русский интерфейс установки — в установщике .exe (NSIS).
"""
import hashlib
import os
import sys
from xml.sax.saxutils import quoteattr

stage, version, out = sys.argv[1], sys.argv[2], sys.argv[3]
display = sys.argv[4] if len(sys.argv) > 4 else version
short = ".".join(version.split(".")[:2])          # 1.0.0 → 1.0: папка C:\Program Files\Kostik-1.0
UPGRADE = "6F0C2A57-3E1B-4B7E-9A55-2D7C4E0A1B26"       # постоянный: новые версии заменяют старые


def ident(prefix, rel):
    return prefix + hashlib.sha1(rel.encode()).hexdigest()[:24]


def guid(rel):
    h = hashlib.md5(("dxaqc:" + rel).encode()).hexdigest().upper()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


lines, comps = [], []


def walk(folder, rel, depth):
    ind = "  " * depth
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if name.startswith(".") or name.endswith((".", " ")) or set(name) & set('\\/:*?"<>|'):
            # Windows Installer такое имя не примет: установка кончится ошибкой 1324 и кодом 1603 уже у пользователя
            sys.exit(f"make_wxs: имя не годится для .msi: {p}")
        r = f"{rel}/{name}" if rel else name
        if os.path.isdir(p):
            lines.append(f'{ind}<Directory Id="{ident("d", r)}" Name={quoteattr(name)}>')
            walk(p, r, depth + 1)
            lines.append(f"{ind}</Directory>")
        else:
            cid = ident("c", r)
            comps.append(cid)
            lines.append(f'{ind}<Component Id="{cid}" Guid="{guid(r)}" Win64="yes">'
                         f'<File Id="{ident("f", r)}" Name={quoteattr(name)} Source={quoteattr(p)} KeyPath="yes"/></Component>')


walk(stage, "", 6)
exe_id = ident("f", "Kostik.exe")               # ярлыки — на оконный запускатель; консольный — Kostik-cli.exe
cmd_id = ident("f", "selftest.cmd")
wxs = f'''<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="Kostik {display}" Language="1049" Version="{version}" Manufacturer="Kvantovyi Skachok team" UpgradeCode="{UPGRADE}">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine"
             Description="Kostik - DXA densitometry quality control" Comments="Works offline, images never leave the computer"/>
    <MajorUpgrade DowngradeErrorMessage="A newer version of Kostik is already installed."/>
    <Media Id="1" Cabinet="dxaqc.cab" EmbedCab="yes"/>
    <Icon Id="dxaqc.ico" SourceFile={quoteattr(os.path.join(stage, "icon.ico"))}/>
    <Property Id="ARPPRODUCTICON" Value="dxaqc.ico"/>
    <Property Id="ARPURLINFOABOUT" Value="https://ltz2026.ru"/>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLDIR" Name="Kostik-{short}">
{chr(10).join(lines)}
        </Directory>
      </Directory>
      <Directory Id="ProgramMenuFolder">
        <Directory Id="MenuDir" Name="Kostik">
          <Component Id="MenuShortcuts" Guid="{guid('menu')}" Win64="yes">
            <Shortcut Id="scApp" Name="Kostik" Target="[INSTALLDIR]Kostik.exe" WorkingDirectory="INSTALLDIR" Icon="dxaqc.ico"/>
            <Shortcut Id="scTest" Name="Kostik self-test" Target="[INSTALLDIR]selftest.cmd" WorkingDirectory="INSTALLDIR" Icon="dxaqc.ico"/>
            <Shortcut Id="scVerbose" Name="Kostik verbose log" Target="[INSTALLDIR]verbose.cmd" WorkingDirectory="INSTALLDIR" Icon="dxaqc.ico"/>
            <RemoveFolder Id="rmMenu" On="uninstall"/>
            <RegistryValue Root="HKLM" Key="Software\\DXA QC" Name="menu" Type="integer" Value="1" KeyPath="yes"/>
          </Component>
        </Directory>
      </Directory>
    </Directory>
    <Feature Id="Main" Title="Kostik" Level="1">
{chr(10).join(f'      <ComponentRef Id="{c}"/>' for c in comps)}
      <ComponentRef Id="MenuShortcuts"/>
    </Feature>
  </Product>
</Wix>
'''
try:
    wxs.encode("ascii")
except UnicodeEncodeError as e:
    sys.exit(f"make_wxs: в описании .msi не латиница: {wxs[max(0, e.start - 60):e.end + 20]!r} — такой пакет не установится (ошибка 1324)")
with open(out, "w", encoding="utf-8") as f:
    f.write(wxs)
print(f"{out}: {len(comps)} файлов")
