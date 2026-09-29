# -*- coding: utf-8 -*-
"""Таблица меток для обучения и оценки из разметки организатора (лист «Калибровка» файла разметка.xlsx).

Строка на исследование: study (StudyInstanceUID = имя папки в «Исследования»), оценки экспертов 0/1 по критериям —
sp_pos, sp_axis, sp_art (позвоночник: укладка/охват, ось, посторонние предметы), rh_pos, rh_roi, lh_pos, lh_roi
(правое и левое бедро: позиционирование/ротация, область интереса), итоги sp_bad, rh_bad, lh_bad и комментарий.
Пустая ячейка — области нет в исследовании. Дополнительно: files — файлов DICOM в папке исследования,
regions — сколько областей оценено.

    .venv/bin/python scripts/make_labels.py <папка набора с разметка.xlsx и «Исследования»> <выход.csv>
"""
import csv
import os
import sys

import openpyxl

FIELDS = ["sp_pos", "sp_axis", "sp_art", "rh_pos", "rh_roi", "lh_pos", "lh_roi", "sp_bad", "rh_bad", "lh_bad"]


def num(v):
    if v is None or str(v).strip() == "":
        return ""
    return f"{float(v):.1f}"


def main(src: str, out: str):
    ws = openpyxl.load_workbook(os.path.join(src, "разметка.xlsx"), read_only=True, data_only=True)["Калибровка"]
    studies = os.path.join(src, "Исследования")
    rows = []
    for r in ws.iter_rows(min_row=3, values_only=True):
        if not r or r[1] is None:
            continue
        study = str(r[1]).strip()
        vals = [num(v) for v in r[2:12]]
        folder = os.path.join(studies, study)
        files = sum(len(fs) for _, _, fs in os.walk(folder)) if os.path.isdir(folder) else 0
        regions = sum(1 for v in vals[7:10] if v != "")
        rows.append([r[0], study, *vals, (r[12] or "").strip() if isinstance(r[12], str) else (r[12] or ""), files, regions])
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "study", *FIELDS, "comment", "files", "regions"])
        w.writerows(rows)
    print(f"исследований: {len(rows)} → {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
