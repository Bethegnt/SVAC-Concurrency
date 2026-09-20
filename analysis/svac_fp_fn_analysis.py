"""
svac_fp_fn_analysis.py
========================
False Positive / False Negative analysis for WFG (deadlock detection) task.

For WFG instances: ground truth is binary — "deadlock_detected: true/false".
This script computes:
  - True Positive  (TP): model said deadlock, GT says deadlock
  - True Negative  (TN): model said no deadlock, GT says no deadlock
  - False Positive (FP): model said deadlock, GT says no deadlock
  - False Negative (FN): model said no deadlock, GT says deadlock
  - Precision, Recall, F1

Also analyses Banker's safe/unsafe classification.

USAGE:
    python analysis/svac_fp_fn_analysis.py
    python analysis/svac_fp_fn_analysis.py --model gemini-3-5-flash-lite
"""
from __future__ import annotations
import json
import os
import sys
import glob
import argparse
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "evaluation"))
SCORES_DIR = os.path.join(BASE_DIR, "results", "scores")
RESPONSES_DIR = os.path.join(BASE_DIR, "svac_llm_responses")
INSTANCES_DIR = os.path.join(BASE_DIR, "data", "instances")


def load_instances(task: str) -> dict:
    files = {
        "wfg":     "svac_wfg_instances.json",
        "bankers": "svac_bankers_instances.json",
    }
    path = os.path.join(INSTANCES_DIR, files[task])
    with open(path) as f:
        data = json.load(f)
    return {inst["instance_id"]: inst for inst in data}


def extract_verdict_from_response(raw_text: str, task: str) -> bool | None:
    """Extract model's binary verdict from raw response text."""
    import re
    text = raw_text.strip()

    # Try JSON first
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text_j = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        text_j = brace.group(0) if brace else None

    if text_j:
        try:
            d = json.loads(text_j)
            if task == "wfg":
                v = d.get("deadlock_detected") or d.get("has_cycle") or d.get("deadlock")
            else:  # bankers
                v = d.get("safe")
                if v is not None:
                    return bool(v)   # bankers: True=safe, we'll flip for consistency
                v = d.get("unsafe")
                if v is not None:
                    return not bool(v)
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "yes", "1", "deadlock", "unsafe")
        except (json.JSONDecodeError, AttributeError):
            pass

    # Fallback: keyword search in plain text
    lower = raw_text.lower()
    if task == "wfg":
        has_deadlock = any(p in lower for p in ["deadlock detected", "deadlock_detected\": true",
                                                  "cycle detected", "has cycle", "has_cycle\": true"])
        no_deadlock  = any(p in lower for p in ["no deadlock", "deadlock_detected\": false",
                                                  "no cycle", "has_cycle\": false"])
        if has_deadlock and not no_deadlock:
            return True
        if no_deadlock and not has_deadlock:
            return False
    return None  # could not determine


def analyse_task(model_slug: str, task: str) -> dict:
    instances = load_instances(task)
    resp_dir = os.path.join(RESPONSES_DIR, model_slug)

    results = []
    for fname in sorted(os.listdir(resp_dir)):
        if not fname.endswith(".json"):
            continue
        parts = fname[:-5].split("__")
        if len(parts) != 3 or parts[0] != task:
            continue
        ftask, variant, iid = parts

        inst = instances.get(iid)
        if not inst:
            continue

        gt = inst["ground_truth"]
        if task == "wfg":
            gt_positive = gt.get("deadlock_detected", False)
        else:
            # bankers: "safe" means no deadlock; unsafe = positive (deadlock-like)
            gt_positive = not gt.get("safe", True)

        with open(os.path.join(resp_dir, fname)) as f:
            resp = json.load(f)

        model_positive = extract_verdict_from_response(resp.get("response_text", ""), task)
        if model_positive is None:
            continue  # skip unparseable

        results.append({
            "instance_id": iid,
            "variant": variant,
            "complexity_level": inst["complexity_level"],
            "gt_positive": gt_positive,
            "model_positive": model_positive,
        })

    return results


