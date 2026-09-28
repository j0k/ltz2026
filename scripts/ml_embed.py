# -*- coding: utf-8 -*-
"""Эмбеддинги предобученных сетей для снимков обучающего набора (исследование 26.09, п.2 и п.3 плана).

Запускается в исследовательской среде с PyTorch (.venv-ml рядом с репозиторием), снимки не покидают сервер,
модели только скачиваются. Результат — data/_ml/emb_<модель>.npz (вне репозитория).

    DXAQC_DATASETS=<папка наборов> ../.venv-ml/bin/python scripts/ml_embed.py [модель ...]
"""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from dxaqc import analyze as AN, datasets
from dxaqc import io as dio

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "_ml")
MODELS = {
    "resnet50": dict(kind="tv", size=224),
    "dinov2-small": dict(kind="hf", repo="facebook/dinov2-small", size=224),
    "dinov2-base": dict(kind="hf", repo="facebook/dinov2-base", size=224),
    "rad-dino": dict(kind="hf", repo="microsoft/rad-dino", size=518),
}


def images():
    root = os.path.join(datasets.ROOT, "train"); labels = datasets.load_labels("train")
    imgs, _, _ = dio.collect(root)
    out = []
    for img in imgs:
        reg = AN.detect_region(img.pixels)[0]
        study = img.rel_path.split(os.sep)[0]
        a = img.pixels[:, ::-1] if reg == "hip_left" else img.pixels        # таз всегда справа
        out.append(dict(key=img.sha[:12], sha=img.sha, study=study, region=reg,
                        expert=datasets.expert_for(labels, study, reg), pixels=np.ascontiguousarray(a)))
    return out


def square(a, size):
    """Кадр в квадрат с чёрными полями без искажения пропорций, затем к размеру сети."""
    h, w = a.shape
    s = max(h, w)
    canvas = np.zeros((s, s), np.uint8)
    canvas[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = a
    return Image.fromarray(canvas).resize((size, size), Image.BICUBIC).convert("RGB")


def embed(name, recs):
    import torch
    cfg = MODELS[name]
    torch.set_num_threads(2)
    if cfg["kind"] == "tv":
        import torchvision
        m = torchvision.models.resnet50(weights="IMAGENET1K_V2"); m.fc = torch.nn.Identity(); m.eval()
        mean, std = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])
        prep = lambda im: torch.tensor(((np.asarray(im, np.float32) / 255 - mean) / std).transpose(2, 0, 1), dtype=torch.float32)
        run = lambda x: m(x)
    else:
        from transformers import AutoImageProcessor, AutoModel
        proc = AutoImageProcessor.from_pretrained(cfg["repo"]); m = AutoModel.from_pretrained(cfg["repo"]).eval()
        mean, std = np.array(proc.image_mean), np.array(proc.image_std)
        prep = lambda im: torch.tensor(((np.asarray(im, np.float32) / 255 - mean) / std).transpose(2, 0, 1), dtype=torch.float32)
        def run(x):
            o = m(pixel_values=x).last_hidden_state
            return torch.cat([o[:, 0], o[:, 1:].mean(1)], dim=1)          # CLS и среднее по патчам
    # по частям: DXAQC_EMB_SECONDS — сколько считать за запуск; сделанное — в emb_<name>.part.npz, следующий запуск продолжит
    part = os.path.join(OUT, f"emb_{name}.part.npz")
    vecs = [np.load(part)["emb"]] if os.path.isfile(part) else []
    start = sum(len(v) for v in vecs)
    budget = float(os.environ.get("DXAQC_EMB_SECONDS", "1e9"))
    t0 = time.time()
    with torch.no_grad():
        for i in range(start, len(recs), 8):
            x = torch.stack([prep(square(r["pixels"], cfg["size"])) for r in recs[i:i + 8]])
            vecs.append(run(x).numpy())
            if time.time() - t0 > budget and i + 8 < len(recs):
                np.savez(part, emb=np.concatenate(vecs))
                print(f"{name}: {i + 8} из {len(recs)} за {time.time() - t0:.0f} с — продолжение следующим запуском", flush=True)
                return None
    V = np.concatenate(vecs)
    if os.path.isfile(part):
        os.remove(part)
    print(f"{name}: {V.shape} за {time.time() - t0:.0f} с", flush=True)
    return V


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    recs = images()
    meta = os.path.join(OUT, "meta.npz")
    np.savez(meta, key=[r["key"] for r in recs], sha=[r["sha"] for r in recs], study=[r["study"] for r in recs],
             region=[r["region"] for r in recs],
             bad=[-1 if not r["expert"] else int(r["expert"]["bad"] == 1) for r in recs],
             types=np.array(["|".join(r["expert"]["types"]) if r["expert"] else "" for r in recs], dtype=object))
    for name in sys.argv[1:] or list(MODELS):
        path = os.path.join(OUT, f"emb_{name}.npz")
        if os.path.isfile(path):
            print(f"{name}: уже есть"); continue
        V = embed(name, recs)
        if V is not None:
            np.savez(path, emb=V)
