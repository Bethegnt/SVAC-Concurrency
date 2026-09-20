#!/usr/bin/env python3
"""
validity_checker.py
===================
Equivalence-Aware Scoring (Invariant-Based Validation) for SVAC-Concurrency.

Evaluates whether model step errors in Banker's Algorithm and WFG Deadlock
Detection are genuine reasoning errors or artifacts of alternative valid choices
(e.g., multiple valid safe sequences, alternative DFS traversal orderings).

Addresses Review Findings: M1, E1.
"""

import json
import os
import sys
import re
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple

BASE = "/Users/bethegnt/Downloads/SVAC_Concurrency"
BANKERS_FILE = os.path.join(BASE, "data", "instances", "svac_bankers_instances.json")
WFG_FILE = os.path.join(BASE, "data", "instances", "svac_wfg_instances.json")
RESP_DIR_GEMINI = os.path.join(BASE, "svac_llm_responses", "gemini-3-5-flash-lite")
OUTPUT_REPORT = os.path.join(BASE, "results", "reports", "validity_checker_report.json")

sys.path.insert(0, os.path.join(BASE, "evaluation"))
from svac_deadlock_scorer import parse_model_response, ParseError


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


# ==============================================================================
# BANKER'S ALGORITHM INVARIANT CHECKER
# ==============================================================================
def validate_bankers_trace(instance: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks each step of Banker's safety algorithm against semantic invariants.
    
    Invariants:
    1. If candidate_process is an int:
       a) Must be within [0, n_p - 1] and not yet finished.
       b) Need[candidate_process] <= current Work.
       c) work_after == current Work + allocation[candidate_process].
       d) finish[candidate_process] flips to True.
    2. If candidate_process is None:
       a) Verified that NO unfinished process can satisfy Need <= Work.
       b) This is a valid terminal step for unsafe states (or when stuck).
    """
    alloc = instance["allocation"]
    max_mat = instance["max_matrix"]
    avail = list(instance["available"])
    n_p = len(alloc)
    n_r = len(avail)
    need = [[max_mat[i][j] - alloc[i][j] for j in range(n_r)] for i in range(n_p)]

    model_steps = model_output.get("steps", [])
    if not isinstance(model_steps, list) or len(model_steps) == 0:
        return {
            "n_steps": 0,
            "step_validity": [],
            "valid_step_rate": 0.0,
            "valid_safe_sequence": False,
            "alt_safe_sequence": False,
            "gt_safe": instance["ground_truth"]["safe"],
            "model_safe": model_output.get("safe")
        }

    work = list(avail)
    finished = [False] * n_p
    step_validity = []

    for idx, s in enumerate(model_steps):
        if not isinstance(s, dict):
            step_validity.append(False)
            continue

        p = s.get("candidate_process")
        wb = s.get("work_before")
        wa = s.get("work_after")
        fin = s.get("finish")
        need_row = s.get("need_row")

        is_valid = True

        if p is None:
            # Check if any unfinished process could have run
            can_any_run = any(
                not finished[i] and all(need[i][j] <= work[j] for j in range(n_r))
                for i in range(n_p)
            )
            if can_any_run:
                is_valid = False
        else:
            if not isinstance(p, int) or p < 0 or p >= n_p or finished[p]:
                is_valid = False
            else:
                # Check need <= work
                can_run = all(need[p][j] <= work[j] for j in range(n_r))
                if not can_run:
                    is_valid = False

                # Check need_row if provided
                if need_row is not None and need_row != need[p]:
                    is_valid = False

                # Transition state
                work = [work[j] + alloc[p][j] for j in range(n_r)]
                finished[p] = True

                # Check work_after if provided
                if wa is not None and wa != work:
                    is_valid = False

                # Check finish if provided
                if fin is not None and fin != finished:
                    is_valid = False

        step_validity.append(is_valid)

    # Check safe sequence validity
    safe_seq = model_output.get("safe_sequence")
    safe_verdict = model_output.get("safe")
    valid_safe_sequence = False
    alt_safe_sequence = False
    gt_safe_seq = instance["ground_truth"].get("safe_sequence")

    if safe_verdict is True and isinstance(safe_seq, list) and len(safe_seq) == n_p:
        # Normalize process entries: e.g. "P0" -> 0, or 0 -> 0
        norm_seq = []
        for x in safe_seq:
            if isinstance(x, int):
                norm_seq.append(x)
            elif isinstance(x, str) and (x.startswith("P") or x.startswith("p")) and x[1:].isdigit():
                norm_seq.append(int(x[1:]))
            elif isinstance(x, str) and x.isdigit():
                norm_seq.append(int(x))

        if len(norm_seq) == n_p and sorted(norm_seq) == list(range(n_p)):
            t_work = list(avail)
            possible = True
            for p in norm_seq:
                if all(need[p][j] <= t_work[j] for j in range(n_r)):
                    t_work = [t_work[j] + alloc[p][j] for j in range(n_r)]
                else:
                    possible = False
                    break
            valid_safe_sequence = possible
            if possible and gt_safe_seq is not None:
                # Normalize gt_safe_seq for comparison
                norm_gt = [int(x[1:]) if isinstance(x, str) and x.startswith('P') else int(x) for x in gt_safe_seq]
                if norm_seq != norm_gt:
                    alt_safe_sequence = True

    return {
        "n_steps": len(model_steps),
        "step_validity": step_validity,
        "valid_step_rate": (sum(step_validity) / len(step_validity)) if step_validity else 0.0,
        "valid_safe_sequence": valid_safe_sequence,
        "alt_safe_sequence": alt_safe_sequence,
        "gt_safe": instance["ground_truth"]["safe"],
        "model_safe": safe_verdict
    }


# ==============================================================================
# WFG INVARIANT CHECKER
# ==============================================================================
def validate_wfg_trace(instance: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks if WFG steps emitted by the model form a sound DFS traversal on the given graph.
    """
    adj = instance.get("edges", {})
    all_nodes = set(instance.get("processes", []))
    model_steps = model_output.get("steps", [])

    if not isinstance(model_steps, list) or len(model_steps) == 0:
        return {
            "n_steps": 0,
            "step_validity": [],
            "valid_step_rate": 0.0,
            "gt_deadlock": instance["ground_truth"]["deadlock"],
            "model_deadlock": model_output.get("deadlock")
        }

    step_validity = []
    stack = []
    visited = set()

    for s in model_steps:
        if not isinstance(s, dict):
            step_validity.append(False)
            continue

        action = s.get("action")
        node = s.get("node")
        m_visited = s.get("visited_set")
        m_stack = s.get("recursion_stack")

        valid = True
        if action == "visit":
            if not stack:
                stack.append(node)
                visited.add(node)
            else:
                top = stack[-1]
                # Is node a neighbor of top?
                if node not in adj.get(top, []):
                    valid = False
                stack.append(node)
                visited.add(node)
        elif action == "backtrack":
            if not stack or stack[-1] != node:
                valid = False
            else:
                stack.pop()
        elif action == "cycle_detected":
            # cycle detected: node must be in current stack and adjacent to stack top
            if not stack or node not in stack or node not in adj.get(stack[-1], []):
                valid = False
        else:
            valid = False

        step_validity.append(valid)

    return {
        "n_steps": len(model_steps),
        "step_validity": step_validity,
        "valid_step_rate": (sum(step_validity) / len(step_validity)) if step_validity else 0.0,
        "gt_deadlock": instance["ground_truth"]["deadlock"],
        "model_deadlock": model_output.get("deadlock")
    }


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("=" * 80)
    print("SVAC-CONCURRENCY: EQUIVALENCE-AWARE / INVARIANT-BASED SCORING AUDIT")
    print("=" * 80)

    instances = load_instances()
    print(f"Loaded {len(instances)} instances.")

    # Load Gemini score file to get original exact-match SA
    score_file = os.path.join(BASE, "results", "scores", "gemini-3-5-flash-lite_20260819_203106_scores.json")
    with open(score_file) as f:
        gemini_scores = json.load(f)

    score_by_key = {}
    for s in gemini_scores:
        key = (s["task"], s["variant"], s["instance_id"])
        score_by_key[key] = s

    # Audit Banker's instances
    bankers_results = []
    bankers_delta_sa = []
    bankers_alt_safe_seq = 0

    # Audit WFG instances
    wfg_results = []
    wfg_delta_sa = []

    for key, orig_score in score_by_key.items():
        task, strat, iid = key
        if not orig_score.get("parse_success"):
            continue

        resp_file = os.path.join(RESP_DIR_GEMINI, f"{task}__{strat}__{iid}.json")
        if not os.path.exists(resp_file):
            continue

        with open(resp_file) as f:
            resp_data = json.load(f)

        raw_text = resp_data.get("response_text", "")
        try:
            model_out = parse_model_response(raw_text)
        except ParseError:
            continue

        inst = instances.get(iid)
        if not inst:
            continue

        orig_sa = orig_score.get("step_accuracy", 0.0)

        if task == "bankers":
            v_res = validate_bankers_trace(inst, model_out)
            valid_sa = v_res["valid_step_rate"]
            bankers_results.append({
                "instance_id": iid,
                "strategy": strat,
                "orig_sa": orig_sa,
                "valid_sa": valid_sa,
                "delta": valid_sa - orig_sa,
                "valid_safe_seq": v_res["valid_safe_sequence"],
                "alt_safe_seq": v_res["alt_safe_sequence"],
                "gt_safe": v_res["gt_safe"],
                "model_safe": v_res["model_safe"]
            })
            bankers_delta_sa.append(valid_sa - orig_sa)
            if v_res["alt_safe_sequence"]:
                bankers_alt_safe_seq += 1

        elif task == "wfg":
            v_res = validate_wfg_trace(inst, model_out)
            valid_sa = v_res["valid_step_rate"]
            wfg_results.append({
                "instance_id": iid,
                "strategy": strat,
                "orig_sa": orig_sa,
                "valid_sa": valid_sa,
                "delta": valid_sa - orig_sa
            })
            wfg_delta_sa.append(valid_sa - orig_sa)

    # Summarize Banker's
    mean_orig_b = sum(r["orig_sa"] for r in bankers_results) / len(bankers_results) if bankers_results else 0
    mean_valid_b = sum(r["valid_sa"] for r in bankers_results) / len(bankers_results) if bankers_results else 0
    mean_delta_b = sum(bankers_delta_sa) / len(bankers_delta_sa) if bankers_delta_sa else 0

    print("\n" + "=" * 60)
    print("BANKER'S ALGORITHM EQUIVALENCE-AWARE SCORING (N = %d parsed)" % len(bankers_results))
    print("=" * 60)
    print(f"  Exact-Match SA (Positional):  {mean_orig_b * 100:.2f}%")
    print(f"  Equivalence-Aware Valid SA:   {mean_valid_b * 100:.2f}%")
    print(f"  Mean Delta (Valid - Exact):   {mean_delta_b * 100:+.2f}%")
    print(f"  Cases with Alternative Valid Safe Sequence: {bankers_alt_safe_seq} / {len(bankers_results)}")

    by_strat_b = defaultdict(lambda: {"orig": [], "valid": []})
    for r in bankers_results:
        by_strat_b[r["strategy"]]["orig"].append(r["orig_sa"])
        by_strat_b[r["strategy"]]["valid"].append(r["valid_sa"])

    print("\n  Per-Strategy Breakdown (Banker's):")
    for st in ["zero_shot", "few_shot", "cot"]:
        if st in by_strat_b:
            o_m = sum(by_strat_b[st]["orig"]) / len(by_strat_b[st]["orig"])
            v_m = sum(by_strat_b[st]["valid"]) / len(by_strat_b[st]["valid"])
            print(f"    {st:10s}: Exact={o_m*100:5.1f}% | Valid={v_m*100:5.1f}% | Delta={(v_m - o_m)*100:+5.1f}%")

    # Summarize WFG
    mean_orig_w = sum(r["orig_sa"] for r in wfg_results) / len(wfg_results) if wfg_results else 0
    mean_valid_w = sum(r["valid_sa"] for r in wfg_results) / len(wfg_results) if wfg_results else 0
    mean_delta_w = sum(wfg_delta_sa) / len(wfg_delta_sa) if wfg_delta_sa else 0

    print("\n" + "=" * 60)
    print("WFG DFS EQUIVALENCE-AWARE SCORING (N = %d parsed)" % len(wfg_results))
    print("=" * 60)
    print(f"  Exact-Match SA (Positional):  {mean_orig_w * 100:.2f}%")
    print(f"  Equivalence-Aware Valid SA:   {mean_valid_w * 100:.2f}%")
    print(f"  Mean Delta (Valid - Exact):   {mean_delta_w * 100:+.2f}%")

    by_strat_w = defaultdict(lambda: {"orig": [], "valid": []})
    for r in wfg_results:
        by_strat_w[r["strategy"]]["orig"].append(r["orig_sa"])
        by_strat_w[r["strategy"]]["valid"].append(r["valid_sa"])

    print("\n  Per-Strategy Breakdown (WFG):")
    for st in ["zero_shot", "few_shot", "cot"]:
        if st in by_strat_w:
            o_m = sum(by_strat_w[st]["orig"]) / len(by_strat_w[st]["orig"])
            v_m = sum(by_strat_w[st]["valid"]) / len(by_strat_w[st]["valid"])
            print(f"    {st:10s}: Exact={o_m*100:5.1f}% | Valid={v_m*100:5.1f}% | Delta={(v_m - o_m)*100:+5.1f}%")

    # Save report
    report_data = {
        "bankers": {
            "n_parsed": len(bankers_results),
            "exact_sa": mean_orig_b,
            "valid_sa": mean_valid_b,
            "delta_sa": mean_delta_b,
            "alt_safe_seq_count": bankers_alt_safe_seq,
            "by_strategy": {
                st: {
                    "exact_sa": sum(by_strat_b[st]["orig"]) / len(by_strat_b[st]["orig"]),
                    "valid_sa": sum(by_strat_b[st]["valid"]) / len(by_strat_b[st]["valid"]),
                }
                for st in by_strat_b
            }
        },
        "wfg": {
            "n_parsed": len(wfg_results),
            "exact_sa": mean_orig_w,
            "valid_sa": mean_valid_w,
            "delta_sa": mean_delta_w,
            "by_strategy": {
                st: {
                    "exact_sa": sum(by_strat_w[st]["orig"]) / len(by_strat_w[st]["orig"]),
                    "valid_sa": sum(by_strat_w[st]["valid"]) / len(by_strat_w[st]["valid"]),
                }
                for st in by_strat_w
            }
        }
    }

    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)
    with open(OUTPUT_REPORT, "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"\nReport successfully saved to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
