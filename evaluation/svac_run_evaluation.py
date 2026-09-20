"""
svac_run_evaluation.py
==========================
Phase 5: Alignment, Scoring & Reporting.

Discovers every saved LLM response for a given model, matches each one
back to its ground-truth instance, routes it to the correct scorer
(deadlock / buddy / sync) based on the task encoded in the filename, and
produces both a machine-readable JSON score file and a human-readable
text report -- mirroring run_evaluation.py / svac_scorer.py from the
original Page Replacement pipeline (results/reports/*.txt,
results/scores/*.json).

USAGE:
    python evaluation/svac_run_evaluation.py --model gemini-2-5-flash-lite
    python evaluation/svac_run_evaluation.py --model nvidia_nemotron-3-ultra_free
    python evaluation/svac_run_evaluation.py --model gemini-2-5-flash-lite --task wfg
    (run with no --model to see which model folders are available)

Run with no --model to see which model folders are available under
svac_llm_responses/.
"""

from __future__ import annotations
import json
import os
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "solvers"))
sys.path.insert(0, os.path.join(BASE_DIR, "evaluation"))

from svac_deadlock_scorer import score_response as score_deadlock
from svac_buddy_scorer import score_response as score_buddy
from svac_sync_scorer import score_response as score_sync

RESPONSES_DIR = os.path.join(BASE_DIR, "svac_llm_responses")
INSTANCES_DIR = os.path.join(BASE_DIR, "data", "instances")
REPORTS_DIR = os.path.join(BASE_DIR, "results", "reports")
SCORES_DIR = os.path.join(BASE_DIR, "results", "scores")

INSTANCE_FILES = {
    "wfg": "svac_wfg_instances.json",
    "bankers": "svac_bankers_instances.json",
    "buddy": "svac_buddy_instances.json",
    "semaphore": "svac_semaphore_instances.json",
    "mutex": "svac_mutex_instances.json",
}


# ══════════════════════════════════════════════════════════════════════════
# 1. BUILD AN instance_id -> (task, complexity_level, ground_truth) LOOKUP
# ══════════════════════════════════════════════════════════════════════════

def build_instance_lookup() -> Dict[str, Dict[str, Any]]:
    lookup = {}
    for task, filename in INSTANCE_FILES.items():
        path = os.path.join(INSTANCES_DIR, filename)
        if not os.path.exists(path):
            print(f"  WARNING: {path} not found -- skipping '{task}' instances "
                  f"(run the {task} generator first if this is unexpected)")
            continue
        with open(path) as f:
            instances = json.load(f)
        for inst in instances:
            lookup[inst["instance_id"]] = {
                "task": inst["task"],
                "complexity_level": inst["complexity_level"],
                "mode": inst.get("mode"),
                "ground_truth": inst["ground_truth"],
            }
    return lookup


# ══════════════════════════════════════════════════════════════════════════
# 2. ROUTE ONE RESPONSE FILE TO THE CORRECT SCORER
# ══════════════════════════════════════════════════════════════════════════

