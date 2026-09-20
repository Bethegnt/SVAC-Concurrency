"""
svac_deadlock_scorer.py
==========================
Aligns and scores raw LLM responses against ground truth for both
Deadlock Detection sub-tasks (WFG cycle detection, Banker's Algorithm).

Mirrors the metrics used in Paper 4 (Page Replacement):
  - SA  (Step Accuracy): fraction of steps where ALL scored fields match
  - FEP (First Error Position): 1-indexed step of the first mismatch
  - ECR (Error Cascade Rate): fraction of steps AFTER FEP that are also wrong
  - Verdict Accuracy: whether the FINAL answer (deadlock/safe) is correct,
    tracked separately since a model can get the final verdict right while
    being wrong on intermediate steps (or vice versa) -- this is the same
    "final answer masks reasoning errors" distinction SVAC uses elsewhere.

A ParseError is raised (and recorded, not crashed on) for malformed model
JSON -- these instances score SA=0 and are flagged for retry, same
convention as svac_aligner.py in Paper 4.
"""

from __future__ import annotations
import json
import re
from typing import Dict, Any, List, Optional


class ParseError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════
# STEP 1: PARSE RAW MODEL OUTPUT INTO A JSON OBJECT
# ══════════════════════════════════════════════════════════════════════════

def parse_model_response(raw_text: str) -> Dict[str, Any]:
    """
    Extract a JSON object from the model's raw response text.
    Handles the common cases: clean JSON, JSON wrapped in ```json fences,
    or JSON with leading/trailing prose the model added despite instructions.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Fallback: grab the first {...} block greedily
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid JSON: {e}")


# ══════════════════════════════════════════════════════════════════════════
# STEP 2: WFG SCORING
# ══════════════════════════════════════════════════════════════════════════

WFG_STEP_FIELDS = ["action", "node", "visited_set", "recursion_stack"]

WFG_ERROR_TAXONOMY = {
    "false_cycle":              "Model declared deadlock=true when ground truth is false",
    "missed_cycle":              "Model declared deadlock=false when ground truth is true",
    "wrong_action":               "action field (visit/backtrack/cycle_detected) mismatch",
    "wrong_node":                 "node field mismatch",
    "visited_set_corruption":     "visited_set does not match ground truth at this step",
    "recursion_stack_corruption": "recursion_stack does not match ground truth at this step",
    "wrong_cycle_nodes":          "cycle_nodes list mismatch when a cycle was correctly found",
    "step_count_mismatch":        "model produced a different number of steps than ground truth",
}


def _normalize_set_field(value) -> Optional[list]:
    if value is None:
        return None
    try:
        return sorted(value)
    except TypeError:
        return None


def score_wfg_instance(gt: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    gt_steps = gt["steps"]
    model_steps = model_output.get("steps", [])

    errors_by_type = {k: 0 for k in WFG_ERROR_TAXONOMY}
    step_results = []

    n_compare = min(len(gt_steps), len(model_steps))
    if len(gt_steps) != len(model_steps):
        errors_by_type["step_count_mismatch"] += 1

    for i in range(n_compare):
        gt_step = gt_steps[i]
        m_step = model_steps[i]
        step_correct = True
        step_errors = []

        if m_step.get("action") != gt_step.get("action"):
            step_correct = False
            step_errors.append("wrong_action")
            errors_by_type["wrong_action"] += 1

        if m_step.get("node") != gt_step.get("node"):
            step_correct = False
            step_errors.append("wrong_node")
            errors_by_type["wrong_node"] += 1

        if _normalize_set_field(m_step.get("visited_set")) != _normalize_set_field(gt_step.get("visited_set")):
            step_correct = False
            step_errors.append("visited_set_corruption")
            errors_by_type["visited_set_corruption"] += 1

        if m_step.get("recursion_stack") != gt_step.get("recursion_stack"):
            step_correct = False
            step_errors.append("recursion_stack_corruption")
            errors_by_type["recursion_stack_corruption"] += 1

        if gt_step.get("action") == "cycle_detected":
            if m_step.get("cycle") != gt_step.get("cycle"):
                step_correct = False
                step_errors.append("wrong_cycle_nodes")
                errors_by_type["wrong_cycle_nodes"] += 1

        step_results.append({"step": i + 1, "correct": step_correct, "errors": step_errors})

    # Verdict-level check (separate from step-level trace correctness)
    verdict_correct = (model_output.get("deadlock") == gt.get("deadlock"))
    if gt.get("deadlock") is False and model_output.get("deadlock") is True:
        errors_by_type["false_cycle"] += 1
    if gt.get("deadlock") is True and model_output.get("deadlock") is False:
        errors_by_type["missed_cycle"] += 1

    return _compute_metrics(step_results, errors_by_type, verdict_correct, n_total_gt=len(gt_steps))


# ══════════════════════════════════════════════════════════════════════════
# STEP 3: BANKER'S ALGORITHM SCORING
# ══════════════════════════════════════════════════════════════════════════

BANKERS_ERROR_TAXONOMY = {
    "wrong_safety_verdict":   "Model's safe/unsafe verdict does not match ground truth",
    "wrong_candidate_process": "candidate_process index mismatch at this step",
    "work_vector_drift":       "work_before or work_after does not match ground truth",
    "finish_array_corruption": "finish[] array does not match ground truth at this step",
    "wrong_need_row":          "need_row mismatch for the chosen candidate",
    "wrong_safe_sequence":     "Final safe_sequence order does not match ground truth",
    "step_count_mismatch":     "model produced a different number of steps than ground truth",
}


def score_bankers_instance(gt: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    gt_steps = gt["steps"]
    model_steps = model_output.get("steps", [])

    errors_by_type = {k: 0 for k in BANKERS_ERROR_TAXONOMY}
    step_results = []

    n_compare = min(len(gt_steps), len(model_steps))
    if len(gt_steps) != len(model_steps):
        errors_by_type["step_count_mismatch"] += 1

    for i in range(n_compare):
        gt_step = gt_steps[i]
        m_step = model_steps[i]
        step_correct = True
        step_errors = []

        if m_step.get("candidate_process") != gt_step.get("candidate_process"):
            step_correct = False
            step_errors.append("wrong_candidate_process")
            errors_by_type["wrong_candidate_process"] += 1

        if (m_step.get("work_before") != gt_step.get("work_before") or
                m_step.get("work_after") != gt_step.get("work_after")):
            step_correct = False
            step_errors.append("work_vector_drift")
            errors_by_type["work_vector_drift"] += 1

        if m_step.get("finish") != gt_step.get("finish"):
            step_correct = False
            step_errors.append("finish_array_corruption")
            errors_by_type["finish_array_corruption"] += 1

        if gt_step.get("need_row") is not None and m_step.get("need_row") != gt_step.get("need_row"):
            step_correct = False
            step_errors.append("wrong_need_row")
            errors_by_type["wrong_need_row"] += 1

        step_results.append({"step": i + 1, "correct": step_correct, "errors": step_errors})

    verdict_correct = (model_output.get("safe") == gt.get("safe"))
    if not verdict_correct:
        errors_by_type["wrong_safety_verdict"] += 1

    if gt.get("safe") and model_output.get("safe_sequence") != gt.get("safe_sequence"):
        errors_by_type["wrong_safe_sequence"] += 1

    return _compute_metrics(step_results, errors_by_type, verdict_correct, n_total_gt=len(gt_steps))


# ══════════════════════════════════════════════════════════════════════════
# SHARED METRIC COMPUTATION (SA / FEP / ECR)
# ══════════════════════════════════════════════════════════════════════════

def _compute_metrics(step_results: List[Dict], errors_by_type: Dict[str, int],
                      verdict_correct: bool, n_total_gt: int) -> Dict[str, Any]:
    if not step_results:
        return {
            "step_accuracy": 0.0,
            "first_error_position": 1,
            "error_cascade_rate": 1.0,
            "verdict_correct": verdict_correct,
            "errors_by_type": errors_by_type,
            "n_steps_compared": 0,
            "n_steps_ground_truth": n_total_gt,
        }

    n = len(step_results)
    n_correct = sum(1 for s in step_results if s["correct"])
    step_accuracy = n_correct / n_total_gt if n_total_gt else 0.0

    fep = None
    for s in step_results:
        if not s["correct"]:
            fep = s["step"]
            break

    if fep is None:
        ecr = 0.0
    else:
        post_fep = [s for s in step_results if s["step"] > fep]
        ecr = (sum(1 for s in post_fep if not s["correct"]) / len(post_fep)) if post_fep else 0.0

    return {
        "step_accuracy": round(step_accuracy, 4),
        "first_error_position": fep,
        "error_cascade_rate": round(ecr, 4),
        "verdict_correct": verdict_correct,
        "errors_by_type": errors_by_type,
        "n_steps_compared": n,
        "n_steps_ground_truth": n_total_gt,
    }


# ══════════════════════════════════════════════════════════════════════════
# TOP-LEVEL ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

def score_response(task: str, gt: Dict[str, Any], raw_model_text: str) -> Dict[str, Any]:
    """
    task: "wfg" or "bankers"
    gt: the "ground_truth" dict from the instance
    raw_model_text: the raw text returned by the LLM API
    """
    try:
        model_output = parse_model_response(raw_model_text)
    except ParseError as e:
        return {
            "parse_success": False,
            "parse_error": str(e),
            "step_accuracy": 0.0,
            "first_error_position": 1,
            "error_cascade_rate": 1.0,
            "verdict_correct": False,
        }

    if task == "wfg":
        result = score_wfg_instance(gt, model_output)
    elif task == "bankers":
        result = score_bankers_instance(gt, model_output)
    else:
        raise ValueError(f"Unknown task: {task}")

    result["parse_success"] = True
    return result


# ══════════════════════════════════════════════════════════════════════════
# SELF-TEST: score a perfect response and a deliberately broken response
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "solvers"))
    from svac_deadlock_solver import solve_wfg_cycle_detection

    gt = solve_wfg_cycle_detection(
        processes=["P0", "P1", "P2"],
        edges={"P0": ["P1"], "P1": ["P2"], "P2": ["P0"]},
    )

    print("=" * 70)
    print("TEST A: PERFECT model response (should score SA=1.0)")
    print("=" * 70)
    perfect_response = json.dumps({
        "steps": gt["steps"],
        "deadlock": gt["deadlock"],
        "cycle_nodes": gt["cycle_nodes"],
    })
    result_a = score_response("wfg", gt, perfect_response)
    print(json.dumps(result_a, indent=2))

    print("\n" + "=" * 70)
    print("TEST B: BROKEN model response (missed the cycle -> should show errors)")
    print("=" * 70)
    broken_response = json.dumps({
        "steps": [
            {"step": 1, "action": "visit", "node": "P0", "visited_set": ["P0"], "recursion_stack": ["P0"]},
            {"step": 2, "action": "visit", "node": "P1", "visited_set": ["P0", "P1"], "recursion_stack": ["P0", "P1"]},
            {"step": 3, "action": "backtrack", "node": "P1", "visited_set": ["P0", "P1"], "recursion_stack": ["P0"]},
        ],
        "deadlock": False,
        "cycle_nodes": None,
    })
    result_b = score_response("wfg", gt, broken_response)
    print(json.dumps(result_b, indent=2))

    print("\n" + "=" * 70)
    print("TEST C: MALFORMED JSON (should be caught as parse error, not crash)")
    print("=" * 70)
    result_c = score_response("wfg", gt, "Sure! Here is my answer: {not valid json...")
    print(json.dumps(result_c, indent=2))
