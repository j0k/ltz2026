# -*- coding: utf-8 -*-
"""Адрес, на котором слушает сервер приложения: kostik --host … и список адресов kostik --show-all-hosts.

По умолчанию 127.0.0.1 — программа видна только с этого компьютера. Любой другой адрес открывает её по сети,
а входа по паролю в приложении нет: так делают только в доверенной сети.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import subprocess
import sys
import time

DEFAULT = "127.0.0.1"
ANY = {"0.0.0.0": "127.0.0.1", "::": "::1"}         # «все интерфейсы»: сами к себе ходим через петлю


def bind_host() -> str:
    return os.environ.get("DXAQC_HOST") or DEFAULT


def family(host: str) -> int:
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def local(host: str | None = None) -> str:
    """Адрес для собственных запросов программы к своему серверу."""
    host = host or bind_host()
    return ANY.get(host, host)


def url(port: int, host: str | None = None) -> str:
    h = local(host)
    return f"http://[{h}]:{port}" if ":" in h else f"http://{h}:{port}"


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_own = {"at": 0.0, "ips": set()}


def is_own(addr: str) -> bool:
    """Запрос пришёл с этого же компьютера: с петли или с одного из его адресов."""
    if is_loopback(bind_host()):
        return True                                  # слушаем только петлю — чужих запросов не бывает
    addr = (addr or "").split("%")[0]
    addr = addr[7:] if addr.startswith("::ffff:") else addr
    if is_loopback(addr):
        return True
    if time.time() - _own["at"] > 30:                # адреса меняются редко: сеть подключили, VPN включили
        _own.update(at=time.time(), ips={ip for ip, _ in interfaces()})
    return addr in _own["ips"]


def check(host: str) -> str | None:
    """None, если на адресе можно слушать; иначе — объяснение для человека."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return f"--host: «{host}» — не IP-адрес; список адресов: kostik --show-all-hosts"
    try:
        with socket.socket(family(host)) as s:
            s.bind((host, 0))
    except OSError as e:
        return f"--host: на адресе {host} слушать нельзя ({e.strerror or e}); список адресов: kostik --show-all-hosts"
    return None


def _windows() -> list[tuple[str, str]]:
    import ctypes
    from ctypes import wintypes as w

    class SockAddr(ctypes.Structure):
        _fields_ = [("p", ctypes.c_void_p), ("n", ctypes.c_int)]

    class Unicast(ctypes.Structure):
        pass
    Unicast._fields_ = [("length", w.ULONG), ("flags", w.DWORD), ("next", ctypes.POINTER(Unicast)), ("address", SockAddr)]

    class Adapter(ctypes.Structure):
        pass
    Adapter._fields_ = [("length", w.ULONG), ("index", w.DWORD), ("next", ctypes.POINTER(Adapter)), ("name", ctypes.c_char_p),
                        ("unicast", ctypes.POINTER(Unicast)), ("anycast", ctypes.c_void_p), ("multicast", ctypes.c_void_p),
                        ("dns", ctypes.c_void_p), ("suffix", ctypes.c_wchar_p), ("description", ctypes.c_wchar_p),
                        ("friendly", ctypes.c_wchar_p), ("mac", ctypes.c_ubyte * 8), ("mac_len", w.ULONG),
                        ("adapter_flags", w.ULONG), ("mtu", w.ULONG), ("if_type", w.ULONG), ("status", ctypes.c_int)]

    size, rc, buf = w.ULONG(16384), 111, None
    for _ in range(4):                                   # 111 — буфер мал, size уже исправлен
        buf = ctypes.create_string_buffer(size.value)
        rc = ctypes.windll.iphlpapi.GetAdaptersAddresses(0, 0x0E, None, buf, ctypes.byref(size))
        if rc != 111:
            break
    if rc != 0:
        return []
    out, a = [], ctypes.cast(buf, ctypes.POINTER(Adapter))
    while a:
        ad = a.contents
        u = ad.unicast if ad.status == 1 and ad.if_type != 24 else None      # включён и не петля
        while u:
            sa = u.contents.address
            raw = ctypes.string_at(sa.p, sa.n)
            fam = int.from_bytes(raw[:2], "little")
            if fam == 2:
                out.append((socket.inet_ntop(socket.AF_INET, raw[4:8]), ad.friendly or ""))
            elif fam == 23:
                out.append((socket.inet_ntop(socket.AF_INET6, raw[8:24]), ad.friendly or ""))
            u = u.contents.next
        a = ad.next
    return out


def _linux() -> list[tuple[str, str]]:
    try:
        data = json.loads(subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True, timeout=5).stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [(i["local"], d.get("ifname", "")) for d in data if "UP" in d.get("flags", []) and "LOOPBACK" not in d.get("flags", [])
            for i in d.get("addr_info", []) if i.get("local")]


def _by_name() -> list[tuple[str, str]]:
    try:
        return [(i[4][0].split("%")[0], "") for i in socket.getaddrinfo(socket.gethostname(), None)]
    except OSError:
        return []


def interfaces() -> list[tuple[str, str]]:
    """Адреса сетевых интерфейсов этого компьютера с названиями; без петли и адресов «только для соседей»."""
    try:
        found = _windows() if sys.platform.startswith("win") else _linux()
    except Exception:  # noqa: BLE001
        found = []
    found = found or _by_name()
    order = {name: n for n, name in reversed(list(enumerate(name for _, name in found)))}
    out, seen = [], set()
    for ip, name in sorted(found, key=lambda f: (order[f[1]], ":" in f[0])):      # по интерфейсам, IPv4 раньше IPv6
        a = ipaddress.ip_address(ip)
        if ip in seen or a.is_loopback or a.is_link_local or a.is_unspecified:
            continue
        seen.add(ip)
        out.append((ip, name))
    return out


def listing(current: str | None = None) -> str:
    """Все значения для --host, отмечено текущее."""
    current = current or bind_host()
    groups = [[("127.0.0.1", "только этот компьютер (по умолчанию)"),
               ("0.0.0.0", "все интерфейсы этого компьютера")],
              [(ip, name or "сетевой интерфейс") for ip, name in interfaces()],
              [("::1", "только этот компьютер, IPv6"), ("::", "все интерфейсы, IPv6")]]
    lines = ["Адреса для --host:", ""]
    for g in groups:
        if g:
            lines += [f"  {'✓' if ip == current else ' '} {ip} — {what}" for ip, what in g] + [""]
    lines += ["Пример: kostik --host 0.0.0.0 --port 8765",
              "Любой адрес, кроме 127.0.0.1 и ::1, открывает программу по сети; входа по паролю в ней нет."]
    return "\n".join(lines)
