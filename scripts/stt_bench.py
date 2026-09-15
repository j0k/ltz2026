# -*- coding: utf-8 -*-
"""Замер моделей Whisper для голосовых вопросов стенда: точность на доменных фразах, время и память.

Запускается в контейнере образа стенда с его лимитами, по процессу на модель:
    docker run --rm --cpus 1.5 --memory 1500m --network none \
      -v $PWD/scripts:/bench/scripts:ro -v $PWD/models:/bench/models:ro -v /tmp/stt_bench:/bench/audio \
      ltz2026-app python /bench/scripts/stt_bench.py --model /bench/models/whisper-large-v3-turbo --name turbo

Аудио синтезирует Piper тем же голосом, что озвучивает стенд: чисто и быстрее с шумом. Живой голос сложнее,
поэтому цифры сравнивают модели между собой, а не обещают точность на любом микрофоне.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import resource
import time
import wave

import numpy as np

from dxaqc import voice

PHRASES = [
    ("Покажи третий поясничный позвонок", r"(трет\w*|3 й|l ?3) поясничн"),
    ("Где двенадцатый грудной позвонок?", r"(двенадцат\w*|12 й) грудн|th ?12"),
    ("Какой наклон оси позвоночника?", r"накл\w*.*ос"),
    ("Видны ли гребни подвздошных костей?", r"подвздошн"),
    ("Есть ли на снимке посторонние предметы?", r"посторонн"),
    ("Покажи большой вертел", r"вертел"),
    ("Где шейка бедра?", r"шейк\w* бедр"),
    ("Почему у снимка нарушение?", r"нарушен"),
    ("Расскажи про пятый поясничный позвонок", r"пят\w* поясничн"),
    ("Покажи диафиз бедренной кости", r"диафиз"),
]
VARIANTS = [("clean", 1.0, None), ("fast_noise", 0.85, 12.0)]


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(ref: str, hyp: str) -> float:
    a, b = norm(ref), norm(hyp)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


def synth(text: str, scale: float, snr: float | None, path: str):
    if os.path.exists(path):
        return
    from piper import PiperVoice
    v = synth.voice = getattr(synth, "voice", None) or PiperVoice.load(voice.TTS_MODEL)
    tmp = path + ".raw.wav"
    with wave.open(tmp, "wb") as w:
        try:
            from piper import SynthesisConfig
            v.synthesize_wav(voice.speech_text(text), w, syn_config=SynthesisConfig(length_scale=scale))
        except ImportError:
            v.synthesize_wav(voice.speech_text(text), w)
    with wave.open(tmp, "rb") as r:
        params, frames = r.getparams(), r.readframes(r.getnframes())
    x = np.frombuffer(frames, np.int16).astype(np.float32)
    if snr is not None:
        rng = np.random.default_rng(20260915)
        noise = rng.normal(0, np.sqrt(np.mean(x ** 2) / 10 ** (snr / 10)), x.shape)
        x = np.clip(x + noise, -32768, 32767)
    x = np.concatenate([np.zeros(int(params.framerate * 0.4)), x, np.zeros(int(params.framerate * 0.6))])  # паузы, как у живой записи
    with wave.open(path, "wb") as w:
        w.setparams(params)
        w.writeframes(x.astype(np.int16).tobytes())
    os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--audio", default="/bench/audio")
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()
    os.makedirs(a.audio, exist_ok=True)
    clips = []
    for vi, (vname, scale, snr) in enumerate(VARIANTS):
        for pi, (text, key) in enumerate(PHRASES):
            path = os.path.join(a.audio, f"{vname}_{pi:02d}.wav")
            synth(text, scale, snr, path)
            clips.append((vname, text, key, path))

    from faster_whisper import WhisperModel
    t0 = time.perf_counter()
    model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=a.threads)
    load_s = time.perf_counter() - t0
    results, times = [], []
    for vname, text, key, path in clips:
        t = time.perf_counter()
        segs, _ = model.transcribe(path, language="ru", beam_size=1, vad_filter=True,
                                   initial_prompt=voice.PROMPT, condition_on_previous_text=False)
        hyp = " ".join(s.text.strip() for s in segs).strip()
        dt = time.perf_counter() - t
        times.append(dt)
        results.append(dict(variant=vname, ref=text, hyp=hyp, cer=round(cer(text, hyp), 3),
                            key=bool(re.search(key, norm(hyp))), sec=round(dt, 2)))
        print(f"{a.name:6s} {vname:10s} {dt:5.1f}s  cer={results[-1]['cer']:.2f} key={results[-1]['key']!s:5s} {hyp}", flush=True)
    warm = times[1:]
    summary = dict(
        name=a.name, load_s=round(load_s, 1), first_s=round(times[0], 1),
        mean_s=round(sum(warm) / len(warm), 2), p90_s=round(sorted(warm)[int(len(warm) * 0.9) - 1], 2),
        cer_clean=round(np.mean([r["cer"] for r in results if r["variant"] == "clean"]), 3),
        cer_noise=round(np.mean([r["cer"] for r in results if r["variant"] != "clean"]), 3),
        key_hits=f"{sum(r['key'] for r in results)}/{len(results)}",
        max_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    )
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    with open(os.path.join(a.audio, f"result_{a.name}.json"), "w", encoding="utf-8") as f:
        json.dump(dict(summary=summary, results=results), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
