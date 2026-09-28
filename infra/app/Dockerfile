# Стенд Kostik. Сборка из корня репозитория: docker build -f infra/app/Dockerfile .
# 3.12: зафиксированные версии numpy и остальных пакетов проверены на этой версии Python
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DXAQC_DATA=/data \
    DXAQC_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
    DXAQC_TTS_MODEL=/models/piper/ru_RU-irina-medium.onnx \
    DXAQC_STT_MODEL=/models/whisper-small \
    DXAQC_OCR_MODEL=/models/ocr/cyrillic_PP-OCRv5_mobile_rec.onnx \
    HF_HUB_OFFLINE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*

# голос Piper для озвучки, модели скачиваются при сборке, в работе сеть не нужна
RUN mkdir -p /models/piper && cd /models/piper \
 && for f in ru_RU-irina-medium.onnx ru_RU-irina-medium.onnx.json; do \
      curl -fsSL -o "$f" "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/irina/medium/$f"; done

WORKDIR /app
COPY infra/app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# чтение надписей на отклонённых картинках (dxaqc/ocr.py): RapidOCR на onnxruntime (он уже есть — от Piper),
# OpenCV без GUI; --no-deps, чтобы не тянуть полный opencv-python. Кириллическая модель распознавания
# PaddlePaddle PP-OCRv5 (Apache 2.0) скачивается при сборке по зафиксированной ревизии и проверяется по SHA-256
RUN pip install --no-cache-dir --no-deps rapidocr_onnxruntime==1.4.4 opencv-python-headless==5.0.0.93 \
      pyclipper==1.4.0 shapely==2.1.2 PyYAML==6.0.3 six==1.17.0 tqdm==4.70.1 \
 && mkdir -p /models/ocr \
 && curl -fsSL -o /models/ocr/cyrillic_PP-OCRv5_mobile_rec.onnx \
      "https://huggingface.co/PaddlePaddle/cyrillic_PP-OCRv5_mobile_rec_onnx/resolve/2cef88145434beb8afa9dd82d77d799eb1ad7b29/inference.onnx" \
 && echo "5371ee1ddaa7983cc62d0818d99e982b6804638c85e4f960d59a574094e172e5  /models/ocr/cyrillic_PP-OCRv5_mobile_rec.onnx" | sha256sum -c -

# Whisper small для голосовых вопросов
RUN HF_HUB_OFFLINE=0 python -c "from huggingface_hub import snapshot_download as s; s('Systran/faster-whisper-small', local_dir='/models/whisper-small')" \
 && rm -rf /models/whisper-small/.cache

COPY dxaqc /app/dxaqc

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /data/runs && chown -R app:app /data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["uvicorn", "dxaqc.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