def compute_metrics(results: list[dict]) -> dict:
    tp = sum(1 for r in results if r["gt_positive"] and r["model_positive"])
    tn = sum(1 for r in results if not r["gt_positive"] and not r["model_positive"])
    fp = sum(1 for r in results if not r["gt_positive"] and r["model_positive"])
    fn = sum(1 for r in results if r["gt_positive"] and not r["model_positive"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / len(results) if results else 0.0
    fpr       = fp / (fp + tn) if (fp + tn) > 0 else 0.0  # false positive rate

    return {"TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "Precision": round(precision, 3), "Recall": round(recall, 3),
            "F1": round(f1, 3), "Accuracy": round(accuracy, 3),
            "FPR": round(fpr, 3), "N": len(results)}


def print_table(header: str, metrics: dict):
    print(f"\n{'─'*50}")
    print(f"  {header}")
    print(f"{'─'*50}")
    conf = f"  TP={metrics['TP']}  TN={metrics['TN']}  FP={metrics['FP']}  FN={metrics['FN']}  (N={metrics['N']})"
    print(conf)
    print(f"  Accuracy  : {metrics['Accuracy']*100:.1f}%")
    print(f"  Precision : {metrics['Precision']*100:.1f}%  (when model says +, how often correct?)")
    print(f"  Recall    : {metrics['Recall']*100:.1f}%  (what fraction of + cases caught?)")
    print(f"  F1 Score  : {metrics['F1']*100:.1f}%")
    print(f"  FP Rate   : {metrics['FPR']*100:.1f}%  (over-prediction of deadlock/unsafe)")


def run(model_slug: str):
    print(f"\n{'='*60}")
    print(f"  FP/FN Analysis — Model: {model_slug}")
    print(f"{'='*60}")

    for task in ["wfg", "bankers"]:
        results = analyse_task(model_slug, task)
        if not results:
            print(f"\n[{task.upper()}] No data found.")
            continue

        # Overall
        overall = compute_metrics(results)
        print_table(f"{task.upper()} — Overall (N={overall['N']})", overall)

        # Per variant
        for variant in ["zero_shot", "few_shot", "cot"]:
            subset = [r for r in results if r["variant"] == variant]
            if subset:
                m = compute_metrics(subset)
                print(f"\n    [{variant}]  "
                      f"Acc={m['Accuracy']*100:.1f}%  "
                      f"FPR={m['FPR']*100:.1f}%  "
                      f"FNR={(1-m['Recall'])*100:.1f}%  "
                      f"F1={m['F1']*100:.1f}%")

        # Per complexity
        print(f"\n  Complexity Breakdown:")
        for c in sorted(set(r["complexity_level"] for r in results)):
            sub = [r for r in results if r["complexity_level"] == c]
            m = compute_metrics(sub)
            print(f"    Complexity {c}: "
                  f"Acc={m['Accuracy']*100:.1f}%  "
                  f"FP={m['FP']}  FN={m['FN']}  "
                  f"FPR={m['FPR']*100:.1f}%")

    # Save results
    out_path = os.path.join(BASE_DIR, "results", "reports",
                             f"{model_slug}_fp_fn_analysis.txt")
    sys.stdout.flush()
    print(f"\n✅ Analysis complete. (to save: redirect stdout > {out_path})")


def find_latest_model(model_slug=None):
    if model_slug:
        return model_slug
    dirs = [d for d in os.listdir(RESPONSES_DIR)
            if os.path.isdir(os.path.join(RESPONSES_DIR, d))]
    return sorted(dirs)[-1] if dirs else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None,
                        help="Model slug under svac_llm_responses/ (default: latest)")
    args = parser.parse_args()

    slug = find_latest_model(args.model)
    if not slug:
        print("No model response folders found.")
        sys.exit(1)

    run(slug)
