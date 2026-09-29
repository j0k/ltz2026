# -*- coding: utf-8 -*-
"""Дообучение Kostik на снимках, размеченных врачом, — через плагины.

Источник новых знаний — правки вердикта в пульте (out/overrides.json каждой проверки): врач указал «качественный»
или «есть нарушение» и какие именно. Сами по себе новые снимки ничему не учат: нужна метка человека.

Плагин (класс Learner) отвечает за одну модель или набор порогов и проходит одинаковый цикл:

    collect  — собрать обучающие примеры: базовый набор организатора + правки врачей (правка важнее);
    train    — обучить кандидата;
    evaluate — честно оценить кандидата кросс-валидацией по исследованиям;
    accept   — ворота качества: кандидат не хуже действующей версии (с допуском на шум);
    install  — установить новую версию; прежние версии остаются, откат одной командой.

Встроенные плагины: hip_trees (модель бедра ExtraTrees) и spine_thresholds (пороги проверок позвоночника).
Сторонние плагины — файлы *.py в папке DXAQC_PLUGINS (по умолчанию <DXAQC_DATA>/plugins), где объявлен класс-
наследник Learner с декоратором @register. Запуск: python -m dxaqc.learning …, в пульте — кнопка для админа.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass, field

DATA = "/data"  # как у веб-сервиса; переопределяется DXAQC_DATA
REGISTRY: dict[str, type] = {}
_lock = threading.Lock()


def home() -> str:
    return os.path.join(os.environ.get("DXAQC_DATA", DATA), "learning")


def plugins_dir() -> str:
    return os.environ.get("DXAQC_PLUGINS") or os.path.join(os.environ.get("DXAQC_DATA", DATA), "plugins")


# ------------------------------------------------------------------ плагины

def register(cls):
    """Декоратор: добавить плагин в реестр по его name."""
    REGISTRY[cls.name] = cls
    return cls


@dataclass
class Sample:
    """Обучающий пример: снимок, область и метка. source — «организатор» или «врач <логин>»."""
    key: str
    sha: str
    study: str
    region: str
    bad: int
    types: list = field(default_factory=list)
    pixels: object = None
    source: str = ""


@dataclass
class Result:
    plugin: str
    ok: bool
    message: str
    metrics: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    installed: str = ""
    samples: int = 0
    feedback: int = 0


class Learner:
    """Базовый класс плагина. Переопределите regions, train, evaluate и install; остальное — общее."""
    name = "base"
    title = "плагин"
    regions: tuple = ()
    min_feedback = 1            # сколько правок врачей нужно, чтобы запуск имел смысл
    tolerance = 0.02            # допуск ворот качества: кандидат может быть хуже действующей версии не больше чем на это

    def available(self) -> tuple[bool, str]:
        return True, ""

    def collect(self, base: list[Sample], feedback: list[Sample]) -> list[Sample]:
        """Базовые примеры своей области + правки врачей; одинаковый снимок (sha) — берём правку врача."""
        mine = [s for s in base if s.region in self.regions]
        fb = {s.sha: s for s in feedback if s.region in self.regions}
        return [fb.pop(s.sha, s) for s in mine] + list(fb.values())

    def train(self, samples: list[Sample]):
        raise NotImplementedError

    def evaluate(self, candidate, samples: list[Sample]) -> dict:
        raise NotImplementedError

    def baseline(self) -> dict:
        """Метрики действующей версии в тех же единицах, что evaluate(); по умолчанию — из установленной версии."""
        act = self.active()
        return dict(act.get("metrics") or {}) if act else {}

    def score(self, metrics: dict) -> float:
        """Одно число для ворот качества."""
        return float(metrics.get("score", 0.0))

    def accept(self, metrics: dict, baseline: dict) -> tuple[bool, str]:
        if not baseline:
            return True, "действующей версии с метриками нет — принимаем"
        new, old = self.score(metrics), self.score(baseline)
        if new + self.tolerance >= old:
            return True, f"качество {new:.3f} против {old:.3f} — не хуже (допуск {self.tolerance})"
        return False, f"качество {new:.3f} хуже действующего {old:.3f} больше допуска {self.tolerance} — версия не установлена"

    def install(self, candidate, metrics: dict, version_dir: str) -> str:
        raise NotImplementedError

    # общее для всех плагинов: папки версий и активной версии
    def dir(self) -> str:
        return os.path.join(home(), self.name)

    def active(self) -> dict | None:
        p = os.path.join(self.dir(), "active.json")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)


def load_external() -> list[str]:
    """Подключить сторонние плагины из plugins_dir(): каждый *.py импортируется, @register добавляет классы."""
    loaded = []
    for path in sorted(glob.glob(os.path.join(plugins_dir(), "*.py"))):
        name = "kostik_plugin_" + os.path.splitext(os.path.basename(path))[0]
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for obj in vars(mod).values():               # наследники Learner регистрируются и без декоратора
                if isinstance(obj, type) and obj.__name__ != "Learner" and \
                        any(b.__name__ == "Learner" for b in obj.__mro__[1:]) and getattr(obj, "name", ""):
                    REGISTRY[obj.name] = obj
            loaded.append(os.path.basename(path))
        except Exception as exc:  # noqa: BLE001 — сломанный плагин не мешает остальным
            loaded.append(f"{os.path.basename(path)}: ошибка {type(exc).__name__}: {exc}")
    return loaded


def plugins() -> dict[str, "Learner"]:
    from dxaqc.learning import hip, spine  # встроенные плагины; регистрируем явно — модуль мог быть перезагружен
    register(hip.HipTrees)
    register(spine.SpineThresholds)
    load_external()
    return {k: v() for k, v in sorted(REGISTRY.items())}


# ------------------------------------------------------------------ данные: правки врачей и базовый набор

def runs_dir() -> str:
    return os.path.join(os.environ.get("DXAQC_DATA", DATA), "runs")


def feedback(runs: str | None = None, with_pixels: bool = True) -> list[Sample]:
    """Правки вердикта врачами из всех проверок: снимок, область и метка. Исключённые из проверки снимки не берём."""
    from dxaqc import io as dio
    out = []
    for ov_path in sorted(glob.glob(os.path.join(runs or runs_dir(), "*", "out", "overrides.json"))):
        out_dir = os.path.dirname(ov_path)
        run_dir = os.path.dirname(out_dir)
        try:
            with open(ov_path, encoding="utf-8") as f:
                ov = json.load(f)
            with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as f:
                man = json.load(f)
        except (OSError, ValueError):
            continue
        rows = {r.get("key"): r for r in man.get("rows", []) if r.get("key")}
        for key, o in ov.items():
            r = rows.get(key)
            if not r or o.get("excluded") or o.get("quality_class") not in (0, 1) or r.get("processing_status") != "Success":
                continue
            region = r.get("anatomical_region")
            if region not in ("lumbar_spine", "hip_left", "hip_right"):
                continue
            pixels, sha = None, key
            if with_pixels:
                src = os.path.join(run_dir, "input", r["path_to_study"])
                img = dio.load_image(src, os.path.join(run_dir, "input")) if os.path.isfile(src) else None
                if img is None or not hasattr(img, "pixels"):
                    continue
                pixels, sha = img.pixels, img.sha
            out.append(Sample(key=key, sha=sha, study=r.get("study_uid") or os.path.basename(run_dir), region=region,
                              bad=int(o["quality_class"]), types=list(o.get("violations") or []), pixels=pixels,
                              source=f"врач {o.get('by', '')}".strip()))
    return out


def base_samples() -> list[Sample]:
    """Обучающий набор организатора с оценками экспертов (если подключён, DXAQC_DATASETS/train)."""
    from dxaqc import analyze as AN, datasets, io as dio
    root = os.path.join(datasets.ROOT, "train")
    labels = datasets.load_labels("train")
    if not os.path.isdir(root) or not labels:
        return []
    images, _, _ = dio.collect(root)
    out = []
    for img in images:
        region = AN.detect_region(img.pixels)[0]
        study = img.rel_path.split(os.sep)[0]
        e = datasets.expert_for(labels, study, region)
        if e is None or e.get("bad") not in (0, 1):
            continue
        out.append(Sample(key=img.sha[:12], sha=img.sha, study=study, region=region, bad=int(e["bad"]),
                          types=list(e.get("types") or []), pixels=img.pixels, source="организатор"))
    return out


# ------------------------------------------------------------------ запуск

def _history(entry: dict):
    os.makedirs(home(), exist_ok=True)
    with open(os.path.join(home(), "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def history(limit: int = 50) -> list[dict]:
    p = os.path.join(home(), "history.jsonl")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        rows = [json.loads(x) for x in f if x.strip()]
    return rows[-limit:][::-1]


def run(names: list[str] | None = None, dry_run: bool = False, force: bool = False, by: str = "",
        base: list[Sample] | None = None, fb: list[Sample] | None = None, progress=None) -> list[Result]:
    """Цикл дообучения для выбранных плагинов (по умолчанию — всех). dry_run — оценить без установки;
    force — запустить, даже если правок врачей меньше min_feedback."""
    with _lock:
        pl = plugins()
        chosen = [pl[n] for n in (names or list(pl)) if n in pl]
        say = progress or (lambda *_: None)
        say("сбор правок врачей")
        fb = feedback() if fb is None else fb
        base = None if base is None else base
        results = []
        for p in chosen:
            ok, why = p.available()
            if not ok:
                results.append(Result(p.name, False, f"плагин недоступен: {why}"))
                continue
            mine_fb = [s for s in fb if s.region in p.regions]
            if len(mine_fb) < p.min_feedback and not force:
                results.append(Result(p.name, False, f"новых правок врачей для этого плагина {len(mine_fb)}, нужно не меньше "
                                                      f"{p.min_feedback} — дообучение не требуется", feedback=len(mine_fb)))
                continue
            if base is None:
                say("чтение базового набора")
                base = base_samples()
            samples = p.collect(base, fb)
            say(f"{p.name}: обучение на {len(samples)} примерах")
            t0 = time.time()
            cand = p.train(samples)
            metrics = p.evaluate(cand, samples)
            bl = p.baseline()
            accepted, msg = p.accept(metrics, bl)
            res = Result(p.name, accepted, msg, metrics=metrics, baseline=bl, samples=len(samples), feedback=len(mine_fb))
            if accepted and not dry_run:
                ver = time.strftime("%Y%m%d-%H%M%S")
                vdir = os.path.join(p.dir(), "versions", ver)
                os.makedirs(vdir, exist_ok=True)
                res.installed = p.install(cand, metrics, vdir)
                info = dict(version=ver, path=res.installed, metrics=metrics, samples=len(samples), feedback=len(mine_fb), by=by, at=time.time())
                with open(os.path.join(vdir, "info.json"), "w", encoding="utf-8") as f:
                    json.dump(info, f, ensure_ascii=False, indent=1)
                with open(os.path.join(p.dir(), "active.json"), "w", encoding="utf-8") as f:
                    json.dump(info, f, ensure_ascii=False, indent=1)
                res.message += f"; установлена версия {ver}"
            elif accepted:
                res.message += "; пробный запуск — не установлено"
            _history(dict(at=time.time(), by=by, plugin=p.name, ok=res.ok, installed=bool(res.installed), message=res.message,
                          metrics=metrics, baseline=bl, samples=len(samples), feedback=len(mine_fb), seconds=round(time.time() - t0, 1),
                          dry_run=dry_run))
            results.append(res)
        return results


def rollback(name: str, version: str | None = None) -> str:
    """Вернуть предыдущую (или указанную) версию плагина; без версий — вернуться к встроенной модели."""
    p = plugins()[name]
    vroot = os.path.join(p.dir(), "versions")
    versions = sorted(os.listdir(vroot)) if os.path.isdir(vroot) else []
    act = p.active()
    if version is None:
        cur = act.get("version") if act else None
        older = [v for v in versions if cur is None or v < cur]
        version = older[-1] if older else None
    if version is None:
        if os.path.exists(os.path.join(p.dir(), "active.json")):
            os.remove(os.path.join(p.dir(), "active.json"))
        _history(dict(at=time.time(), plugin=name, ok=True, installed=False, message="откат к встроенной версии"))
        return "встроенная версия"
    shutil.copyfile(os.path.join(vroot, version, "info.json"), os.path.join(p.dir(), "active.json"))
    _history(dict(at=time.time(), plugin=name, ok=True, installed=True, message=f"откат к версии {version}"))
    return version


def status() -> dict:
    pl = plugins()
    fb = feedback(with_pixels=False)
    out = dict(plugins=[], feedback=len(fb), plugins_dir=plugins_dir(), history=history(10))
    for name, p in pl.items():
        ok, why = p.available()
        act = p.active()
        out["plugins"].append(dict(name=name, title=p.title, regions=list(p.regions), available=ok, why=why,
                                   feedback=sum(1 for s in fb if s.region in p.regions), min_feedback=p.min_feedback,
                                   active=act.get("version") if act else "встроенная", metrics=(act or {}).get("metrics") or p.baseline()))
    return out
