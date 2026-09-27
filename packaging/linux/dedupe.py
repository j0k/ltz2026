# -*- coding: utf-8 -*-
"""Одинаковые файлы в наборах библиотек под разные версии Python — жёсткими ссылками: пакет меньше."""
import hashlib
import os
import sys

seen, saved = {}, 0
for d, _, fs in os.walk(sys.argv[1]):
    for f in fs:
        p = os.path.join(d, f)
        if os.path.islink(p):
            continue
        st = os.stat(p)
        h = hashlib.sha1(open(p, "rb").read()).hexdigest() + f":{st.st_size}:{oct(st.st_mode)}"
        if h in seen:
            os.remove(p)
            os.link(seen[h], p)
            saved += st.st_size
        else:
            seen[h] = p
print(f"одинаковых файлов свёрнуто: {saved / 1e6:.0f} МБ")
