# -*- coding: utf-8 -*-
"""Графики к scripts/learning_curves.py: квадрат ошибки (Brier) от объёма данных и от числа деревьев.

    ../.venv-ml/bin/python scripts/plot_learning_curves.py <curves.json> <out_dir>
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

d = json.load(open(sys.argv[1])); out = sys.argv[2]
TRAIN, VAL, CONST = "#2a78d6", "#eb6834", "#8a8983"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e4df", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titleweight": "bold", "axes.titlesize": 12.5,
                     "axes.titlecolor": INK, "figure.facecolor": SURF, "axes.facecolor": SURF})


def style(ax):
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylim(bottom=0)


def panel(ax, v, key, xs, xlab, logx=False):
    series = v[key]
    x = [float(k) * (100 if key == "size" else 1) for k in series]
    tr = [series[k]["train"][0] for k in series]; va = [series[k]["val"][0] for k in series]
    lo = [series[k]["val"][1] for k in series]; hi = [series[k]["val"][2] for k in series]
    ax.fill_between(x, lo, hi, color=VAL, alpha=0.12, lw=0)
    ax.plot(x, tr, color=TRAIN, lw=2, marker="o", ms=4.5, label="обучение")
    ax.plot(x, va, color=VAL, lw=2, marker="o", ms=4.5, label="проверка вне фолда")
    const = v["size"]["1.0"]["const"][0]
    ax.axhline(const, color=CONST, lw=1.4, ls=(0, (4, 3)), label="константа (доля брака)")
    ax.annotate(f"{va[-1]:.3f}".replace(".", ","), (x[-1], va[-1]), xytext=(6, 4), textcoords="offset points", color=INK, fontsize=10)
    ax.annotate(f"{tr[-1]:.3f}".replace(".", ","), (x[-1], tr[-1]), xytext=(6, -12), textcoords="offset points", color=INK, fontsize=10)
    if logx:
        ax.set_xscale("log"); ax.set_xticks([1, 2, 5, 10, 20, 50, 100, 200]); ax.set_xticklabels(["1", "2", "5", "10", "20", "50", "100", "200"])
    ax.set_title(v["title"], loc="left", pad=20)
    short = "правило" if v["model"].startswith("правило") else v["model"]
    ax.text(0, 1.015, f"{short} · {v['n']} снимков, брак {v['positives']}", transform=ax.transAxes, fontsize=10, color=INK2)
    ax.set_xlabel(xlab); style(ax)
    ax.set_ylim(top=max(max(tr), max(hi), const) * 1.18)


order = ["overall", "coverage", "axis_tilt", "artifact", "hip_bad", "hip_positioning", "hip_roi"]
fig, axes = plt.subplots(2, 4, figsize=(17, 8.6))
for ax, k in zip(axes.flat, order):
    panel(ax, d[k], "size", None, "доля обучающих исследований, %")
    ax.set_ylabel("Brier, (p − y)²") if ax in (axes[0, 0], axes[1, 0]) else None
axn = axes[1, 3]; axn.axis("off")
h, l = axes[0, 0].get_legend_handles_labels()
axn.legend(h, l, loc="upper left", frameon=False, fontsize=11.5)
axn.text(0, 0.52, "Квадрат ошибки вероятности брака против\nоценки экспертов. Проверка — 5 фолдов по\nисследованиям × 10 повторов, полоса —\n10–90% повторов. Ниже константы — модель\nдаёт информацию; большой зазор с обучением —\nпереобучение. Шкалы Y у панелей разные.",
         va="top", fontsize=10.5, color=INK2, transform=axn.transAxes)
fig.suptitle("Квадрат ошибки во время обучения: от объёма данных · DXA QC 0.5.4", x=0.01, ha="left", fontsize=15, fontweight="bold", color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.96)); fig.savefig(os.path.join(out, "brier_by_data.png"), dpi=110)

fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
for ax, k in zip(axes, ["hip_bad", "hip_positioning", "hip_roi"]):
    panel(ax, d[k], "trees", None, "число деревьев в лесу", logx=True)
axes[0].set_ylabel("Brier, (p − y)²"); axes[0].legend(frameon=False, loc="upper right")
fig.suptitle("Квадрат ошибки по мере добавления деревьев · бедро, ExtraTrees", x=0.01, ha="left", fontsize=15, fontweight="bold", color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.93)); fig.savefig(os.path.join(out, "brier_by_trees.png"), dpi=110)
print("ok")
