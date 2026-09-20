#!/usr/bin/env python3
"""
reconcile_table2.py
===================
Resolves audit finding C1: Table II's N/denominator/parse columns don't reconcile.
Reads all raw score JSONs and produces exact counts per model.

Also extracts per-model WFG-specific metrics for fixing Figure 5 (C3).
"""

import json
import os
import glob

SCORES_DIR = os.path.join(os.path.dirname(__file__), "..", "results", "scores")
RESPONSES_DIR = os.path.join(os.path.dirname(__file__), "..", "svac_llm_responses")


def load_scores(path):
    with open(path) as f:
        return json.load(f)


def analyze_score_file(path):
    """Analyze a single score JSON file and extract all relevant counts."""
    data = load_scores(path)
    fname = os.path.basename(path)

    all_entries = []
    if isinstance(data, list):
        all_entries = data
    elif isinstance(data, dict):
        for task_name, task_data in data.items():
            if isinstance(task_data, dict):
                for variant_name, variant_data in task_data.items():
                    if isinstance(variant_data, list):
                        for entry in variant_data:
                            entry["_task"] = task_name
                            entry["_variant"] = variant_name
                            all_entries.append(entry)
                    elif isinstance(variant_data, dict):
                        variant_data["_task"] = task_name
                        variant_data["_variant"] = variant_name
                        all_entries.append(variant_data)

    if not all_entries:
        return None

    # Count the various categories
    total = len(all_entries)
    parsed_ok = sum(1 for e in all_entries if e.get("parse_success", False))
    has_response = sum(1 for e in all_entries if e.get("raw_response") is not None
                       or e.get("parse_success") is not None)

    # Compute metrics over parsed-only
    sa_values = [e.get("step_accuracy", 0.0) for e in all_entries if e.get("parse_success", False)]
    ecr_values = [e.get("error_cascade_rate", 0.0) for e in all_entries if e.get("parse_success", False)]
    va_values = [1 if e.get("verdict_correct", False) else 0 for e in all_entries if e.get("parse_success", False)]

    mean_sa = sum(sa_values) / len(sa_values) if sa_values else 0
    mean_ecr = sum(ecr_values) / len(ecr_values) if ecr_values else 0
    mean_va = sum(va_values) / len(va_values) if va_values else 0

    # Per-task breakdown
    tasks = {}
    for e in all_entries:
        task = e.get("_task", e.get("task", "unknown"))
        if task not in tasks:
            tasks[task] = {"total": 0, "parsed": 0, "sa": [], "ecr": [], "va": []}
        tasks[task]["total"] += 1
        if e.get("parse_success", False):
            tasks[task]["parsed"] += 1
            tasks[task]["sa"].append(e.get("step_accuracy", 0.0))
            tasks[task]["ecr"].append(e.get("error_cascade_rate", 0.0))
            tasks[task]["va"].append(1 if e.get("verdict_correct", False) else 0)

    # WFG-specific metrics for Figure 5 fix
    wfg_data = tasks.get("wfg", None)
    wfg_sa = sum(wfg_data["sa"]) / len(wfg_data["sa"]) if wfg_data and wfg_data["sa"] else None
    wfg_va = sum(wfg_data["va"]) / len(wfg_data["va"]) if wfg_data and wfg_data["va"] else None

    return {
        "file": fname,
        "total_entries": total,
        "responses_received": has_response,
        "parsed_ok": parsed_ok,
        "parse_rate": parsed_ok / total if total > 0 else 0,
        "mean_sa": mean_sa,
        "mean_ecr": mean_ecr,
        "mean_va": mean_va,
        "per_task": {
            task: {
                "total": d["total"],
                "parsed": d["parsed"],
                "parse_rate": d["parsed"] / d["total"] if d["total"] > 0 else 0,
                "mean_sa": sum(d["sa"]) / len(d["sa"]) if d["sa"] else None,
                "mean_ecr": sum(d["ecr"]) / len(d["ecr"]) if d["ecr"] else None,
                "mean_va": sum(d["va"]) / len(d["va"]) if d["va"] else None,
            }
            for task, d in tasks.items()
        },
        "wfg_sa": wfg_sa,
        "wfg_va": wfg_va,
    }


