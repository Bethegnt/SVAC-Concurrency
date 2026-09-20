"""
svac_plot_results.py
=====================
Generates high-resolution, publication-quality figures from SVAC_Concurrency
evaluation score files. All labels, legends, and metric values are dynamically
placed with intelligent collision avoidance, clear typography, and generous
padding for standard IEEE two-column paper formatting.

Outputs four figures:
  Fig 1 — Step Accuracy and Verdict Accuracy by Task x Prompt Strategy
  Fig 2 — Complexity Scaling Law (accuracy vs. complexity level, per task)
  Fig 3 — Error Cascade Rate (ECR) heatmap, Task x Prompt Strategy
  Fig 4 — Cross-model comparison across all evaluated models

USAGE
-----
  python analysis/svac_plot_results.py
  python analysis/svac_plot_results.py --scores results/scores/<file>.json
  python analysis/svac_plot_results.py --scores <f1> --compare <f2> <f3> ...
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
except ImportError:
    sys.exit(
        "ERROR: matplotlib and numpy are required.\n"
        "  pip install matplotlib numpy --break-system-packages"
    )

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORES_DIR  = os.path.join(BASE_DIR, "results", "scores")
FIGURES_DIR = os.path.join(BASE_DIR, "analysis", "figures")

# ---------------------------------------------------------------------------
# Configuration (High DPI, Clean Typography, Generous Layout Bounds)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlotStyle:
    dpi:          int   = 300
    fig_w_dual:   float = 15.5
    fig_h_dual:   float = 5.8
    fig_w_heat:   float = 9.0
    fig_h_heat:   float = 5.5
    bar_alpha:    float = 0.88
    linewidth:    float = 2.4
    markersize:   float = 8.0
    font_axis:    int   = 12
    font_tick:    int   = 10
    font_legend:  int   = 10
    font_title:   int   = 13
    font_annot:   int   = 11
    grid_alpha:   float = 0.35
    grid_style:   str   = "--"


@dataclass(frozen=True)
class DisplayMaps:
    task_labels: Dict[str, str] = field(default_factory=lambda: {
        "wfg":       "WFG\nDeadlock",
        "bankers":   "Banker's\nAlgorithm",
        "buddy":     "Buddy\nSystem",
        "semaphore": "Semaphore\nSync",
        "mutex":     "Mutex\nLock",
    })
    variant_labels: Dict[str, str] = field(default_factory=lambda: {
        "zero_shot": "Zero-Shot",
        "few_shot":  "Few-Shot",
        "cot":       "Chain-of-Thought",
    })
    variant_colors: Dict[str, str] = field(default_factory=lambda: {
        "zero_shot": "#386CB0",
        "few_shot":  "#FDB462",
        "cot":       "#7FC97F",
    })
    task_colors: Dict[str, str] = field(default_factory=lambda: {
        "wfg":       "#1F77B4",
        "bankers":   "#FF7F0E",
        "buddy":     "#2CA02C",
        "semaphore": "#D62728",
        "mutex":     "#9467BD",
    })
    model_colors: List[str] = field(default_factory=lambda: [
        "#1F77B4", "#2CA02C", "#FF7F0E", "#D62728", "#9467BD", "#8C564B",
    ])


STYLE = PlotStyle()
MAPS  = DisplayMaps()

# Preferred display ordering for tasks / variants
_TASK_PREF    = ["wfg", "bankers", "buddy", "semaphore", "mutex"]
_VARIANT_PREF = ["zero_shot", "few_shot", "cot"]

# ---------------------------------------------------------------------------
# Matplotlib global settings
# ---------------------------------------------------------------------------

def _apply_rc() -> None:
    plt.rcParams.update({
        "font.family":        "DejaVu Sans",
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.grid":          True,
        "grid.alpha":         STYLE.grid_alpha,
        "grid.linestyle":     STYLE.grid_style,
        "axes.axisbelow":     True,
    })

# ---------------------------------------------------------------------------
# I/O & Formatting helpers
# ---------------------------------------------------------------------------

def load_scores(path: str) -> List[Dict]:
    with open(path) as fh:
        return json.load(fh)


def infer_model_name(path: str) -> str:
    return os.path.basename(path).rsplit("_", 2)[0]


def format_model_label(raw_name: str) -> str:
    """Produces clean, professional display titles for models."""
    s = raw_name.lower()
    if "3-1-flash-lite" in s:
        return "Gemini-3.1 Flash Lite"
    elif "3-5-flash-lite" in s:
        return "Gemini-3.5 Flash Lite"
    elif "3-5-flash" in s:
        return "Gemini-3.5 Flash (Standard)"
    elif "nemotron" in s:
        return "Nemotron-3 120B (Open)"
    elif "llama" in s:
        return "LLaMA-3.1 8B (Open)"
    return raw_name.replace("_", " ").replace("-", " ").title()


def find_latest_scores() -> Optional[str]:
    files = sorted(glob.glob(os.path.join(SCORES_DIR, "*_scores.json")))
    return files[-1] if files else None


def _save(fig: plt.Figure, path: str) -> None:
    fig.savefig(path, dpi=STYLE.dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved -> {path}")

# ---------------------------------------------------------------------------
# Ordering helpers
# ---------------------------------------------------------------------------

def _ordered_tasks(scores: List[Dict]) -> List[str]:
    present = {s.get("task") for s in scores if s.get("task")}
    return [t for t in _TASK_PREF if t in present] + sorted(present - set(_TASK_PREF))


def _ordered_variants(scores: List[Dict]) -> List[str]:
    present = {s.get("variant") for s in scores if s.get("variant")}
    return [v for v in _VARIANT_PREF if v in present] + sorted(present - set(_VARIANT_PREF))

# ---------------------------------------------------------------------------
# Metric aggregators
# ---------------------------------------------------------------------------

def sa_mean(group: List[Dict]) -> float:
    vals = [s["step_accuracy"] for s in group if s.get("parse_success", True)]
    return (sum(vals) / len(vals) * 100) if vals else 0.0


def verdict_mean(group: List[Dict]) -> float:
    return (sum(1 for s in group if s.get("verdict_correct")) / len(group) * 100) if group else 0.0

# ---------------------------------------------------------------------------
# Fig 1 — Task x Variant bar charts
# ---------------------------------------------------------------------------

def fig1_task_variant(scores: List[Dict], model_name: str, out_dir: str) -> str:
    _apply_rc()
    task_order    = _ordered_tasks(scores)
    variant_order = _ordered_variants(scores)

    fig, axes = plt.subplots(1, 2, figsize=(STYLE.fig_w_dual, STYLE.fig_h_dual))
    x     = np.arange(len(task_order))
    width = 0.82 / max(len(variant_order), 1)

    for ax, metric_fn, ylabel, title in zip(
        axes,
        [sa_mean, verdict_mean],
        ["Step Accuracy (%)", "Verdict Accuracy (%)"],
        ["Step Accuracy by Task & Strategy",
         "Verdict Accuracy by Task & Strategy"],
    ):
        for vi, variant in enumerate(variant_order):
            var_scores = [s for s in scores if s.get("variant") == variant]
            heights = [metric_fn([s for s in var_scores if s.get("task") == t])
                       for t in task_order]
            offset = (vi - len(variant_order) / 2 + 0.5) * width
            bars = ax.bar(
                x + offset, heights, width,
                label=MAPS.variant_labels.get(variant, variant),
                color=MAPS.variant_colors.get(variant, "#888"),
                alpha=STYLE.bar_alpha, edgecolor="white", linewidth=0.8,
            )
            # Add explicit value labels on top of bars
            for bar, h in zip(bars, heights):
                if h > 1.0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                        f"{h:.0f}%", ha="center", va="bottom",
                        fontsize=8.5, fontweight="bold", color="#222222"
                    )

        ax.set_xticks(x)
        ax.set_xticklabels([MAPS.task_labels.get(t, t) for t in task_order],
                           fontsize=STYLE.font_tick)
        ax.set_ylabel(ylabel, fontsize=STYLE.font_axis, fontweight="bold")
        ax.set_title(title, fontsize=STYLE.font_title, fontweight="bold", pad=12)
        ax.set_ylim(0, 125)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
        ax.legend(fontsize=STYLE.font_legend, loc="upper right", framealpha=0.9, edgecolor="#cccccc")

    fig.suptitle(f"Model: {format_model_label(model_name)}", fontsize=10, color="#444", y=0.01)
    plt.tight_layout()
    path = os.path.join(out_dir, f"{model_name}_fig1_task_variant.png")
    _save(fig, path)
    return path

# ---------------------------------------------------------------------------
# Fig 2 — Complexity scaling law
# ---------------------------------------------------------------------------

def fig2_scaling_law(scores: List[Dict], model_name: str, out_dir: str) -> str:
    _apply_rc()
    task_order   = _ordered_tasks(scores)
    complexities = sorted({s["complexity_level"] for s in scores
                           if s.get("complexity_level") is not None})

    fig, axes = plt.subplots(1, 2, figsize=(STYLE.fig_w_dual, STYLE.fig_h_dual))
    task_markers = {"wfg": "o", "bankers": "s", "buddy": "^", "semaphore": "D", "mutex": "v"}

    for ax, metric_fn, ylabel in zip(
        axes,
        [sa_mean, verdict_mean],
        ["Step Accuracy (%)", "Verdict Accuracy (%)"],
    ):
        for task in task_order:
            task_scores = [s for s in scores if s.get("task") == task]
            ys = [metric_fn([s for s in task_scores if s.get("complexity_level") == c])
                  for c in complexities]
            marker = task_markers.get(task, "o")
            color  = MAPS.task_colors.get(task, "#888")
            ax.plot(
                complexities, ys, f"-{marker}",
                label=MAPS.task_labels.get(task, task).replace("\n", " "),
                color=color,
                linewidth=STYLE.linewidth, markersize=STYLE.markersize,
                markeredgecolor="white", markeredgewidth=1.4
            )
        ax.set_xlabel("Complexity Level (1: Low to 5: High)", fontsize=STYLE.font_axis, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=STYLE.font_axis, fontweight="bold")
        ax.set_title(
            f"Complexity Scaling Law: {ylabel.split('(')[0].strip()}",
            fontsize=STYLE.font_title, fontweight="bold", pad=12,
        )
        ax.set_xticks(complexities)
        ax.set_ylim(-3, 140)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
        # 2-column clean legend placed in upper right with 40% headroom above 100% lines
        ax.legend(fontsize=9.5, loc="upper right", framealpha=0.95,
                  facecolor="white", edgecolor="#cccccc", ncol=2)

    fig.suptitle(f"Model: {format_model_label(model_name)}", fontsize=10, color="#444", y=0.01)
    plt.tight_layout()
    path = os.path.join(out_dir, f"{model_name}_fig2_scaling_law.png")
    _save(fig, path)
    return path

# ---------------------------------------------------------------------------
# Fig 3 — ECR heatmap
# ---------------------------------------------------------------------------

def fig3_ecr_heatmap(scores: List[Dict], model_name: str, out_dir: str) -> str:
    _apply_rc()
    task_order    = _ordered_tasks(scores)
    variant_order = _ordered_variants(scores)

    matrix = np.full((len(task_order), len(variant_order)), np.nan)
    annot  = np.empty_like(matrix, dtype=object)

    for ti, task in enumerate(task_order):
        for vi, variant in enumerate(variant_order):
            group = [s for s in scores
                     if s.get("task") == task and s.get("variant") == variant
                     and s.get("parse_success", True)
                     and s.get("error_cascade_rate") is not None]
            if group:
                val = sum(s["error_cascade_rate"] for s in group) / len(group) * 100
                matrix[ti, vi] = val
                annot[ti, vi]  = f"{val:.1f}%"
            else:
                annot[ti, vi] = "0.0%"

    fig, ax = plt.subplots(figsize=(STYLE.fig_w_heat, STYLE.fig_h_heat))
    im = ax.imshow(np.ma.masked_invalid(matrix), cmap="YlOrRd",
                   vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(len(variant_order)))
    ax.set_xticklabels([MAPS.variant_labels.get(v, v) for v in variant_order],
                       fontsize=STYLE.font_axis, fontweight="bold")
    ax.set_yticks(range(len(task_order)))
    ax.set_yticklabels([MAPS.task_labels.get(t, t).replace("\n", " ") for t in task_order],
                       fontsize=STYLE.font_axis, fontweight="bold")

    for ti in range(len(task_order)):
        for vi in range(len(variant_order)):
            val = matrix[ti, vi]
            color = "white" if (not np.isnan(val) and val > 55) else "black"
            ax.text(vi, ti, annot[ti, vi], ha="center", va="center",
                    fontsize=STYLE.font_annot, fontweight="bold", color=color)

    cbar = plt.colorbar(im, ax=ax, fraction=0.035, pad=0.04)
    cbar.set_label("Error Cascade Rate (%) — Higher indicates severe drift", fontsize=STYLE.font_axis)
    ax.set_title(
        "Error Cascade Rate (ECR) Heatmap by Task & Prompt Strategy",
        fontsize=STYLE.font_title, fontweight="bold", pad=14,
    )
    ax.set_xlabel("Prompting Strategy", fontsize=STYLE.font_axis, fontweight="bold")
    fig.suptitle(f"Model: {format_model_label(model_name)}", fontsize=10, color="#444")
    plt.tight_layout()
    path = os.path.join(out_dir, f"{model_name}_fig3_ecr_heatmap.png")
    _save(fig, path)
    return path

# ---------------------------------------------------------------------------
# Fig 4 — Cross-model comparison (Clean multi-model alignment)
# ---------------------------------------------------------------------------

def fig4_model_comparison(
    model_data: List[Tuple[str, List[Dict]]], out_dir: str
) -> str:
    _apply_rc()
    task_sets  = [set(s.get("task") for s in data) for _, data in model_data]
    task_order = [t for t in _ordered_tasks(model_data[0][1])
                  if all(t in ts for ts in task_sets)]

    fig, axes = plt.subplots(1, 2, figsize=(STYLE.fig_w_dual, STYLE.fig_h_dual))
    x     = np.arange(len(task_order))
    n_models = len(model_data)
    width = 0.84 / max(n_models, 1)

    for ax, metric_fn, ylabel in zip(
        axes,
        [sa_mean, verdict_mean],
        ["Step Accuracy (%)", "Verdict Accuracy (%)"],
    ):
        for mi, (model_raw_name, scores) in enumerate(model_data):
            label_clean = format_model_label(model_raw_name)
            heights = [metric_fn([s for s in scores if s.get("task") == t])
                       for t in task_order]
            offset  = (mi - n_models / 2 + 0.5) * width
            bars = ax.bar(
                x + offset, heights, width,
                label=label_clean,
                color=MAPS.model_colors[mi % len(MAPS.model_colors)],
                alpha=STYLE.bar_alpha, edgecolor="white", linewidth=0.8,
            )
            for bar, h in zip(bars, heights):
                if h > 0.5:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                        f"{h:.0f}%", ha="center", va="bottom",
                        fontsize=7.5, fontweight="bold", color="#222222"
                    )

        ax.set_xticks(x)
        ax.set_xticklabels([MAPS.task_labels.get(t, t) for t in task_order],
                           fontsize=STYLE.font_tick, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=STYLE.font_axis, fontweight="bold")
        ax.set_title(f"Cross-Model Benchmark: {ylabel}",
                     fontsize=STYLE.font_title, fontweight="bold", pad=12)
        ax.set_ylim(0, 130)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
        ax.legend(fontsize=STYLE.font_legend, loc="upper right", framealpha=0.9,
                  edgecolor="#cccccc", ncol=1 if n_models <= 2 else 2)

    plt.tight_layout()
    path = os.path.join(out_dir, "fig4_model_comparison.png")
    _save(fig, path)
    return path

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate high-resolution publication-quality figures from SVAC score files.",
    )
    p.add_argument("--scores",  metavar="PATH", default=None,
                   help="Score JSON for model 1 (default: latest in results/scores/)")
    p.add_argument("--compare", metavar="PATH", nargs="+", default=[],
                   help="Additional Score JSONs for Fig 4 comparison")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    os.makedirs(FIGURES_DIR, exist_ok=True)

    scores_path = args.scores or find_latest_scores()
    if not scores_path:
        sys.exit("No score files found. Run evaluation/svac_run_evaluation.py first.")

    model_name = infer_model_name(scores_path)
    print(f"\nLoading: {scores_path}")
    scores = load_scores(scores_path)
    print(f"  {len(scores)} records | model: {model_name}\n")

    print("Fig 1 — Task x Variant (300 DPI) ...")
    fig1_task_variant(scores, model_name, FIGURES_DIR)

    print("Fig 2 — Complexity Scaling Law (300 DPI) ...")
    fig2_scaling_law(scores, model_name, FIGURES_DIR)

    print("Fig 3 — ECR Heatmap (300 DPI) ...")
    fig3_ecr_heatmap(scores, model_name, FIGURES_DIR)

    if args.compare:
        models = [(model_name, scores)]
        for path in args.compare:
            m_name = infer_model_name(path)
            print(f"\nLoading: {path}")
            m_scores = load_scores(path)
            print(f"  {len(m_scores)} records | model: {m_name}\n")
            models.append((m_name, m_scores))
            
        print("Fig 4 — Cross-Model Comparison (300 DPI) ...")
        fig4_model_comparison(models, FIGURES_DIR)
    else:
        print("\n(Fig 4 skipped — pass --compare <paths> to enable cross-model comparison)")

    print(f"\nAll figures successfully regenerated at 300 DPI in: {FIGURES_DIR}/")


if __name__ == "__main__":
    main()
