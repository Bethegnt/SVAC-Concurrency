"""
svac_buddy_scorer.py
========================
Aligns and scores raw LLM responses against ground truth for the Buddy
System module. Follows the exact conventions of svac_deadlock_scorer.py:

  - SA  (Step Accuracy): fraction of steps where ALL scored fields match
  - FEP (First Error Position): 1-indexed step of the first mismatch
  - ECR (Error Cascade Rate): fraction of steps AFTER FEP that are also wrong
  - Verdict-level checks (here: allocation_log / final_free_lists) tracked
    separately from step-level trace correctness, same "final answer masks
    reasoning errors" distinction used throughout SVAC.
  - A ParseError is recorded (never crashes) for malformed model JSON --
    such instances score SA=0 and are flagged for retry.

Reuses parse_model_response's exact strategy from svac_deadlock_scorer.py
(fence-stripping, greedy brace-matching fallback).
"""

from __future__ import annotations
import json
import re
from typing import Dict, Any, List, Optional


class ParseError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════
# STEP 1: PARSE RAW MODEL OUTPUT INTO A JSON OBJECT
# (identical strategy to svac_deadlock_scorer.py -- kept local/duplicated
#  rather than imported, so each module's evaluation script stays fully
#  standalone and runnable in isolation, matching the original SVAC
#  convention of one self-contained scorer script per algorithm family.)
# ══════════════════════════════════════════════════════════════════════════