def main():
    # The score files that correspond to the paper's reported models
    target_files = {
        "Gemini-3.5-Flash-Lite": "gemini-3-5-flash-lite_20260819_203106_scores.json",
        "GPT-OSS-20B": "openai_gpt-oss-20b_20260821_203228_scores.json",
        "Nemotron-3-Super-120B": "nvidia_nemotron-3-super-120b-a12b_free_20260820_141907_scores.json",
        "LFM-2.6B": "liquid_lfm-2.5-2.6b_free_20260821_203235_scores.json",
    }

    print("=" * 100)
    print("TABLE II RECONCILIATION REPORT")
    print("Audit finding C1: Table II's N/denominator/parse columns don't reconcile")
    print("=" * 100)

    print("\n### STEP 1: What the paper reports vs what the data shows ###\n")
    paper_values = {
        "Gemini-3.5-Flash-Lite": {"N": "375/375", "Parse": "99.2%", "SA": "56.1%", "ECR": "36.9%", "VA": "72.3%"},
        "GPT-OSS-20B": {"N": "81/303", "Parse": "58.0%", "SA": "53.1%", "ECR": "45.3%", "VA": "58.0%"},
        "Nemotron-3-Super-120B": {"N": "113/375", "Parse": "19.7%", "SA": "48.5%", "ECR": "41.3%", "VA": "18.9%"},
        "LFM-2.6B": {"N": "39/189", "Parse": "69.2%", "SA": "14.4%", "ECR": "86.1%", "VA": "66.7%"},
    }

    for model_name, score_file in target_files.items():
        path = os.path.join(SCORES_DIR, score_file)
        if not os.path.exists(path):
            print(f"\n⚠ {model_name}: Score file not found: {score_file}")
            continue

        result = analyze_score_file(path)
        if result is None:
            print(f"\n⚠ {model_name}: Could not parse score file")
            continue

        paper = paper_values[model_name]
        print(f"\n{'='*60}")
        print(f"  {model_name}")
        print(f"{'='*60}")
        print(f"  Score file: {score_file}")
        print(f"  Total entries in JSON:    {result['total_entries']}")
        print(f"  Parsed OK:               {result['parsed_ok']}")
        print(f"  Parse rate:              {result['parse_rate']:.1%}")
        print(f"  Mean SA (parsed only):   {result['mean_sa']:.1%}")
        print(f"  Mean ECR (parsed only):  {result['mean_ecr']:.1%}")
        print(f"  Mean VA (parsed only):   {result['mean_va']:.1%}")
        print(f"  WFG-only SA:             {result['wfg_sa']:.1%}" if result['wfg_sa'] is not None else "  WFG-only SA:             N/A")
        print(f"  WFG-only VA:             {result['wfg_va']:.1%}" if result['wfg_va'] is not None else "  WFG-only VA:             N/A")
        print(f"\n  Paper reports:  N={paper['N']}  Parse={paper['Parse']}  SA={paper['SA']}  ECR={paper['ECR']}  VA={paper['VA']}")

        # Check consistency
        issues = []
        if f"{result['parse_rate']:.1%}" != paper["Parse"]:
            issues.append(f"Parse rate mismatch: data={result['parse_rate']:.1%}, paper={paper['Parse']}")
        if f"{result['mean_sa']:.1%}" != paper["SA"]:
            issues.append(f"SA mismatch: data={result['mean_sa']:.1%}, paper={paper['SA']}")

        if issues:
            print(f"\n  ⚠ ISSUES:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print(f"\n  ✓ All values match")

        # Per-task breakdown
        print(f"\n  Per-task breakdown:")
        for task, td in result["per_task"].items():
            sa_str = f"{td['mean_sa']:.1%}" if td['mean_sa'] is not None else "N/A"
            va_str = f"{td['mean_va']:.1%}" if td['mean_va'] is not None else "N/A"
            print(f"    {task:<12} total={td['total']:>3}  parsed={td['parsed']:>3}  "
                  f"parse_rate={td['parse_rate']:.1%}  SA={sa_str}  VA={va_str}")

    # Also count raw response files per model
    print(f"\n\n{'='*100}")
    print("STEP 2: Count raw LLM response files per model")
    print("(To determine 'attempted' vs 'received' vs 'scored')")
    print("=" * 100)

    for model_dir in sorted(os.listdir(RESPONSES_DIR)):
        dir_path = os.path.join(RESPONSES_DIR, model_dir)
        if not os.path.isdir(dir_path):
            continue
        # Count response files
        response_files = glob.glob(os.path.join(dir_path, "**", "*.json"), recursive=True)
        print(f"\n  {model_dir}: {len(response_files)} response files")
        # Count by task
        by_task = {}
        for rf in response_files:
            basename = os.path.basename(rf)
            # Try to determine task from path or filename
            parts = rf.split(os.sep)
            for part in parts:
                if part in ("wfg", "bankers", "buddy", "semaphore", "mutex"):
                    by_task[part] = by_task.get(part, 0) + 1
                    break
            else:
                by_task["unknown"] = by_task.get("unknown", 0) + 1
        for task, count in sorted(by_task.items()):
            print(f"    {task}: {count}")


if __name__ == "__main__":
    main()
