# -*- coding: utf-8 -*-
"""Пакетная обработка: папка с исследованиями -> таблица по ТЗ, картинки разметки, manifest для веба.

Колонки таблицы по разделу 2.5 ТЗ: path_to_study, study_uid, image_uid, anatomical_region,
quality_class, violation_type, processing_status, time_of_processing.

Параметры анализа (пороги) сохраняются в manifest. Правки снимков из пульта хранятся в out/overrides.json и
применяются apply_overrides(): автоматический результат остаётся в row["auto"], в таблицах — итог с правкой,
исключённые снимки в таблицы и сводку не попадают, оценка против экспертов считается по автоматическим вердиктам.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import zipfile

from dxaqc import __version__, analyze, atlas, datasets, render
from dxaqc import params as P
from dxaqc.io import collect

COLUMNS = ["path_to_study", "study_uid", "image_uid", "anatomical_region",
           "quality_class", "violation_type", "processing_status", "time_of_processing"]
# коды нарушений, которые можно поставить правкой вручную
OVERRIDE_CODES = ["axis_tilt", "coverage", "artifact", "hip_positioning", "hip_roi", "other"]
PARTIAL = "partial.jsonl"  # строки снимков по мере анализа, удаляется после manifest.json


class Cancelled(Exception):
    """Прогон отменён из пульта."""


def _row_for_table(r: dict) -> list:
    q = r.get("quality_class")
    return [r["path_to_study"], r["study_uid"], r["image_uid"], r["anatomical_region"],
            "" if q is None else int(q), r["violation_type"], r["processing_status"], round(r["time_of_processing"], 3)]


def _write_tables(rows: list[dict], out_dir: str):
    with open(os.path.join(out_dir, "results.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(_row_for_table(r))
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "results"
        ws.append(COLUMNS)
        for r in rows:
            ws.append(_row_for_table(r))
        wb.save(os.path.join(out_dir, "results.xlsx"))
    except Exception as exc:  # xlsx необязателен, csv есть всегда
        print(f"[pipeline] xlsx не записан: {exc}", file=sys.stderr)


def _confusion(pairs):
    tp = sum(1 for p, y in pairs if p and y)
    fp = sum(1 for p, y in pairs if p and not y)
    fn = sum(1 for p, y in pairs if not p and y)
    tn = sum(1 for p, y in pairs if not p and not y)
    sens = tp / (tp + fn) if tp + fn else None
    spec = tn / (tn + fp) if tn + fp else None
    prec = tp / (tp + fp) if tp + fp else None
    f1 = (2 * prec * sens / (prec + sens)) if prec and sens else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, n=len(pairs), sensitivity=sens, specificity=spec, f1=f1)


def evaluate(rows: list[dict]) -> dict:
    """Сравнение с экспертами на уровне исследования: метки даны на исследование и область."""
    spine = {}
    for r in rows:
        if r.get("processing_status") != "Success" or r.get("anatomical_region") != "lumbar_spine" or not r.get("expert"):
            continue
        st = spine.setdefault(r["study_key"], dict(pred=set(), bad=False, exp=r["expert"]))
        st["pred"].update(r.get("violation_list") or [])
        st["bad"] = st["bad"] or r.get("quality_class") == 1
    out = dict(level="study", spine_studies=len(spine))
    out["spine_overall"] = _confusion([(v["bad"], v["exp"]["bad"] == 1) for v in spine.values()])
    for code in ("coverage", "axis_tilt", "artifact"):
        out[f"spine_{code}"] = _confusion([(code in v["pred"], code in v["exp"]["types"]) for v in spine.values()])
    hips = [r for r in rows if r.get("anatomical_region", "").startswith("hip") and r.get("expert")]
    out["hip_expert_bad"] = sum(1 for r in hips if r["expert"]["bad"] == 1)
    out["hip_expert_total"] = len(hips)
    return out


def _summary(rows: list[dict], duplicates: int, wall_time: float) -> dict:
    ok = [r for r in rows if r["processing_status"] == "Success"]
    return dict(
        images=len(ok),
        good=sum(1 for r in ok if r["quality_class"] == 0),
        bad=sum(1 for r in ok if r["quality_class"] == 1),
        not_evaluated=sum(1 for r in ok if r["quality_class"] is None),
        failures=len(rows) - len(ok),
        duplicates=duplicates,
        studies=len({r["study_uid"] for r in ok}),
        mean_time=(sum(r["time_of_processing"] for r in ok) / len(ok)) if ok else 0.0,
        wall_time=wall_time,
    )


def analyze_image(pixels, params: dict | None = None) -> tuple[dict, dict | None]:
    """Анализ и атлас одного снимка: (результат анализа, атлас или None). Атлас не роняет анализ."""
    res = analyze.analyze(pixels, params)
    try:
        art = atlas.render(pixels, res)
    except Exception as exc:
        print(f"[pipeline] атлас не построен: {exc}", file=sys.stderr)
        art = None
    return res, art


def run_batch(input_dir: str, out_dir: str, labels: dict | None = None, dataset: str | None = None,
              params: dict | None = None, progress=None, should_stop=None, force: bool = False) -> dict:
    """progress(этап, сделано, всего, деталь, last=..., tally=...) сообщает о ходе прогона: этапы read, analyze, tables,
    evaluate; should_stop() -> True прерывает прогон исключением Cancelled."""
    os.makedirs(out_dir, exist_ok=True)
    started = time.time()
    p = P.normalize(params)
    emit = progress or (lambda *a, **k: None)
    emit("read", 0, 0, "")
    images, failures, dups = collect(input_dir, on_file=lambda done, total, rel: emit("read", done, total, rel), force=force)
    rows = []
    tally = dict(good=0, bad=0, na=0, failed=0)
    # строки по мере анализа: страница идущего прогона открывает результат снимка, не дожидаясь manifest.json
    partial = os.path.join(out_dir, PARTIAL)
    if os.path.exists(partial):
        os.remove(partial)
    emit("analyze", 0, len(images), "")

    for i, img in enumerate(images):
        if should_stop and should_stop():
            raise Cancelled()
        t0 = time.perf_counter()
        key = img.sha[:12]
        study_key = img.rel_path.split(os.sep)[0] if os.sep in img.rel_path else img.study_uid
        base = dict(path_to_study=img.rel_path, study_uid=img.study_uid, image_uid=img.image_uid, key=key, study_key=study_key)
        try:
            orig_name, ov_name, th_name = f"{key}_original.png", f"{key}_overlay.png", f"{key}_thumb.png"
            hit_name = f"{key}_hit.png"
            render.original(img.pixels).save(os.path.join(out_dir, orig_name))
            res, art = analyze_image(img.pixels, p)
            layers = []
            if art:
                art["atlas"].save(os.path.join(out_dir, ov_name))
                art["thumb"].save(os.path.join(out_dir, th_name))
                art["hit"].save(os.path.join(out_dir, hit_name), optimize=True)
                # слой снимка — уже сохранённый original_png, остальные слои прозрачные, пустые не пишем
                layers.append(dict(name="image", file=orig_name, x=art["image_box"][0], y=art["image_box"][1]))
                for name, im in art["layers"].items():
                    layer_name = f"{key}_layer_{name}.png"
                    im.save(os.path.join(out_dir, layer_name), compress_level=6)
                    layers.append(dict(name=name, file=layer_name, x=0, y=0))
            else:
                simple = render.overlay(img.pixels, res)
                simple.save(os.path.join(out_dir, ov_name))
                simple.thumbnail((220, 220))
                simple.save(os.path.join(out_dir, th_name))
            codes = res["violations"]
            base.update(
                anatomical_region=res["region"],
                quality_class=res["quality_class"],
                violation_type=";".join(codes) if codes else "none",
                violation_list=[c for c in codes],
                processing_status="Success",
                explanations=res["explanations"],
                measurements=res["measurements"],
                metrics=res.get("metrics", {}),
                expert=datasets.expert_for(labels, study_key, res["region"]),
                original_png=orig_name,
                overlay_png=ov_name,
                thumb_png=th_name,
                atlas=bool(art),
                hit_png=hit_name if art else None,
                regions=art["regions"] if art else [],
                layers=layers,
                callouts=art.get("callouts") if art else None,   # подписи данными для компонента atlas-callouts
            )
        except Exception as exc:
            base.update(anatomical_region="unknown", quality_class=None, violation_type=f"error: {type(exc).__name__}",
                        violation_list=[], processing_status="Failure", explanations=[str(exc)[:300]], measurements={})
        if img.meta.get("forced"):   # принудительный анализ: пометка первой строкой пояснений, в метрики не входит
            base["forced"] = True
            base["explanations"] = [img.meta.get("forced_note", "Принудительный анализ.")] + list(base.get("explanations") or [])
        base["time_of_processing"] = time.perf_counter() - t0
        rows.append(base)
        with open(partial, "a", encoding="utf-8") as f:   # строка целиком за одну запись, читатель пропускает недописанную
            f.write(json.dumps(base, ensure_ascii=False, default=str) + "\n")
        q = base.get("quality_class")
        ok = base["processing_status"] == "Success"
        tally["failed" if not ok else "good" if q == 0 else "bad" if q == 1 else "na"] += 1
        emit("analyze", i + 1, len(images), img.rel_path, tally=dict(tally),
             last=dict(name=os.path.basename(img.rel_path), region=base.get("anatomical_region"), quality_class=q,
                       violations=base.get("violation_list") or [], key=key if ok else ""))

    for fl in failures:
        rows.append(dict(path_to_study=fl.rel_path, study_uid="", image_uid="", key="", anatomical_region="unknown",
                         quality_class=None, violation_type=f"error: {fl.error}"[:200], violation_list=[],
                         processing_status="Failure", time_of_processing=0.0, explanations=[fl.error], measurements={},
                         reject_code=fl.code, forceable=fl.forceable))

    rows.sort(key=lambda r: (r["processing_status"] != "Success", r["study_uid"], r["anatomical_region"], r["path_to_study"]))
    emit("tables", 0, 1, "results.csv, results.xlsx, overlays.zip")
    _write_tables(rows, out_dir)

    with zipfile.ZipFile(os.path.join(out_dir, "overlays.zip"), "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            if r.get("overlay_png"):
                zf.write(os.path.join(out_dir, r["overlay_png"]), f"{r['study_uid'] or 'study'}/{r['overlay_png']}")

    if labels:
        emit("evaluate", 0, 1, "метки экспертов на уровне исследования")
    manifest = dict(version=__version__, created=time.time(), summary=_summary(rows, dups, time.time() - started),
                    columns=COLUMNS, rows=rows, dataset=dataset, has_labels=bool(labels),
                    evaluation=evaluate(rows) if labels else None, axis_limit=p["axis_limit_deg"], params=p)
    # через временный файл: страница прогона и API читают manifest во время записи и не должны увидеть его обрезанным
    path = os.path.join(out_dir, "manifest.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
    try:  # после manifest.json промежуточные строки не нужны
        os.remove(partial)
    except OSError:
        pass
    return manifest


def apply_overrides(out_dir: str, overrides: dict) -> dict:
    """Применить правки снимков {key: {excluded, quality_class, violations, note, by, at}} к готовому прогону."""
    path = os.path.join(out_dir, "manifest.json")
    with open(path, encoding="utf-8") as f:
        man = json.load(f)
    auto_rows = []
    for r in man["rows"]:
        if r.get("key") and "auto" not in r:  # автоматический результат запоминаем один раз
            r["auto"] = dict(quality_class=r.get("quality_class"), violation_type=r.get("violation_type"),
                             violation_list=list(r.get("violation_list") or []))
        if r.get("auto"):
            r.update(quality_class=r["auto"]["quality_class"], violation_type=r["auto"]["violation_type"],
                     violation_list=list(r["auto"]["violation_list"]))
        auto_rows.append(dict(r))
        r.pop("override", None)
        r.pop("excluded", None)
        o = overrides.get(r.get("key") or "")
        if not o:
            continue
        r["override"] = o
        if o.get("excluded"):
            r["excluded"] = True
            continue
        if o.get("quality_class") in (0, 1):
            codes = [c for c in (o.get("violations") or []) if c in OVERRIDE_CODES] if o["quality_class"] == 1 else []
            r.update(quality_class=o["quality_class"], violation_list=codes,
                     violation_type=";".join(codes) if codes else ("none" if o["quality_class"] == 0 else "manual"))
    kept = [r for r in man["rows"] if not r.get("excluded")]
    _write_tables(kept, out_dir)
    summary = _summary(kept, man["summary"].get("duplicates", 0), man["summary"].get("wall_time", 0.0))
    summary["excluded"] = len(man["rows"]) - len(kept)
    summary["overridden"] = sum(1 for r in man["rows"] if r.get("override") and not r.get("excluded"))
    man["summary"] = summary
    if man.get("has_labels"):
        man["evaluation"] = evaluate(auto_rows)  # качество сервиса — по его собственным вердиктам, без правок
    man["overrides"] = len(overrides)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
    return man


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Пакетная проверка качества DXA: папка с DICOM -> results.csv")
    ap.add_argument("input_dir")
    ap.add_argument("out_dir")
    for s in P.SPEC:
        ap.add_argument("--" + s["name"].replace("_", "-"), dest=s["name"], default=None, help=s["help"])
    a = ap.parse_args(argv)
    m = run_batch(a.input_dir, a.out_dir, params={s["name"]: getattr(a, s["name"]) for s in P.SPEC})
    print(json.dumps(m["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
