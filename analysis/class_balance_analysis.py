#!/usr/bin/env python3
"""
class_balance_analysis.py
=========================
Computes class balance, majority-class baselines, and Wilson confidence
intervals for all SVAC-Concurrency task families.

Addresses audit findings: M6 (class balance unreported), E4 (baselines),
and the 50%-guessing-baseline claim in §I.

Output: printed tables + CSV for paper integration.
"""

import json
import math
import os
import sys
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "instances")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "results", "reports")


def wilson_ci(p_hat, n, z=1.96):
    """Wilson score interval for a proportion (95% CI)."""
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z**2 / n
    centre = (p_hat + z**2 / (2 * n)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    return (max(0, centre - spread), min(1, centre + spread))


def load_instances(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path) as f:
        return json.load(f)


def analyze_wfg():
    instances = load_instances("svac_wfg_instances.json")
    labels = [inst["ground_truth"]["deadlock"] for inst in instances]
    n_pos = sum(1 for l in labels if l is True)
    n_neg = sum(1 for l in labels if l is False)
    n = len(labels)

    # Per complexity level
    by_level = {}
    for inst in instances:
        level = inst["complexity_level"]
        by_level.setdefault(level, []).append(inst["ground_truth"]["deadlock"])

    # Ground-truth step counts
    step_counts = [len(inst["ground_truth"]["steps"]) for inst in instances]

    return {
        "task": "WFG Deadlock Detection",
        "short": "wfg",
        "n": n,
        "positive_label": "deadlock=True",
        "negative_label": "deadlock=False",
        "n_positive": n_pos,
        "n_negative": n_neg,
        "balance": n_pos / n if n > 0 else 0,
        "majority_baseline_va": max(n_pos, n_neg) / n if n > 0 else 0,
        "random_baseline_va": 0.5,
        "by_level": {k: {"n": len(v), "pos": sum(v), "neg": len(v) - sum(v)}
                     for k, v in sorted(by_level.items())},
        "step_counts": {
            "min": min(step_counts), "max": max(step_counts),
            "mean": sum(step_counts) / len(step_counts),
        },
    }


def analyze_bankers():
    instances = load_instances("svac_bankers_instances.json")
    labels = [inst["ground_truth"]["safe"] for inst in instances]
    n_pos = sum(1 for l in labels if l is True)
    n_neg = sum(1 for l in labels if l is False)
    n = len(labels)

    by_level = {}
    for inst in instances:
        level = inst["complexity_level"]
        by_level.setdefault(level, []).append(inst["ground_truth"]["safe"])

    step_counts = [len(inst["ground_truth"]["steps"]) for inst in instances]

    return {
        "task": "Banker's Algorithm",
        "short": "bankers",
        "n": n,
        "positive_label": "safe=True",
        "negative_label": "safe=False (unsafe)",
        "n_positive": n_pos,
        "n_negative": n_neg,
        "balance": n_pos / n if n > 0 else 0,
        "majority_baseline_va": max(n_pos, n_neg) / n if n > 0 else 0,
        "random_baseline_va": 0.5,
        "by_level": {k: {"n": len(v), "pos": sum(v), "neg": len(v) - sum(v)}
                     for k, v in sorted(by_level.items())},
        "step_counts": {
            "min": min(step_counts), "max": max(step_counts),
            "mean": sum(step_counts) / len(step_counts),
        },
    }


def analyze_buddy():
    instances = load_instances("svac_buddy_instances.json")
    n = len(instances)

    # Buddy doesn't have a binary verdict the same way; check what's there
    step_counts = [len(inst["ground_truth"]["steps"]) for inst in instances]

    by_level = {}
    for inst in instances:
        level = inst["complexity_level"]
        by_level.setdefault(level, []).append(1)

    return {
        "task": "Buddy System Allocation",
        "short": "buddy",
        "n": n,
        "positive_label": "N/A (no binary verdict)",
        "negative_label": "N/A",
        "n_positive": "N/A",
        "n_negative": "N/A",
        "balance": "N/A (non-binary task)",
        "majority_baseline_va": "N/A",
        "random_baseline_va": "N/A",
        "by_level": {k: {"n": len(v)} for k, v in sorted(by_level.items())},
        "step_counts": {
            "min": min(step_counts), "max": max(step_counts),
            "mean": sum(step_counts) / len(step_counts),
        },
    }


def analyze_semaphore():
    instances = load_instances("svac_semaphore_instances.json")
    n = len(instances)
    step_counts = [len(inst["ground_truth"]["steps"]) for inst in instances]

    by_level = {}
    for inst in instances:
        level = inst["complexity_level"]
        by_level.setdefault(level, []).append(1)

    return {
        "task": "Counting Semaphore",
        "short": "semaphore",
        "n": n,
        "positive_label": "N/A (no binary verdict)",
        "negative_label": "N/A",
        "n_positive": "N/A",
        "n_negative": "N/A",
        "balance": "N/A",
        "majority_baseline_va": "N/A",
        "random_baseline_va": "N/A",
        "by_level": {k: {"n": len(v)} for k, v in sorted(by_level.items())},
        "step_counts": {
            "min": min(step_counts), "max": max(step_counts),
            "mean": sum(step_counts) / len(step_counts),
        },
    }


def analyze_mutex():
    instances = load_instances("svac_mutex_instances.json")
    n = len(instances)
    step_counts = [len(inst["ground_truth"]["steps"]) for inst in instances]

    by_level = {}
    for inst in instances:
        level = inst["complexity_level"]
        by_level.setdefault(level, []).append(1)

    return {
        "task": "Mutex Lock Synchronization",
        "short": "mutex",
        "n": n,
        "positive_label": "N/A (no binary verdict)",
        "negative_label": "N/A",
        "n_positive": "N/A",
        "n_negative": "N/A",
        "balance": "N/A",
        "majority_baseline_va": "N/A",
        "random_baseline_va": "N/A",
        "by_level": {k: {"n": len(v)} for k, v in sorted(by_level.items())},
        "step_counts": {
            "min": min(step_counts), "max": max(step_counts),
            "mean": sum(step_counts) / len(step_counts),
        },
    }


def print_report(results):
    print("=" * 80)
    print("SVAC-Concurrency: CLASS BALANCE & BASELINE ANALYSIS")
    print("=" * 80)

    print("\n### TABLE: Ground-Truth Label Distribution ###\n")
    header = f"{'Task':<28} {'N':>4} {'Positive':>12} {'Negative':>12} {'Balance':>10} {'Majority BL':>12} {'Random BL':>10}"
    print(header)
    print("-" * len(header))

    for r in results:
        if isinstance(r["n_positive"], int):
            pos_str = f"{r['n_positive']} ({r['balance']:.1%})"
            neg_str = f"{r['n_negative']} ({1 - r['balance']:.1%})"
            maj_str = f"{r['majority_baseline_va']:.1%}"
            rnd_str = f"{r['random_baseline_va']:.1%}"
        else:
            pos_str = neg_str = maj_str = rnd_str = "N/A"

        bal_str = "N/A" if isinstance(r['balance'], str) else f"{r['balance']:.1%}"
        print(f"{r['task']:<28} {r['n']:>4} {pos_str:>12} {neg_str:>12} "
              f"{bal_str:>10} {maj_str:>12} {rnd_str:>10}")

    # Detail for binary-verdict tasks
    for r in results:
        if isinstance(r["n_positive"], int):
            print(f"\n--- {r['task']} per complexity level ---")
            for level, data in r["by_level"].items():
                print(f"  Level {level}: N={data['n']}, "
                      f"positive={data['pos']}, negative={data['neg']}, "
                      f"balance={data['pos']/data['n']:.1%}")

    # Step count distributions
    print("\n### TABLE: Ground-Truth Trace Lengths (T*) ###\n")
    header2 = f"{'Task':<28} {'Min T*':>8} {'Mean T*':>9} {'Max T*':>8}"
    print(header2)
    print("-" * len(header2))
    for r in results:
        sc = r["step_counts"]
        print(f"{r['task']:<28} {sc['min']:>8} {sc['mean']:>9.1f} {sc['max']:>8}")

    # Wilson CIs for key paper proportions
    print("\n### TABLE: Wilson 95% Confidence Intervals for Key Gemini Metrics ###\n")
    # Load Gemini report data
    gemini_metrics = [
        ("Overall SA",      0.561, 375),
        ("Overall VA",      0.723, 375),
        ("Overall ECR",     0.369, 375),
        ("WFG SA (ZS)",     0.043, 30),
        ("WFG SA (FS)",     0.854, 30),
        ("WFG SA (CoT)",    0.075, 30),
        ("Banker's SA (ZS)", 0.329, 30),
        ("Banker's SA (CoT)", 0.497, 30),
        ("Buddy SA (CoT)",  0.491, 25),
        ("Mutex SA",        1.000, 60),
        ("Semaphore SA",    0.942, 60),
    ]
    header3 = f"{'Metric':<24} {'Point Est':>10} {'N':>5} {'95% CI Lower':>13} {'95% CI Upper':>13}"
    print(header3)
    print("-" * len(header3))
    for name, p, n in gemini_metrics:
        lo, hi = wilson_ci(p, n)
        print(f"{name:<24} {p:>10.1%} {n:>5} {lo:>13.1%} {hi:>13.1%}")


def main():
    results = [
        analyze_wfg(),
        analyze_bankers(),
        analyze_buddy(),
        analyze_semaphore(),
        analyze_mutex(),
    ]
    print_report(results)

    # Save as JSON for other scripts
    out_path = os.path.join(os.path.dirname(__file__), "..", "results",
                            "reports", "class_balance_analysis.json")
    # Sanitize for JSON (replace non-serializable)
    for r in results:
        for k, v in r.items():
            if v == "N/A":
                r[k] = None
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
