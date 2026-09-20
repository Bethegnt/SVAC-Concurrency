"""
svac_sync_scorer.py
========================
Aligns and scores raw LLM responses against ground truth for both
Process Synchronization sub-tasks (Semaphore, Mutex). Follows the exact
conventions of svac_deadlock_scorer.py and svac_buddy_scorer.py:

  - SA  (Step Accuracy): fraction of steps where ALL scored fields match
  - FEP (First Error Position): 1-indexed step of the first mismatch
  - ECR (Error Cascade Rate): fraction of steps AFTER FEP that are also wrong
  - Verdict-level checks (final state) tracked separately from step-level
    trace correctness.
  - A ParseError is recorded (never crashes) for malformed model JSON.
"""

from __future__ import annotations
import json
import re
from typing import Dict, Any, List, Optional


class ParseError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════
# STEP 1: PARSE RAW MODEL OUTPUT (identical strategy to sibling scorers)
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
# STEP 2: SEMAPHORE ERROR TAXONOMY + SCORING
# ══════════════════════════════════════════════════════════════════════════

SEMAPHORE_ERROR_TAXONOMY = {
    "wrong_action":              "action field mismatch at this step",
    "value_drift":                "value_before or value_after does not match ground truth",
    "blocked_queue_corruption":   "blocked_queue_before or blocked_queue_after mismatch",
    "wrong_woken_thread":         "woken_thread mismatch on a signal_handoff step",
    "missed_handoff":             "ground truth performs a handoff here but model incremented "
                                   "value instead (or vice versa)",
    "invalid_over_signal_missed": "model failed to flag an invalid_over_signal edge case "
                                   "(or falsely flagged one that is not present)",
    "wrong_final_state":          "final_value / final_blocked_queue / thread_final_state mismatch",
    "step_count_mismatch":        "model produced a different number of steps than ground truth",
}


