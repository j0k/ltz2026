# Компилятор для запускателя Kostik.exe (mingw-w64): на машине сборки его нет, образ собирается один раз
FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc-mingw-w64-x86-64 binutils-mingw-w64-x86-64 make \
 && rm -rf /var/lib/apt/lists/*
