#!/usr/bin/env python3
"""
test_validity_checker_oracle.py
===============================
Oracle and Corrupted-Oracle Validation for validity_checker.py.

Validates that the Equivalence-Aware Invariant Checker is neither too lenient
nor broken:
1. Clean Oracle Test: Ground-truth traces MUST score 100% valid step rate.
2. Corrupted-Oracle Test: Deliberately corrupted invalid steps MUST be caught
   (valid step rate < 100%, caught=True).
"""

import json
import os
import sys
import copy

BASE = "/Users/bethegnt/Downloads/SVAC_Concurrency"
BANKERS_FILE = os.path.join(BASE, "data", "instances", "svac_bankers_instances.json")
WFG_FILE = os.path.join(BASE, "data", "instances", "svac_wfg_instances.json")

sys.path.insert(0, os.path.join(BASE, "evaluation"))
from validity_checker import validate_bankers_trace, validate_wfg_trace


def test_bankers_oracle():
    print("--- 1. Banker's Clean Oracle Test ---")
    with open(BANKERS_FILE) as f:
        instances = json.load(f)

    passed = 0
    total = len(instances)
    for inst in instances:
        gt = inst["ground_truth"]
        model_sim = {
            "steps": gt["steps"],
            "safe": gt["safe"],
            "safe_sequence": gt.get("safe_sequence")
        }
        res = validate_bankers_trace(inst, model_sim)
        if res["valid_step_rate"] == 1.0:
            if gt["safe"]:
                if res["valid_safe_sequence"]:
                    passed += 1
                else:
                    print(f"  FAIL safe sequence on {inst['instance_id']}")
            else:
                passed += 1
        else:
            print(f"  FAIL step rate {res['valid_step_rate']} on {inst['instance_id']}")

    print(f"  Result: {passed}/{total} instances passed 100% (Clean Oracle PASS = {passed == total})")
    assert passed == total, f"Expected {total}, got {passed}"


def test_bankers_corrupted_oracle():
    print("\n--- 2. Banker's Corrupted-Oracle Test ---")
    with open(BANKERS_FILE) as f:
        instances = json.load(f)

    # Pick a safe instance
    inst = next(i for i in instances if i["ground_truth"]["safe"])
    gt = inst["ground_truth"]

    # Corruption A: Choose an illegal candidate process whose Need > Work
    corrupt_a = {
        "steps": copy.deepcopy(gt["steps"]),
        "safe": gt["safe"],
        "safe_sequence": gt.get("safe_sequence")
    }
    # Inflate candidate's need or flip candidate to one that cannot run
    if len(corrupt_a["steps"]) > 0:
        corrupt_a["steps"][0]["need_row"] = [999, 999]  # Exceeds work
    res_a = validate_bankers_trace(inst, corrupt_a)
    caught_a = res_a["step_validity"][0] is False
    print(f"  Corruption A (Need > Work injected at step 1): Caught = {caught_a}")
    assert caught_a

    # Corruption B: Arithmetic drift in work_after
    corrupt_b = {
        "steps": copy.deepcopy(gt["steps"]),
        "safe": gt["safe"],
        "safe_sequence": gt.get("safe_sequence")
    }
    if len(corrupt_b["steps"]) > 0:
        corrupt_b["steps"][0]["work_after"] = [0, 0]  # Wrong arithmetic
    res_b = validate_bankers_trace(inst, corrupt_b)
    caught_b = res_b["step_validity"][0] is False
    print(f"  Corruption B (Arithmetic drift in work_after): Caught = {caught_b}")
    assert caught_b

    # Corruption C: Invalid safe sequence (permutation that cannot execute)
    corrupt_c = {
        "steps": copy.deepcopy(gt["steps"]),
        "safe": gt["safe"],
        "safe_sequence": list(reversed(gt.get("safe_sequence", [])))
    }
    res_c = validate_bankers_trace(inst, corrupt_c)
    print(f"  Corruption C (Reversed safe sequence permutation): Valid = {res_c['valid_safe_sequence']}")


def test_wfg_oracle():
    print("\n--- 3. WFG Clean Oracle Test ---")
    with open(WFG_FILE) as f:
        instances = json.load(f)

    passed = 0
    total = len(instances)
    for inst in instances:
        gt = inst["ground_truth"]
        model_sim = {
            "steps": gt["steps"],
            "deadlock": gt["deadlock"],
            "cycle": gt.get("cycle")
        }
        res = validate_wfg_trace(inst, model_sim)
        if res["valid_step_rate"] == 1.0:
            passed += 1
        else:
            print(f"  FAIL on {inst['instance_id']}: step rate {res['valid_step_rate']}")

    print(f"  Result: {passed}/{total} instances passed 100% (Clean Oracle PASS = {passed == total})")
    assert passed == total, f"Expected {total}, got {passed}"


def test_wfg_corrupted_oracle():
    print("\n--- 4. WFG Corrupted-Oracle Test ---")
    with open(WFG_FILE) as f:
        instances = json.load(f)

    inst = instances[0]
    gt = inst["ground_truth"]

    # Corruption A: Non-neighbor visit (teleportation)
    corrupt_a = {
        "steps": copy.deepcopy(gt["steps"]),
        "deadlock": gt["deadlock"]
    }
    if len(corrupt_a["steps"]) > 1:
        corrupt_a["steps"][1]["node"] = "P999_NON_EXISTENT"
    res_a = validate_wfg_trace(inst, corrupt_a)
    caught_a = res_a["step_validity"][1] is False
    print(f"  Corruption A (Non-neighbor DFS visit): Caught = {caught_a}")
    assert caught_a

    # Corruption B: Illegal backtrack (backtracking a node not on stack top)
    corrupt_b = {
        "steps": copy.deepcopy(gt["steps"]),
        "deadlock": gt["deadlock"]
    }
    if len(corrupt_b["steps"]) > 1:
        corrupt_b["steps"][1]["action"] = "backtrack"
        corrupt_b["steps"][1]["node"] = "P_WRONG"
    res_b = validate_wfg_trace(inst, corrupt_b)
    caught_b = res_b["step_validity"][1] is False
    print(f"  Corruption B (Illegal backtrack): Caught = {caught_b}")
    assert caught_b


def main():
    print("=" * 70)
    print("ORACLE & CORRUPTED-ORACLE VERIFICATION OF INVARIANT CHECKER")
    print("=" * 70)
    test_bankers_oracle()
    test_bankers_corrupted_oracle()
    test_wfg_oracle()
    test_wfg_corrupted_oracle()
    print("\n" + "=" * 70)
    print("ALL ORACLE TESTS PASSED: The invariant checker is rigorous and sensitive!")
    print("=" * 70)


if __name__ == "__main__":
    main()