def score_one_response(task: str, gt: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    if task in ("wfg", "bankers"):
        return score_deadlock(task, gt, response_text)
    elif task == "buddy":
        return score_buddy(gt, response_text)
    elif task in ("semaphore", "mutex"):
        return score_sync(task, gt, response_text)
    else:
        raise ValueError(f"Unknown task: {task}")


# ══════════════════════════════════════════════════════════════════════════
# 3. DISCOVER AND SCORE ALL RESPONSES FOR ONE MODEL
# ══════════════════════════════════════════════════════════════════════════

def score_model_responses(model_slug: str, task_filter: Optional[str] = None,
                           variant_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    model_dir = os.path.join(RESPONSES_DIR, model_slug)
    if not os.path.isdir(model_dir):
        raise FileNotFoundError(
            f"No response folder at {model_dir}. Available model folders: "
            f"{os.listdir(RESPONSES_DIR) if os.path.isdir(RESPONSES_DIR) else '(none yet)'}"
        )

    lookup = build_instance_lookup()
    results = []

    for fname in sorted(os.listdir(model_dir)):
        if not fname.endswith(".json"):
            continue
        # filename pattern: {task}__{variant}__{instance_id}.json
        stem = fname[:-5]
        parts = stem.split("__")
        if len(parts) != 3:
            print(f"  SKIPPING malformed filename: {fname}")
            continue
        task, variant, instance_id = parts

        if task_filter and task != task_filter:
            continue
        if variant_filter and variant != variant_filter:
            continue

        if instance_id not in lookup:
            print(f"  WARNING: no ground truth found for instance_id={instance_id} "
                  f"(file: {fname}) -- skipping")
            continue

        with open(os.path.join(model_dir, fname)) as f:
            response_payload = json.load(f)

        response_text = response_payload.get("response_text", "")
        gt_entry = lookup[instance_id]
        gt = gt_entry["ground_truth"]

        score = score_one_response(task, gt, response_text)
        score.update({
            "instance_id": instance_id,
            "task": task,
            "variant": variant,
            "complexity_level": gt_entry["complexity_level"],
            "mode": gt_entry.get("mode"),
            "model_slug": model_slug,
            "response_meta": response_payload.get("meta", {}),
        })
        results.append(score)

    return results


# ══════════════════════════════════════════════════════════════════════════
# 4. AGGREGATION
# ══════════════════════════════════════════════════════════════════════════

def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def aggregate(results: List[Dict[str, Any]], group_keys: List[str]) -> List[Dict[str, Any]]:
    """Group results by the given keys (e.g. ['task'], ['task', 'variant'],
    ['complexity_level']) and compute mean SA / FEP / ECR, verdict accuracy,
    and parse-success rate per group."""
    groups = defaultdict(list)
    for r in results:
        key = tuple(r[k] for k in group_keys)
        groups[key].append(r)

    rows = []
    for key, group in sorted(groups.items()):
        n = len(group)
        sa_values = [r["step_accuracy"] for r in group if r.get("parse_success")]
        fep_values = [r["first_error_position"] for r in group
                      if r.get("parse_success") and r.get("first_error_position") is not None]
        ecr_values = [r["error_cascade_rate"] for r in group if r.get("parse_success")]
        n_parse_success = sum(1 for r in group if r.get("parse_success"))
        n_verdict_correct = sum(1 for r in group if r.get("verdict_correct"))

        row = dict(zip(group_keys, key))
        row.update({
            "n": n,
            "parse_success_rate": round(n_parse_success / n, 4) if n else 0.0,
            "mean_sa": round(_mean(sa_values), 4) if sa_values else None,
            "min_sa": round(min(sa_values), 4) if sa_values else None,
            "max_sa": round(max(sa_values), 4) if sa_values else None,
            "mean_fep": round(_mean(fep_values), 2) if fep_values else None,
            "mean_ecr": round(_mean(ecr_values), 4) if ecr_values else None,
            "verdict_accuracy": round(n_verdict_correct / n, 4) if n else 0.0,
        })
        rows.append(row)
    return rows


# ══════════════════════════════════════════════════════════════════════════
# 5. HUMAN-READABLE TEXT REPORT
# ══════════════════════════════════════════════════════════════════════════

def _format_table(rows: List[Dict[str, Any]], group_keys: List[str]) -> str:
    if not rows:
        return "  (no data)\n"
    headers = group_keys + ["N", "ParseOK", "MeanSA", "MinSA", "MaxSA", "MeanFEP", "MeanECR", "VerdictAcc"]
    lines = [" | ".join(headers)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        cells = [str(row[k]) for k in group_keys]
        cells += [
            str(row["n"]),
            f"{row['parse_success_rate']*100:.1f}%",
            f"{row['mean_sa']*100:.1f}%" if row["mean_sa"] is not None else "-",
            f"{row['min_sa']*100:.1f}%" if row["min_sa"] is not None else "-",
            f"{row['max_sa']*100:.1f}%" if row["max_sa"] is not None else "-",
            f"{row['mean_fep']:.1f}" if row["mean_fep"] is not None else "-",
            f"{row['mean_ecr']*100:.1f}%" if row["mean_ecr"] is not None else "-",
            f"{row['verdict_accuracy']*100:.1f}%",
        ]
        lines.append(" | ".join(cells))
    return "\n".join(lines) + "\n"


def write_text_report(model_slug: str, results: List[Dict[str, Any]], out_path: str):
    lines = []
    lines.append("=" * 78)
    lines.append(f"SVAC_Concurrency Evaluation Report")
    lines.append(f"Model: {model_slug}")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Total scored responses: {len(results)}")
    lines.append("=" * 78)

    lines.append("\n### AGGREGATE BY TASK ###\n")
    lines.append(_format_table(aggregate(results, ["task"]), ["task"]))

    lines.append("\n### AGGREGATE BY TASK x PROMPT VARIANT ###\n")
    lines.append(_format_table(aggregate(results, ["task", "variant"]), ["task", "variant"]))

    lines.append("\n### AGGREGATE BY COMPLEXITY LEVEL ###\n")
    lines.append(_format_table(aggregate(results, ["complexity_level"]), ["complexity_level"]))

    lines.append("\n### AGGREGATE BY TASK x COMPLEXITY LEVEL ###\n")
    lines.append(_format_table(aggregate(results, ["task", "complexity_level"]),
                                ["task", "complexity_level"]))

    lines.append("\n### OVERALL SUMMARY ###\n")
    overall = aggregate(results, [])  # single group, no keys -> empty tuple key
    # aggregate() with empty group_keys groups everything into one bucket
    if overall:
        row = overall[0]
        sa_str  = f"{row['mean_sa']*100:.1f}%" if row.get('mean_sa') is not None else "-"
        ecr_str = f"{row['mean_ecr']*100:.1f}%" if row.get('mean_ecr') is not None else "-"
        lines.append(f"N={row['n']}  ParseSuccess={row['parse_success_rate']*100:.1f}%  "
                      f"MeanSA={sa_str}  MeanECR={ecr_str}  "
                      f"VerdictAccuracy={row['verdict_accuracy']*100:.1f}%")

    report_text = "\n".join(lines)
    with open(out_path, "w") as f:
        f.write(report_text)
    return report_text


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def run(model_slug: str, task_filter: Optional[str] = None,
        variant_filter: Optional[str] = None):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(SCORES_DIR, exist_ok=True)

    print(f"Scoring responses for model: {model_slug}")
    if task_filter:
        print(f"  (filtered to task={task_filter})")
    if variant_filter:
        print(f"  (filtered to variant={variant_filter})")

    try:
        results = score_model_responses(model_slug, task_filter, variant_filter)
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        return
    print(f"Scored {len(results)} responses.\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scores_path = os.path.join(SCORES_DIR, f"{model_slug}_{timestamp}_scores.json")
    with open(scores_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Per-instance scores written to: {scores_path}")

    report_path = os.path.join(REPORTS_DIR, f"{model_slug}_{timestamp}_report.txt")
    report_text = write_text_report(model_slug, results, report_path)
    print(f"Report written to: {report_path}\n")
    print(report_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score all saved LLM responses for a model.")
    parser.add_argument("--model", required=False,
                         help="model_slug folder name under svac_llm_responses/ "
                              "(e.g. gemini-2-5-flash-lite)")
    parser.add_argument("--task", default=None,
                         choices=["wfg", "bankers", "buddy", "semaphore", "mutex"],
                         help="Only score this task (default: all)")
    parser.add_argument("--variant", default=None,
                         choices=["zero_shot", "few_shot", "cot"],
                         help="Only score this prompt variant (default: all)")
    args = parser.parse_args()

    if not args.model:
        if os.path.isdir(RESPONSES_DIR):
            available = [d for d in os.listdir(RESPONSES_DIR)
                         if os.path.isdir(os.path.join(RESPONSES_DIR, d))]
        else:
            available = []
        print("Please specify --model. Available model folders:")
        for m in available:
            n_files = len(os.listdir(os.path.join(RESPONSES_DIR, m)))
            print(f"  {m}  ({n_files} response files)")
        if not available:
            print("  (none yet -- run an api_callers script first)")
        sys.exit(1)

    run(args.model, args.task, args.variant)