def score_semaphore_instance(gt: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    gt_steps = gt["steps"]
    model_steps = model_output.get("steps", [])

    errors_by_type = {k: 0 for k in SEMAPHORE_ERROR_TAXONOMY}
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
            if gt_action == "signal_handoff" or m_action == "signal_handoff":
                errors_by_type["missed_handoff"] += 1
            if gt_action == "invalid_over_signal" or m_action == "invalid_over_signal":
                errors_by_type["invalid_over_signal_missed"] += 1

        if (m_step.get("value_before") != gt_step.get("value_before") or
                m_step.get("value_after") != gt_step.get("value_after")):
            step_correct = False
            step_errors.append("value_drift")
            errors_by_type["value_drift"] += 1

        if (m_step.get("blocked_queue_before") != gt_step.get("blocked_queue_before") or
                m_step.get("blocked_queue_after") != gt_step.get("blocked_queue_after")):
            step_correct = False
            step_errors.append("blocked_queue_corruption")
            errors_by_type["blocked_queue_corruption"] += 1

        if gt_action == "signal_handoff":
            if m_step.get("woken_thread") != gt_step.get("woken_thread"):
                step_correct = False
                step_errors.append("wrong_woken_thread")
                errors_by_type["wrong_woken_thread"] += 1

        step_results.append({"step": i + 1, "correct": step_correct, "errors": step_errors})

    # thread_final_state: check only GT-tracked threads (model may include extra
    # threads that never acquired the semaphore and are therefore absent from GT)
    gt_tfs = gt.get("thread_final_state") or {}
    model_tfs = model_output.get("thread_final_state") or {}
    tfs_correct = all(model_tfs.get(t) == state for t, state in gt_tfs.items())

    verdict_correct = (
        model_output.get("final_value") == gt.get("final_value") and
        model_output.get("final_blocked_queue") == gt.get("final_blocked_queue") and
        tfs_correct
    )
    if not verdict_correct:
        errors_by_type["wrong_final_state"] += 1

    return _compute_metrics(step_results, errors_by_type, verdict_correct, n_total_gt=len(gt_steps))


# ══════════════════════════════════════════════════════════════════════════
# STEP 3: MUTEX ERROR TAXONOMY + SCORING
# ══════════════════════════════════════════════════════════════════════════

MUTEX_ERROR_TAXONOMY = {
    "wrong_action":               "action field mismatch at this step",
    "owner_corruption":            "owner_before or owner_after does not match ground truth",
    "wait_queue_corruption":       "wait_queue_before or wait_queue_after mismatch",
    "wrong_woken_thread":          "woken_thread mismatch on an unlock_release_handoff step",
    "missed_self_deadlock":        "model failed to detect a thread relocking a mutex it "
                                    "already owns (or falsely flagged one that isn't present)",
    "invalid_unlock_misclassified":"model failed to flag an invalid_unlock (wrong owner or "
                                    "no owner) or falsely flagged a valid unlock as invalid",
    "wrong_final_state":           "final_owner / final_wait_queue / thread_final_state mismatch",
    "step_count_mismatch":         "model produced a different number of steps than ground truth",
}


def score_mutex_instance(gt: Dict[str, Any], model_output: Dict[str, Any]) -> Dict[str, Any]:
    gt_steps = gt["steps"]
    model_steps = model_output.get("steps", [])

    errors_by_type = {k: 0 for k in MUTEX_ERROR_TAXONOMY}
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
            if gt_action == "lock_self_deadlock" or m_action == "lock_self_deadlock":
                errors_by_type["missed_self_deadlock"] += 1
            if gt_action == "invalid_unlock" or m_action == "invalid_unlock":
                errors_by_type["invalid_unlock_misclassified"] += 1

        if (m_step.get("owner_before") != gt_step.get("owner_before") or
                m_step.get("owner_after") != gt_step.get("owner_after")):
            step_correct = False
            step_errors.append("owner_corruption")
            errors_by_type["owner_corruption"] += 1

        if (m_step.get("wait_queue_before") != gt_step.get("wait_queue_before") or
                m_step.get("wait_queue_after") != gt_step.get("wait_queue_after")):
            step_correct = False
            step_errors.append("wait_queue_corruption")
            errors_by_type["wait_queue_corruption"] += 1

        if gt_action == "unlock_release_handoff":
            if m_step.get("woken_thread") != gt_step.get("woken_thread"):
                step_correct = False
                step_errors.append("wrong_woken_thread")
                errors_by_type["wrong_woken_thread"] += 1

        step_results.append({"step": i + 1, "correct": step_correct, "errors": step_errors})

    # thread_final_state: check only GT-tracked threads (model may include
    # extra threads that only did invalid_unlock and were never owned the mutex,
    # so they are absent from GT's thread_final_state dict)
    gt_tfs = gt.get("thread_final_state") or {}
    model_tfs = model_output.get("thread_final_state") or {}
    tfs_correct = all(model_tfs.get(t) == state for t, state in gt_tfs.items())

    verdict_correct = (
        model_output.get("final_owner") == gt.get("final_owner") and
        model_output.get("final_wait_queue") == gt.get("final_wait_queue") and
        tfs_correct
    )
    if not verdict_correct:
        errors_by_type["wrong_final_state"] += 1

    return _compute_metrics(step_results, errors_by_type, verdict_correct, n_total_gt=len(gt_steps))


# ══════════════════════════════════════════════════════════════════════════
# SHARED METRIC COMPUTATION (identical formula to sibling scorers)
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

def score_response(task: str, gt: Dict[str, Any], raw_model_text: str) -> Dict[str, Any]:
    """
    task: "semaphore" or "mutex"
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

    if task == "semaphore":
        result = score_semaphore_instance(gt, model_output)
    elif task == "mutex":
        result = score_mutex_instance(gt, model_output)
    else:
        raise ValueError(f"Unknown task: {task}")

    result["parse_success"] = True
    return result


# ══════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "solvers"))
    from svac_sync_solver import solve_semaphore_trace, solve_mutex_trace

    # --- SEMAPHORE TESTS ---
    sem_gt = solve_semaphore_trace(
        initial_value=0,
        operations=[{"thread": "T0", "op": "wait"}, {"thread": "T1", "op": "signal"}],
    )

    print("=" * 70)
    print("TEST A: PERFECT semaphore response (should score SA=1.0)")
    print("=" * 70)
    perfect_sem = json.dumps({
        "steps": sem_gt["steps"],
        "final_value": sem_gt["final_value"],
        "final_blocked_queue": sem_gt["final_blocked_queue"],
        "thread_final_state": sem_gt["thread_final_state"],
    })
    result_a = score_response("semaphore", sem_gt, perfect_sem)
    print(json.dumps(result_a, indent=2))
    assert result_a["step_accuracy"] == 1.0
    assert result_a["verdict_correct"] is True
    print("PASS\n")

    print("=" * 70)
    print("TEST B: BROKEN semaphore response — model thinks signal always")
    print("increments value, missing the handoff-to-blocked-thread rule")
    print("(classic busy-waiting-model confusion)")
    print("=" * 70)
    broken_sem = json.dumps({
        "steps": [
            sem_gt["steps"][0],  # wait_blocked -- correct
            {"step": 2, "op_index": 1, "thread": "T1", "action": "signal_increment",
             "value_before": 0, "value_after": 1, "blocked_queue_before": ["T0"],
             "blocked_queue_after": ["T0"], "woken_thread": None},  # WRONG: should be handoff
        ],
        "final_value": 1,
        "final_blocked_queue": ["T0"],
        "thread_final_state": {"T0": "blocked"},
    })
    result_b = score_response("semaphore", sem_gt, broken_sem)
    print(json.dumps(result_b, indent=2))
    assert result_b["errors_by_type"]["missed_handoff"] >= 1
    assert result_b["verdict_correct"] is False
    print("PASS\n")

    # --- MUTEX TESTS ---
    mtx_gt = solve_mutex_trace(
        operations=[
            {"thread": "T0", "op": "lock"},
            {"thread": "T0", "op": "lock"},  # self-deadlock
        ],
    )

    print("=" * 70)
    print("TEST C: PERFECT mutex response (should score SA=1.0)")
    print("=" * 70)
    perfect_mtx = json.dumps({
        "steps": mtx_gt["steps"],
        "final_owner": mtx_gt["final_owner"],
        "final_wait_queue": mtx_gt["final_wait_queue"],
        "thread_final_state": mtx_gt["thread_final_state"],
    })
    result_c = score_response("mutex", mtx_gt, perfect_mtx)
    print(json.dumps(result_c, indent=2))
    assert result_c["step_accuracy"] == 1.0
    print("PASS\n")

    print("=" * 70)
    print("TEST D: BROKEN mutex response — model fails to detect self-deadlock,")
    print("incorrectly reports the second lock() as just 'lock_acquired' again")
    print("=" * 70)
    broken_mtx = json.dumps({
        "steps": [
            mtx_gt["steps"][0],  # lock_acquired -- correct
            {"step": 2, "op_index": 1, "thread": "T0", "action": "lock_acquired",
             "owner_before": "T0", "owner_after": "T0", "wait_queue_before": [],
             "wait_queue_after": [], "woken_thread": None},  # WRONG: should be lock_self_deadlock
        ],
        "final_owner": "T0",
        "final_wait_queue": [],
        "thread_final_state": {"T0": "running"},
    })
    result_d = score_response("mutex", mtx_gt, broken_mtx)
    print(json.dumps(result_d, indent=2))
    assert result_d["errors_by_type"]["missed_self_deadlock"] >= 1
    assert result_d["verdict_correct"] is False
    print("PASS\n")

    print("=" * 70)
    print("TEST E: MALFORMED JSON (should be caught as parse error, not crash)")
    print("=" * 70)
    result_e = score_response("semaphore", sem_gt, "Let me trace this: {broken json")
    print(json.dumps(result_e, indent=2))
    assert result_e["parse_success"] is False
    print("PASS\n")

    print("ALL SELF-TESTS PASSED.")
