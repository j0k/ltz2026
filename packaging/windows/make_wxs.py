# -*- coding: utf-8 -*-
"""Описание .msi для wixl (WiX 3): все файлы папки приложения, ярлыки в Пуске, установка на компьютер (#157).

    python make_wxs.py <папка приложения> <версия> <out.wxs>
"""
import hashlib
import os
import sys
from xml.sax.saxutils import quoteattr

stage, version, out = sys.argv[1], sys.argv[2], sys.argv[3]
display = sys.argv[4] if len(sys.argv) > 4 else version
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
exe_id = ident("f", "Kostik.exe")
cmd_id = ident("f", "selftest.cmd")
wxs = f'''<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="Kostik {display}" Language="1049" Codepage="1251" Version="{version}" Manufacturer="команда «Квантовый Скачок»" UpgradeCode="{UPGRADE}">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" SummaryCodepage="1251"
             Description="Kostik — контроль качества денситометрии" Comments="Работает без интернета, снимки не покидают компьютер"/>
    <MajorUpgrade DowngradeErrorMessage="Уже установлена более новая версия Kostik."/>
    <Media Id="1" Cabinet="dxaqc.cab" EmbedCab="yes"/>
    <Icon Id="dxaqc.ico" SourceFile={quoteattr(os.path.join(stage, "icon.ico"))}/>
    <Property Id="ARPPRODUCTICON" Value="dxaqc.ico"/>
    <Property Id="ARPURLINFOABOUT" Value="https://ltz2026.ru"/>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLDIR" Name="Kostik">
{chr(10).join(lines)}
        </Directory>
      </Directory>
      <Directory Id="ProgramMenuFolder">
        <Directory Id="MenuDir" Name="Kostik">
          <Component Id="MenuShortcuts" Guid="{guid('menu')}" Win64="yes">
            <Shortcut Id="scApp" Name="Kostik" Target="[INSTALLDIR]Kostik.exe" WorkingDirectory="INSTALLDIR" Icon="dxaqc.ico"/>
            <Shortcut Id="scTest" Name="Проверка установки" Target="[INSTALLDIR]selftest.cmd" WorkingDirectory="INSTALLDIR" Icon="dxaqc.ico"/>
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
with open(out, "w", encoding="utf-8") as f:
    f.write(wxs)
print(f"{out}: {len(comps)} файлов")
