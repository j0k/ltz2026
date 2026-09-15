# -*- coding: utf-8 -*-
"""Голос стенда: озвучка пояснений (Piper) и распознавание вопросов (faster-whisper).

Обе модели лежат в контейнере и работают без внешних сервисов. Whisper загружается по первому вопросу
и выгружается после простоя, потому что сервер общий и память на нём ограничена.
"""
from __future__ import annotations

import gc
import hashlib
import os
import re
import tempfile
import threading
import time
import wave

TTS_MODEL = os.environ.get("DXAQC_TTS_MODEL", "/models/piper/ru_RU-irina-medium.onnx")
STT_MODEL = os.environ.get("DXAQC_STT_MODEL", "/models/whisper-small")
STT_IDLE = int(os.environ.get("DXAQC_STT_IDLE", "600"))
MAX_TEXT = 900
MAX_AUDIO = 3 * 1024 * 1024
CACHE_FILES = 600
PROMPT = ("Позвонки L1, L2, L3, L4, L5, Th12. Ось позвоночника, подвздошные кости, посторонний предмет, "
          "большой вертел, шейка бедра, диафиз, тазовая кость. Что не так со снимком?")

_tts = None
_tts_lock = threading.Lock()
_stt = None
_stt_used = 0.0
_stt_lock = threading.Lock()

def _degrees(num: str) -> str:
    """Согласование: 2,2 градуса, 1 градус, 3 градуса, 5 градусов."""
    if "," in num:
        return "градуса"
    n = int(num)
    if n % 10 == 1 and n % 100 != 11:
        return "градус"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "градуса"
    return "градусов"


_SUBS = [
    (re.compile(r"L1\s*[–-]\s*L4"), "с первого по четвёртый поясничный"),
    (re.compile(r"Th\s?12"), "тэ-аш двенадцать"),
    (re.compile(r"\bL\s?([1-5])\b"), r"эл \1"),
    (re.compile(r"(\d)\.(\d)"), r"\1,\2"),
    (re.compile(r"(\d+(?:,\d+)?)\s*°"), lambda m: f"{m.group(1)} {_degrees(m.group(1))}"),
    (re.compile(r"\bТЗ\b"), "техническому заданию"),
    (re.compile(r"\bpx\b"), "пикселей"),
    (re.compile(r"[«»\"()]"), ""),
    (re.compile(r"\s+"), " "),
]


def status() -> dict:
    return dict(tts=os.path.isfile(TTS_MODEL), stt=os.path.isfile(os.path.join(STT_MODEL, "model.bin")))


def speech_text(text: str) -> str:
    """Текст для синтеза: латинские обозначения позвонков и единицы словами."""
    t = text.strip()
    for rx, rep in _SUBS:
        t = rx.sub(rep, t)
    return t[:MAX_TEXT].strip()


def _prune(cache_dir: str):
    files = sorted((os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.endswith(".wav")), key=os.path.getmtime)
    for p in files[:-CACHE_FILES]:
        try:
            os.remove(p)
        except OSError:
            pass


def tts_wav(text: str, cache_dir: str) -> str:
    """Путь к WAV с озвучкой; одинаковые фразы берутся из кэша."""
    t = speech_text(text)
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha1(f"{os.path.basename(TTS_MODEL)}|{t}".encode()).hexdigest()
    path = os.path.join(cache_dir, key + ".wav")
    if os.path.exists(path):
        return path
    global _tts
    with _tts_lock:
        if not os.path.exists(path):
            if _tts is None:
                from piper import PiperVoice
                _tts = PiperVoice.load(TTS_MODEL)
            tmp = path + ".tmp"
            with wave.open(tmp, "wb") as w:
                _tts.synthesize_wav(t, w)
            os.replace(tmp, path)
            _prune(cache_dir)
    return path


def _unload_when_idle():
    global _stt
    while True:
        time.sleep(30)
        with _stt_lock:
            if _stt is not None and time.time() - _stt_used > STT_IDLE:
                _stt = None
                gc.collect()
                return


def transcribe(data: bytes, suffix: str = ".webm") -> str:
    """Текст вопроса из записи браузера (webm, ogg, mp4). Язык русский."""
    global _stt, _stt_used
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        with _stt_lock:
            if _stt is None:
                from faster_whisper import WhisperModel
                _stt = WhisperModel(STT_MODEL, device="cpu", compute_type="int8", cpu_threads=2)
                threading.Thread(target=_unload_when_idle, daemon=True).start()
            segs, _info = _stt.transcribe(f.name, language="ru", beam_size=1, vad_filter=True,
                                          initial_prompt=PROMPT, condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segs)
            _stt_used = time.time()
    return text.strip()
