#!/usr/bin/env python3
"""
error_taxonomy_report.py
========================
Extracts per-error-type counts from score JSONs to quantify the CoT Inversion
Effect with actual distributions instead of n=1 case studies.

Addresses audit findings M13 (error taxonomy unreported) and E3 (case study
is n=1, not distribution).
"""

import json
import os
from collections import defaultdict

SCORES_DIR = os.path.join(os.path.dirname(__file__), "..", "results", "scores")

# Use the canonical Gemini run
GEMINI_SCORES = "gemini-3-5-flash-lite_20260819_203106_scores.json"


def load_scores(path):
    with open(path) as f:
        return json.load(f)


def analyze_wfg_errors(scores):
    """Extract WFG error taxonomy per prompt strategy."""
    # Group by variant
    by_variant = defaultdict(lambda: defaultdict(int))
    by_variant_counts = defaultdict(int)

    for entry in scores:
        task = entry.get("task", "")
        if task != "wfg":
            continue

        variant = entry.get("variant", "unknown")
        by_variant_counts[variant] += 1

        if not entry.get("parse_success", False):
            by_variant[variant]["_parse_fail"] += 1
            continue

        errors = entry.get("errors_by_type", {})
        for error_type, count in errors.items():
            if count > 0:
                by_variant[variant][error_type] += count

        # Also track per-step errors
        step_results = entry.get("step_results", [])

    return by_variant, by_variant_counts


def analyze_bankers_errors(scores):
    """Extract Banker's error taxonomy per prompt strategy."""
    by_variant = defaultdict(lambda: defaultdict(int))
    by_variant_counts = defaultdict(int)

    for entry in scores:
        task = entry.get("task", "")
        if task != "bankers":
            continue

        variant = entry.get("variant", "unknown")
        by_variant_counts[variant] += 1

        if not entry.get("parse_success", False):
            by_variant[variant]["_parse_fail"] += 1
            continue

        errors = entry.get("errors_by_type", {})
        for error_type, count in errors.items():
            if count > 0:
                by_variant[variant][error_type] += count

    return by_variant, by_variant_counts


def analyze_fep_distribution(scores):
    """Extract First Error Position distribution per task × variant."""
    fep_data = defaultdict(lambda: defaultdict(list))
    sa_data = defaultdict(lambda: defaultdict(list))

    for entry in scores:
        task = entry.get("task", "unknown")
        variant = entry.get("variant", "unknown")

        if not entry.get("parse_success", False):
            continue

        fep = entry.get("first_error_position")
        sa = entry.get("step_accuracy", 0.0)
        n_gt = entry.get("n_steps_ground_truth", 0)

        if fep is not None:
            fep_data[task][variant].append(fep)
        sa_data[task][variant].append(sa)

    return fep_data, sa_data


def main():
    path = os.path.join(SCORES_DIR, GEMINI_SCORES)
    scores = load_scores(path)

    print("=" * 80)
    print("SVAC-Concurrency: ERROR TAXONOMY & FEP DISTRIBUTION REPORT")
    print(f"Model: Gemini-3.5-Flash-Lite")
    print(f"Score file: {GEMINI_SCORES}")
    print("=" * 80)

    # --- WFG Error Taxonomy ---
    wfg_errors, wfg_counts = analyze_wfg_errors(scores)
    print("\n### WFG Deadlock Detection — Error Taxonomy by Prompt Strategy ###\n")
    for variant in ["zero_shot", "few_shot", "cot"]:
        errors = wfg_errors.get(variant, {})
        n = wfg_counts.get(variant, 0)
        print(f"  [{variant}] (N={n})")
        if errors:
            for err_type, count in sorted(errors.items(), key=lambda x: -x[1]):
                print(f"    {err_type:<35} {count:>4}")
        else:
            print(f"    No errors (all correct)")
        print()

    # --- Banker's Error Taxonomy ---
    bankers_errors, bankers_counts = analyze_bankers_errors(scores)
    print("\n### Banker's Algorithm — Error Taxonomy by Prompt Strategy ###\n")
    for variant in ["zero_shot", "few_shot", "cot"]:
        errors = bankers_errors.get(variant, {})
        n = bankers_counts.get(variant, 0)
        print(f"  [{variant}] (N={n})")
        if errors:
            for err_type, count in sorted(errors.items(), key=lambda x: -x[1]):
                print(f"    {err_type:<35} {count:>4}")
        else:
            print(f"    No errors (all correct)")
        print()

    # --- FEP Distribution ---
    fep_data, sa_data = analyze_fep_distribution(scores)
    print("\n### First Error Position (FEP) Distribution ###\n")
    for task in ["wfg", "bankers", "buddy", "semaphore", "mutex"]:
        print(f"  --- {task.upper()} ---")
        for variant in ["zero_shot", "few_shot", "cot"]:
            feps = fep_data.get(task, {}).get(variant, [])
            sas = sa_data.get(task, {}).get(variant, [])
            if not feps:
                if sas:
                    perfect = sum(1 for s in sas if s >= 0.9999)
                    print(f"    [{variant}] N={len(sas)}, Perfect traces: {perfect}/{len(sas)}")
                continue
            mean_fep = sum(feps) / len(feps)
            median_fep = sorted(feps)[len(feps) // 2]
            min_fep = min(feps)
            max_fep = max(feps)
            fep_1_count = sum(1 for f in feps if f == 1)
            perfect = sum(1 for s in sas if s >= 0.9999)
            print(f"    [{variant}] N={len(sas)}, FEP entries={len(feps)}, "
                  f"Mean FEP={mean_fep:.1f}, Median FEP={median_fep}, "
                  f"Min={min_fep}, Max={max_fep}, "
                  f"FEP=1 (step-1 errors): {fep_1_count} ({fep_1_count/len(feps):.0%}), "
                  f"Perfect: {perfect}")
        print()

    # --- Key finding: SA on non-saturated tasks only ---
    print("\n### Non-Saturated Task SA (excluding Mutex 100% + Semaphore ~95%) ###\n")
    non_sat_sa = []
    sat_sa = []
    for entry in scores:
        task = entry.get("task", "")
        if not entry.get("parse_success", False):
            continue
        sa = entry.get("step_accuracy", 0.0)
        if task in ("mutex", "semaphore"):
            sat_sa.append(sa)
        else:
            non_sat_sa.append(sa)

    if non_sat_sa:
        mean_non_sat = sum(non_sat_sa) / len(non_sat_sa)
        print(f"  Non-saturated tasks (WFG + Banker's + Buddy): N={len(non_sat_sa)}, Mean SA={mean_non_sat:.1%}")
    if sat_sa:
        mean_sat = sum(sat_sa) / len(sat_sa)
        print(f"  Saturated tasks (Mutex + Semaphore):          N={len(sat_sa)}, Mean SA={mean_sat:.1%}")
    all_sa = non_sat_sa + sat_sa
    print(f"  All tasks combined:                            N={len(all_sa)}, Mean SA={sum(all_sa)/len(all_sa):.1%}")


if __name__ == "__main__":
    main()
