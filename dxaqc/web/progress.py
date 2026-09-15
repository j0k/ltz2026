# -*- coding: utf-8 -*-
"""Этапы прогона и живой прогресс.

Tracker получает события пайплайна и пишет в status.json: этапы с временем начала и конца, текущий этап и его счётчик,
прогресс по снимкам, оценку оставшегося времени, счётчики вердиктов и последние обработанные снимки.
Запись не чаще раза в 0,3 секунды, смена этапа и конец этапа пишутся сразу.
"""
from __future__ import annotations

import time

STAGE_LABELS = {
    "received": "Файлы приняты",
    "unpack": "Распаковка архивов",
    "read": "Чтение DICOM и поиск дублей",
    "analyze": "Анализ снимков и разметка",
    "tables": "Таблицы и архив разметки",
    "evaluate": "Сравнение с экспертами",
    "done": "Готово",
}
# доля этапа в общем проценте: анализ снимков — основная работа
WEIGHTS = {"received": 2, "unpack": 6, "read": 14, "analyze": 68, "tables": 7, "evaluate": 3, "done": 0}


def stage_plan(has_archives: bool, has_labels: bool) -> list[dict]:
    keys = (["received"] + (["unpack"] if has_archives else []) + ["read", "analyze", "tables"]
            + (["evaluate"] if has_labels else []) + ["done"])
    return [dict(key=k, label=STAGE_LABELS[k], weight=WEIGHTS[k]) for k in keys]


class Tracker:
    MIN_INTERVAL = 0.3

    def __init__(self, write, stages: dict | None = None):
        self.write = write                      # write(**поля) — дописать поля в status.json
        self.stages = dict(stages or {})
        self.stage = None
        self.recent: list[dict] = []
        self.pending: dict = {}
        self.last = 0.0
        self.analyze_started = None

    def start(self, key: str, total: int = 0, detail: str = ""):
        now = time.time()
        if self.stage and self.stage != key:
            self.stages.setdefault(self.stage, {}).setdefault("end", now)
        self.stage = key
        self.stages.setdefault(key, {})["start"] = now
        if key == "analyze":
            self.analyze_started = now
        self._flush(True, stage=key, step={"done": 0, "total": total}, detail=detail)

    def __call__(self, stage: str, done: int = 0, total: int = 0, detail: str = "", last: dict | None = None,
                 tally: dict | None = None):
        if stage != self.stage:
            self.start(stage, total, detail)
        fields = dict(step={"done": done, "total": total}, detail=detail)
        if stage == "analyze":
            fields["progress"] = {"done": done, "total": total}
            if done and self.analyze_started:
                rate = done / max(time.time() - self.analyze_started, 1e-3)
                fields["eta"] = round((total - done) / rate, 1)
        if tally is not None:
            fields["tally"] = tally
        if last:
            self.recent = ([last] + self.recent)[:8]
            fields["recent"] = self.recent
        self._flush(total > 0 and done >= total, **fields)

    def finish(self):
        now = time.time()
        if self.stage:
            self.stages.setdefault(self.stage, {}).setdefault("end", now)
        self.stages["done"] = {"start": now, "end": now}
        self.stage = "done"
        self._flush(True, stage="done", eta=0, detail="")

    def _flush(self, force: bool = False, **fields):
        self.pending.update(fields)
        now = time.time()
        if not force and now - self.last < self.MIN_INTERVAL:
            return
        self.last = now
        self.write(stages=self.stages, **self.pending)
        self.pending = {}
