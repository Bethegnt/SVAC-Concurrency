#!/usr/bin/env python3
"""
parse_failure_analysis.py
=========================
Analyzes parse failure patterns across models, prompt strategies,
and complexity levels to quantify survivorship bias.

Addresses audit findings M10 (survivorship bias) and E10 (parse-failure
pattern unreported).

Also resolves the VA discrepancy: the evaluation pipeline counts parse
failures as verdict_correct=False, making VA = correct_verdicts/total
instead of correct_verdicts/parsed. This conflation is documented.
"""

import json
import os
from collections import defaultdict

SCORES_DIR = os.path.join(os.path.dirname(__file__), "..", "results", "scores")

MODELS = {
    "Gemini-3.5-Flash-Lite": "gemini-3-5-flash-lite_20260819_203106_scores.json",
    "GPT-OSS-20B": "openai_gpt-oss-20b_20260821_203228_scores.json",
    "Nemotron-3-120B": "nvidia_nemotron-3-super-120b-a12b_free_20260820_141907_scores.json",
    "LFM-2.6B": "liquid_lfm-2.5-2.6b_free_20260821_203235_scores.json",
}


def analyze_model(model_name, score_file):
    path = os.path.join(SCORES_DIR, score_file)
    if not os.path.exists(path):
        return None

    with open(path) as f:
        scores = json.load(f)

    total = len(scores)
    parsed = [s for s in scores if s.get("parse_success")]
    unparsed = [s for s in scores if not s.get("parse_success")]

    # VA discrepancy
    parsed_vc = sum(1 for s in parsed if s.get("verdict_correct"))
    total_vc = sum(1 for s in scores if s.get("verdict_correct"))

    # By task
    by_task = defaultdict(lambda: {"total": 0, "parsed": 0, "vc_parsed": 0})
    for s in scores:
        task = s.get("task", "unknown")
        by_task[task]["total"] += 1
        if s.get("parse_success"):
            by_task[task]["parsed"] += 1
            if s.get("verdict_correct"):
                by_task[task]["vc_parsed"] += 1

    # By variant
    by_variant = defaultdict(lambda: {"total": 0, "parsed": 0})
    for s in scores:
        variant = s.get("variant", "unknown")
        by_variant[variant]["total"] += 1
        if s.get("parse_success"):
            by_variant[variant]["parsed"] += 1

    # By complexity
    by_complexity = defaultdict(lambda: {"total": 0, "parsed": 0})
    for s in scores:
        level = s.get("complexity_level", "?")
        by_complexity[level]["total"] += 1
        if s.get("parse_success"):
            by_complexity[level]["parsed"] += 1

    # Parse failure by task × variant
    by_task_variant = defaultdict(lambda: {"total": 0, "parsed": 0})
    for s in scores:
        key = f"{s.get('task','?')} × {s.get('variant','?')}"
        by_task_variant[key]["total"] += 1
        if s.get("parse_success"):
            by_task_variant[key]["parsed"] += 1

    return {
        "model": model_name,
        "total": total,
        "parsed": len(parsed),
        "unparsed": len(unparsed),
        "parse_rate": len(parsed) / total if total > 0 else 0,
        "va_paper": total_vc / total if total > 0 else 0,       # what paper reports
        "va_true": parsed_vc / len(parsed) if len(parsed) > 0 else 0,  # among parsed
        "parsed_vc": parsed_vc,
        "by_task": dict(by_task),
        "by_variant": dict(by_variant),
        "by_complexity": dict(by_complexity),
        "by_task_variant": dict(by_task_variant),
    }


def main():
    print("=" * 90)
    print("SVAC-Concurrency: PARSE FAILURE & VA DISCREPANCY ANALYSIS")
    print("=" * 90)

    results = []
    for model_name, score_file in MODELS.items():
        result = analyze_model(model_name, score_file)
        if result:
            results.append(result)

    # VA Discrepancy Table
    print("\n### CRITICAL: Verdict Accuracy Conflation ###\n")
    print("The evaluation pipeline counts parse failures as verdict_correct=False.")
    print("This means VA_paper = correct_verdicts / total_entries (including unparsed).")
    print("VA_true = correct_verdicts / parsed_entries (only successfully parsed).\n")

    header = f"{'Model':<25} {'Total':>6} {'Parsed':>7} {'Parse%':>8} {'VA(paper)':>10} {'VA(true)':>10} {'Delta':>7}"
    print(header)
    print("-" * len(header))
    for r in results:
        delta = r["va_true"] - r["va_paper"]
        print(f"{r['model']:<25} {r['total']:>6} {r['parsed']:>7} "
              f"{r['parse_rate']:>8.1%} {r['va_paper']:>10.1%} {r['va_true']:>10.1%} "
              f"{'+' if delta >= 0 else ''}{delta:>6.1%}")

    # Parse failures by task × variant for each model
    for r in results:
        if r["parse_rate"] >= 0.99:
            continue  # skip models with near-perfect parse rates

        print(f"\n\n### {r['model']}: Parse Success by Task × Variant ###\n")
        for key, data in sorted(r["by_task_variant"].items()):
            rate = data["parsed"] / data["total"] if data["total"] > 0 else 0
            bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
            print(f"  {key:<30} {data['parsed']:>3}/{data['total']:>3} ({rate:>6.1%}) {bar}")

        print(f"\n  Parse Success by Complexity Level:")
        for level, data in sorted(r["by_complexity"].items()):
            rate = data["parsed"] / data["total"] if data["total"] > 0 else 0
            bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
            print(f"  Level {level}: {data['parsed']:>3}/{data['total']:>3} ({rate:>6.1%}) {bar}")

    # Survivorship bias summary
    print("\n\n### SURVIVORSHIP BIAS SUMMARY ###\n")
    print("Direction of bias for each model:")
    for r in results:
        if r["parse_rate"] >= 0.99:
            print(f"  {r['model']}: Minimal (99%+ parse success)")
            continue

        # Check if parse rate correlates with complexity
        levels = sorted(r["by_complexity"].keys())
        rates = [r["by_complexity"][l]["parsed"] / r["by_complexity"][l]["total"]
                 if r["by_complexity"][l]["total"] > 0 else 0 for l in levels]

        if len(rates) >= 2:
            trend = "decreasing" if rates[-1] < rates[0] else "increasing"
            print(f"  {r['model']}: Parse rate {trend} with complexity "
                  f"(L1={rates[0]:.0%} → L{levels[-1]}={rates[-1]:.0%}). "
                  f"SA/ECR metrics are biased toward {'easier' if trend == 'decreasing' else 'harder'} instances.")


if __name__ == "__main__":
    main()
