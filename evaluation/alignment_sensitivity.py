#!/usr/bin/env python3
"""
alignment_sensitivity.py
========================
Evaluates trace alignment sensitivity (Positional vs Sequence-Aligned SA).

Addresses Review Findings: M12, E11.
Strict 1-to-1 positional matching (step i vs step i) causes severe cascade penalties
if a model inserts or deletes even a single step. This script computes:
1. Trace length disparity: m (model steps) vs T* (ground truth steps).
2. Positional SA (strict i == i) vs Aligned SA (LCS / optimal monotonic alignment).
3. Impact across tasks and prompting strategies (especially WFG CoT).
"""

import json
import os
import sys
from collections import defaultdict
from typing import Dict, Any, List, Tuple

BASE = "/Users/bethegnt/Downloads/SVAC_Concurrency"
BANKERS_FILE = os.path.join(BASE, "data", "instances", "svac_bankers_instances.json")
WFG_FILE = os.path.join(BASE, "data", "instances", "svac_wfg_instances.json")
RESP_DIR_GEMINI = os.path.join(BASE, "svac_llm_responses", "gemini-3-5-flash-lite")
OUTPUT_REPORT = os.path.join(BASE, "results", "reports", "alignment_sensitivity_report.json")

sys.path.insert(0, os.path.join(BASE, "evaluation"))
from svac_deadlock_scorer import parse_model_response, ParseError, _normalize_set_field


def load_instances() -> Dict[str, Dict[str, Any]]:
    instances = {}
    if os.path.exists(BANKERS_FILE):
        with open(BANKERS_FILE) as f:
            for inst in json.load(f):
                instances[inst["instance_id"]] = inst
    if os.path.exists(WFG_FILE):
        with open(WFG_FILE) as f:
            for inst in json.load(f):
                instances[inst["instance_id"]] = inst
    return instances


def step_matches_wfg(m_step: Dict[str, Any], gt_step: Dict[str, Any]) -> bool:
    if not isinstance(m_step, dict) or not isinstance(gt_step, dict):
        return False
    if m_step.get("action") != gt_step.get("action"):
        return False
    if m_step.get("node") != gt_step.get("node"):
        return False
    if _normalize_set_field(m_step.get("visited_set")) != _normalize_set_field(gt_step.get("visited_set")):
        return False
    if m_step.get("recursion_stack") != gt_step.get("recursion_stack"):
        return False
    if gt_step.get("action") == "cycle_detected" and m_step.get("cycle") != gt_step.get("cycle"):
        return False
    return True


def step_matches_bankers(m_step: Dict[str, Any], gt_step: Dict[str, Any]) -> bool:
    if not isinstance(m_step, dict) or not isinstance(gt_step, dict):
        return False
    if m_step.get("candidate_process") != gt_step.get("candidate_process"):
        return False
    if m_step.get("work_before") != gt_step.get("work_before"):
        return False
    if m_step.get("work_after") != gt_step.get("work_after"):
        return False
    if m_step.get("finish") != gt_step.get("finish"):
        return False
    if gt_step.get("need_row") is not None and m_step.get("need_row") != gt_step.get("need_row"):
        return False
    return True


def compute_lcs_alignment(m_steps: List[Dict], gt_steps: List[Dict], match_fn) -> int:
    """Computes length of Longest Common Subsequence of matching steps."""
    m = len(m_steps)
    n = len(gt_steps)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if match_fn(m_steps[i - 1], gt_steps[j - 1]):
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def main():
    print("=" * 80)
    print("SVAC-CONCURRENCY: TRACE ALIGNMENT SENSITIVITY AUDIT")
    print("=" * 80)

    instances = load_instances()
    score_file = os.path.join(BASE, "results", "scores", "gemini-3-5-flash-lite_20260819_203106_scores.json")
    with open(score_file) as f:
        gemini_scores = json.load(f)

    score_by_key = {}
    for s in gemini_scores:
        key = (s["task"], s["variant"], s["instance_id"])
        score_by_key[key] = s

    stats = defaultdict(lambda: {
        "m_lens": [], "gt_lens": [],
        "strict_sa": [], "aligned_sa": [],
        "len_ratio": []
    })

    for key, orig_score in score_by_key.items():
        task, strat, iid = key
        if task not in ["wfg", "bankers"]:
            continue
        if not orig_score.get("parse_success"):
            continue

        resp_file = os.path.join(RESP_DIR_GEMINI, f"{task}__{strat}__{iid}.json")
        if not os.path.exists(resp_file):
            continue

        with open(resp_file) as f:
            resp_data = json.load(f)

        try:
            model_out = parse_model_response(resp_data.get("response_text", ""))
        except ParseError:
            continue

        inst = instances.get(iid)
        if not inst:
            continue

        gt_steps = inst["ground_truth"]["steps"]
        m_steps = model_out.get("steps", [])
        if not isinstance(m_steps, list):
            m_steps = []

        m_len = len(m_steps)
        gt_len = len(gt_steps)
        match_fn = step_matches_wfg if task == "wfg" else step_matches_bankers

        # Strict positional match
        n_pos_matches = sum(
            1 for i in range(min(m_len, gt_len))
            if match_fn(m_steps[i], gt_steps[i])
        )
        strict_sa = (n_pos_matches / gt_len) if gt_len > 0 else 0.0

        # LCS-aligned match
        lcs_matches = compute_lcs_alignment(m_steps, gt_steps, match_fn)
        aligned_sa = (lcs_matches / gt_len) if gt_len > 0 else 0.0

        cell = f"{task}__{strat}"
        stats[cell]["m_lens"].append(m_len)
        stats[cell]["gt_lens"].append(gt_len)
        stats[cell]["strict_sa"].append(strict_sa)
        stats[cell]["aligned_sa"].append(aligned_sa)
        stats[cell]["len_ratio"].append(m_len / gt_len if gt_len > 0 else 1.0)

    print("\n" + "=" * 90)
    print(f"{'Cell':<22} | {'Mean m':<8} | {'Mean T*':<8} | {'m/T*':<6} | {'Strict SA':<10} | {'Aligned SA':<10} | {'Delta':<8}")
    print("=" * 90)

    report_out = {}
    for cell in sorted(stats.keys()):
        d = stats[cell]
        mean_m = sum(d["m_lens"]) / len(d["m_lens"])
        mean_gt = sum(d["gt_lens"]) / len(d["gt_lens"])
        mean_ratio = sum(d["len_ratio"]) / len(d["len_ratio"])
        mean_strict = sum(d["strict_sa"]) / len(d["strict_sa"])
        mean_aligned = sum(d["aligned_sa"]) / len(d["aligned_sa"])
        delta = mean_aligned - mean_strict

        print(f"{cell:<22} | {mean_m:<8.1f} | {mean_gt:<8.1f} | {mean_ratio:<6.2f} | {mean_strict*100:<9.1f}% | {mean_aligned*100:<9.1f}% | {delta*100:+7.1f}%")

        report_out[cell] = {
            "mean_m": mean_m,
            "mean_gt": mean_gt,
            "ratio": mean_ratio,
            "strict_sa": mean_strict,
            "aligned_sa": mean_aligned,
            "delta": delta,
            "n": len(d["m_lens"])
        }

    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)
    with open(OUTPUT_REPORT, "w") as f:
        json.dump(report_out, f, indent=2)
    print(f"\nReport saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