def parse_model_response(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()

    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid JSON: {e}")


# ══════════════════════════════════════════════════════════════════════════
# STEP 2: FIELD NORMALIZATION HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _normalize_free_lists(value) -> Optional[dict]:
    """
    Normalize a free_lists dict so equivalent states compare equal
    regardless of key type (str vs int) or address ordering within a list.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    try:
        return {str(k): sorted(v) for k, v in value.items() if v}
    except TypeError:
        return None


# ══════════════════════════════════════════════════════════════════════════
# STEP 3: BUDDY SYSTEM ERROR TAXONOMY + STEP SCORING
# ══════════════════════════════════════════════════════════════════════════

BUDDY_ERROR_TAXONOMY = {
    "wrong_action":            "action field mismatch at this step (e.g. said "
                                "'alloc_placement' when ground truth is 'split')",
    "wrong_block_addr":        "block_addr does not match ground truth",
    "wrong_block_size":        "block_size does not match ground truth",
    "free_list_corruption":    "free_lists snapshot does not match ground truth after this step",
    "wrong_buddy_addr":        "buddy_addr mismatch on a split or coalesce step",
    "wrong_split_size":        "resulting_block_size mismatch on a split step",
    "wrong_merge_level":       "merged_from_size mismatch on a coalesce step",
    "missed_coalesce":         "ground truth coalesces at this point but model reports "
                                "free_settled without merging (or vice versa)",
    "invalid_op_misclassified":"model failed to correctly identify a double_free / "
                                "free_unknown_request / free_failed_request edge case",
    "wrong_allocation_log":    "final allocation_log does not match ground truth",
    "wrong_final_free_lists":  "final_free_lists does not match ground truth",
    "step_count_mismatch":     "model produced a different number of steps than ground truth",
}

_INVALID_OP_ACTIONS = {"double_free", "free_unknown_request", "free_failed_request"}


def score_buddy_instance(gt: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    gt_steps = gt["steps"]
    model_steps = model_output.get("steps", [])

    errors_by_type = {k: 0 for k in BUDDY_ERROR_TAXONOMY}
    step_results = []

    n_compare = min(len(gt_steps), len(model_steps))
    if len(gt_steps) != len(model_steps):
        errors_by_type["step_count_mismatch"] += 1

    for i in range(n_compare):
        gt_step = gt_steps[i]
        m_step = model_steps[i]
        step_correct = True
        step_errors = []

        gt_action = gt_step.get("action")
        m_action = m_step.get("action")

        if m_action != gt_action:
            step_correct = False
            step_errors.append("wrong_action")
            errors_by_type["wrong_action"] += 1
            if gt_action in _INVALID_OP_ACTIONS or m_action in _INVALID_OP_ACTIONS:
                errors_by_type["invalid_op_misclassified"] += 1

        if m_step.get("block_addr") != gt_step.get("block_addr"):
            step_correct = False
            step_errors.append("wrong_block_addr")
            errors_by_type["wrong_block_addr"] += 1

        if m_step.get("block_size") != gt_step.get("block_size"):
            step_correct = False
            step_errors.append("wrong_block_size")
            errors_by_type["wrong_block_size"] += 1

        if _normalize_free_lists(m_step.get("free_lists")) != _normalize_free_lists(gt_step.get("free_lists")):
            step_correct = False
            step_errors.append("free_list_corruption")
            errors_by_type["free_list_corruption"] += 1

        if gt_action == "split":
            if m_step.get("buddy_addr") != gt_step.get("buddy_addr"):
                step_correct = False
                step_errors.append("wrong_buddy_addr")
                errors_by_type["wrong_buddy_addr"] += 1
            if m_step.get("resulting_block_size") != gt_step.get("resulting_block_size"):
                step_correct = False
                step_errors.append("wrong_split_size")
                errors_by_type["wrong_split_size"] += 1

        if gt_action == "coalesce":
            if m_step.get("buddy_addr") != gt_step.get("buddy_addr"):
                step_correct = False
                step_errors.append("wrong_buddy_addr")
                errors_by_type["wrong_buddy_addr"] += 1
            if m_step.get("merged_from_size") != gt_step.get("merged_from_size"):
                step_correct = False
                step_errors.append("wrong_merge_level")
                errors_by_type["wrong_merge_level"] += 1

        if gt_action == "free_settled" and m_action == "free_settled":
            # A subtle failure mode: model correctly labels the LAST step
            # "free_settled" but its block_size there doesn't reflect the
            # merges it should have performed earlier (checked via block_size
            # already above, but flagged separately here for the taxonomy).
            if m_step.get("block_size") != gt_step.get("block_size"):
                errors_by_type["missed_coalesce"] += 1

        step_results.append({"step": i + 1, "correct": step_correct, "errors": step_errors})

    # ── Final-state (verdict-level) checks, separate from step-level trace ──
    allocation_log_correct = (model_output.get("allocation_log") == gt.get("allocation_log"))
    if not allocation_log_correct:
        errors_by_type["wrong_allocation_log"] += 1

    final_free_lists_correct = (
        _normalize_free_lists(model_output.get("final_free_lists")) ==
        _normalize_free_lists(gt.get("final_free_lists"))
    )
    if not final_free_lists_correct:
        errors_by_type["wrong_final_free_lists"] += 1

    verdict_correct = allocation_log_correct and final_free_lists_correct

    return _compute_metrics(step_results, errors_by_type, verdict_correct, n_total_gt=len(gt_steps))


# ══════════════════════════════════════════════════════════════════════════
# SHARED METRIC COMPUTATION (identical formula to svac_deadlock_scorer.py)
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
        "n_steps_compared": len(step_results),
        "n_steps_ground_truth": n_total_gt,
    }


# ══════════════════════════════════════════════════════════════════════════
# TOP-LEVEL ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

def score_response(gt: Dict[str, Any], raw_model_text: str) -> Dict[str, Any]:
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

    result = score_buddy_instance(gt, model_output)
    result["parse_success"] = True
    return result


# ══════════════════════════════════════════════════════════════════════════
# SELF-TEST: score a perfect response, a broken response, and malformed JSON
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "solvers"))
    from svac_buddy_solver import solve_buddy_system

    gt = solve_buddy_system(
        total_memory=8, min_block_size=2,
        operations=[
            {"op": "alloc", "request_id": "A", "size": 3},
            {"op": "free", "request_id": "A"},
        ],
    )

    print("=" * 70)
    print("TEST A: PERFECT model response (should score SA=1.0, verdict_correct=True)")
    print("=" * 70)
    perfect_response = json.dumps({
        "steps": gt["steps"],
        "allocation_log": gt["allocation_log"],
        "final_free_lists": gt["final_free_lists"],
    })
    result_a = score_response(gt, perfect_response)
    print(json.dumps(result_a, indent=2))
    assert result_a["step_accuracy"] == 1.0
    assert result_a["verdict_correct"] is True
    assert result_a["error_cascade_rate"] == 0.0
    print("PASS\n")

    print("=" * 70)
    print("TEST B: BROKEN response — model reports free_settled WITHOUT")
    print("performing the coalesce (a classic 'missed_coalesce' failure)")
    print("=" * 70)
    broken_response = json.dumps({
        "steps": [
            gt["steps"][0],  # split -- correct
            gt["steps"][1],  # alloc_placement -- correct
            gt["steps"][2],  # free_placement -- correct
            # MISSING the coalesce step -- jumps straight to a (wrong) free_settled
            {"step": 4, "op_index": 1, "request_id": "A", "action": "free_settled",
             "block_addr": 0, "block_size": 4,  # should be 8 after coalescing!
             "free_lists": {"4": [0, 4]}},
        ],
        "allocation_log": {"A": {"address": 0, "block_size": 4, "status": "freed"}},
        "final_free_lists": {"4": [0, 4]},  # wrong -- should have coalesced to {"8": [0]}
    })
    result_b = score_response(gt, broken_response)
    print(json.dumps(result_b, indent=2))
    # The model SKIPPED the coalesce step entirely, so everything from that
    # point on misaligns positionally against ground truth. This should be
    # caught via step_count_mismatch (4 steps vs GT's 5), wrong_action (GT's
    # step 4 is "coalesce" but model's step 4 is "free_settled"), and a wrong
    # final_free_lists / verdict -- exactly the signal a real missed-coalesce
    # bug should produce, even though it doesn't land in the narrower
    # "missed_coalesce" taxonomy bucket (that bucket is reserved for the case
    # where the model correctly LABELS the final step "free_settled" at the
    # matching position but reports the wrong post-coalesce size there).
    assert result_b["verdict_correct"] is False
    assert result_b["errors_by_type"]["step_count_mismatch"] == 1  # 4 steps vs gt's 5
    assert result_b["errors_by_type"]["wrong_action"] >= 1
    assert result_b["errors_by_type"]["wrong_final_free_lists"] == 1
    assert result_b["step_accuracy"] < 1.0
    print("PASS\n")

    print("=" * 70)
    print("TEST B2: narrower case — model correctly labels the LAST step")
    print("'free_settled' at the right position, but reports the WRONG size")
    print("there (i.e. claims it settled at size 4 instead of the coalesced 8)")
    print("=" * 70)
    broken_response_b2 = json.dumps({
        "steps": [
            gt["steps"][0],  # split -- correct
            gt["steps"][1],  # alloc_placement -- correct
            gt["steps"][2],  # free_placement -- correct
            gt["steps"][3],  # coalesce -- correct
            # step 5 (index 4): mislabels the settle size as 4 instead of 8
            {"step": 5, "op_index": 1, "request_id": "A", "action": "free_settled",
             "block_addr": 0, "block_size": 4, "free_lists": {"8": [0]}},
        ],
        "allocation_log": {"A": {"address": 0, "block_size": 4, "status": "freed"}},
        "final_free_lists": {"8": [0]},
    })
    result_b2 = score_response(gt, broken_response_b2)
    print(json.dumps(result_b2, indent=2))
    assert result_b2["errors_by_type"]["missed_coalesce"] >= 1
    print("PASS\n")

    print("=" * 70)
    print("TEST C: MALFORMED JSON (should be caught as parse error, not crash)")
    print("=" * 70)
    result_c = score_response(gt, "I'll trace this now... { totally not json")
    print(json.dumps(result_c, indent=2))
    assert result_c["parse_success"] is False
    print("PASS\n")

    print("ALL SELF-TESTS PASSED.")
