#!/usr/bin/env python3
"""
fep_analysis.py
===============
Analyzes and visualizes First Error Position (FEP) distributions across tasks
and prompt strategies for SVAC-Concurrency.

Addresses Review Finding C6.
"""

import json
import os
import sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = "/Users/bethegnt/Downloads/SVAC_Concurrency"
SCORES_FILE = os.path.join(BASE, "results", "scores", "gemini-3-5-flash-lite_20260819_203106_scores.json")
FIGURES_DIR = os.path.join(BASE, "analysis", "figures")
OUTPUT_REPORT = os.path.join(BASE, "results", "reports", "fep_analysis_report.json")


def main():
    print("=" * 80)
    print("SVAC-CONCURRENCY: FIRST ERROR POSITION (FEP) ANALYSIS")
    print("=" * 80)

    with open(SCORES_FILE) as f:
        scores = json.load(f)

    # Group FEP by task and strategy
    fep_data = defaultdict(lambda: defaultdict(list))
    fep1_counts = defaultdict(lambda: defaultdict(int))
    total_with_errors = defaultdict(lambda: defaultdict(int))

    for s in scores:
        if not s.get("parse_success"):
            continue
        task = s["task"]
        strat = s["variant"]
        fep = s.get("first_error_position")

        if fep is not None and fep > 0:
            total_with_errors[task][strat] += 1
            fep_data[task][strat].append(fep)
            if fep == 1:
                fep1_counts[task][strat] += 1

    print("\n" + "=" * 85)
    print(f"{'Task':<18} | {'Strategy':<10} | {'N Err':<6} | {'FEP=1 (%)':<10} | {'Mean FEP':<10} | {'Median FEP':<10}")
    print("=" * 85)

    report_dict = {}
    for task in sorted(fep_data.keys()):
        report_dict[task] = {}
        for strat in ["zero_shot", "few_shot", "cot"]:
            vals = fep_data[task][strat]
            n_err = len(vals)
            if n_err > 0:
                fep1_pct = (fep1_counts[task][strat] / n_err) * 100
                mean_fep = float(np.mean(vals))
                med_fep = float(np.median(vals))
            else:
                fep1_pct = 0.0
                mean_fep = 0.0
                med_fep = 0.0

            print(f"{task:<18} | {strat:<10} | {n_err:<6} | {fep1_pct:<9.1f}% | {mean_fep:<10.2f} | {med_fep:<10.1f}")
            report_dict[task][strat] = {
                "n_errors": n_err,
                "fep1_pct": fep1_pct,
                "mean_fep": mean_fep,
                "median_fep": med_fep,
                "raw_fep": vals
            }

    # Plot FEP Distribution Figure
    os.makedirs(FIGURES_DIR, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)

    tasks_to_plot = ["wfg", "bankers", "buddy"]
    task_names = ["WFG Deadlock", "Banker's Safety", "Buddy System"]
    colors = {"zero_shot": "#E24A33", "few_shot": "#348ABD", "cot": "#8EBA63"}

    for ax, task_key, task_name in zip(axes, tasks_to_plot, task_names):
        all_vals = []
        labels = []
        plot_colors = []
        for strat in ["zero_shot", "few_shot", "cot"]:
            vals = fep_data[task_key][strat]
            if vals:
                all_vals.append(vals)
                labels.append(f"{strat.replace('_', ' ').title()}\n(N={len(vals)})")
                plot_colors.append(colors[strat])

        if all_vals:
            bp = ax.boxplot(all_vals, patch_artist=True, tick_labels=labels, widths=0.5)
            for patch, col in zip(bp["boxes"], plot_colors):
                patch.set_facecolor(col)
                patch.set_alpha(0.7)
            for median in bp["medians"]:
                median.set_color("black")
                median.set_linewidth(2)

        ax.set_title(f"{task_name} (FEP Distribution)", fontsize=12, fontweight="bold", pad=10)
        ax.set_ylabel("First Error Step Position", fontsize=11, fontweight="bold")
        ax.grid(True, linestyle="--", alpha=0.5, axis="y")
        ax.set_ylim(0, 25)

    plt.suptitle("First Error Position (FEP) Across Reasoning Tasks (Gemini-3.5-Flash-Lite)", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    out_fig = os.path.join(FIGURES_DIR, "fig5_fep_distribution.png")
    plt.savefig(out_fig, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nFigure saved to: {out_fig}")

    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)
    with open(OUTPUT_REPORT, "w") as f:
        json.dump(report_dict, f, indent=2)
    print(f"Report saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
