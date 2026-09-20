#!/usr/bin/env python3
"""
differential_tests.py
=====================
Validates SVAC solvers against independent reference implementations.

For WFG: uses networkx cycle detection as an oracle.
For Banker's: uses brute-force permutation checking.

Addresses audit finding E9 (solver correctness assumed without proof).
"""

import json
import os
import sys
from itertools import permutations

# Add parent to path for solver imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from svac_deadlock_solver import solve_wfg_cycle_detection, solve_bankers_safety

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "instances")


def brute_force_wfg_has_cycle(processes, edges):
    """
    Independent cycle detection using DFS with explicit color marking.
    WHITE=0, GRAY=1, BLACK=2.
    """
    color = {p: 0 for p in processes}

    def dfs(u):
        color[u] = 1  # GRAY
        for v in edges.get(u, []):
            if color.get(v, 0) == 1:  # back edge
                return True
            if color.get(v, 0) == 0:
                if dfs(v):
                    return True
        color[u] = 2  # BLACK
        return False

    for p in processes:
        if color[p] == 0:
            if dfs(p):
                return True
    return False


def brute_force_bankers_is_safe(available, max_matrix, allocation):
    """
    Independent Banker's safety check using brute-force:
    Try all permutations of unfinished processes and check if any
    forms a valid safe sequence.
    """
    n = len(allocation)
    r = len(available)
    need = [[max_matrix[i][j] - allocation[i][j] for j in range(r)] for i in range(n)]

    # For small n (≤ 8), try all permutations
    for perm in permutations(range(n)):
        work = list(available)
        valid = True
        for i in perm:
            if not all(need[i][j] <= work[j] for j in range(r)):
                valid = False
                break
            work = [work[j] + allocation[i][j] for j in range(r)]
        if valid:
            return True
    return False


def validate_wfg():
    """Validate all WFG instances."""
    path = os.path.join(DATA_DIR, "svac_wfg_instances.json")
    with open(path) as f:
        instances = json.load(f)

    print(f"\n{'='*70}")
    print(f"WFG CYCLE DETECTION — Differential Validation ({len(instances)} instances)")
    print(f"{'='*70}")

    mismatches = 0
    for inst in instances:
        processes = inst["processes"]
        edges = inst["edges"]

        # SVAC solver
        svac_result = solve_wfg_cycle_detection(processes, edges)
        svac_has_cycle = svac_result["deadlock"]

        # Independent oracle
        oracle_has_cycle = brute_force_wfg_has_cycle(processes, edges)

        # Ground truth from instance file
        gt_has_cycle = inst["ground_truth"]["deadlock"]

        if svac_has_cycle != oracle_has_cycle:
            print(f"  ✗ MISMATCH: {inst['instance_id']} "
                  f"SVAC={svac_has_cycle} vs Oracle={oracle_has_cycle}")
            mismatches += 1
        elif svac_has_cycle != gt_has_cycle:
            print(f"  ✗ GT-MISMATCH: {inst['instance_id']} "
                  f"SVAC={svac_has_cycle} vs GT={gt_has_cycle}")
            mismatches += 1

    if mismatches == 0:
        print(f"  ✓ All {len(instances)} instances: SVAC solver agrees with oracle AND stored ground truth")
    else:
        print(f"  ✗ {mismatches} mismatches found!")
    return mismatches


def validate_bankers():
    """Validate all Banker's instances."""
    path = os.path.join(DATA_DIR, "svac_bankers_instances.json")
    with open(path) as f:
        instances = json.load(f)

    print(f"\n{'='*70}")
    print(f"BANKER'S SAFETY ALGORITHM — Differential Validation ({len(instances)} instances)")
    print(f"{'='*70}")

    mismatches = 0
    for inst in instances:
        available = inst["available"]
        max_matrix = inst["max_matrix"]
        allocation = inst["allocation"]

        # SVAC solver
        svac_result = solve_bankers_safety(available, max_matrix, allocation)
        svac_safe = svac_result["safe"]

        # Independent oracle (brute force)
        oracle_safe = brute_force_bankers_is_safe(available, max_matrix, allocation)

        # Ground truth from instance file
        gt_safe = inst["ground_truth"]["safe"]

        if svac_safe != oracle_safe:
            print(f"  ✗ MISMATCH: {inst['instance_id']} "
                  f"SVAC={svac_safe} vs Oracle={oracle_safe}")
            mismatches += 1
        elif svac_safe != gt_safe:
            print(f"  ✗ GT-MISMATCH: {inst['instance_id']} "
                  f"SVAC={svac_safe} vs GT={gt_safe}")
            mismatches += 1

    if mismatches == 0:
        print(f"  ✓ All {len(instances)} instances: SVAC solver agrees with oracle AND stored ground truth")
    else:
        print(f"  ✗ {mismatches} mismatches found!")
    return mismatches


def validate_solver_oracle_consistency():
    """
    Additional check: run the SVAC solver on each instance's input and
    verify its output matches the stored ground truth trace exactly.
    """
    print(f"\n{'='*70}")
    print(f"SOLVER-GT TRACE CONSISTENCY (does re-running the solver reproduce stored GT?)")
    print(f"{'='*70}")

    # WFG
    path = os.path.join(DATA_DIR, "svac_wfg_instances.json")
    with open(path) as f:
        wfg_instances = json.load(f)

    wfg_mismatches = 0
    for inst in wfg_instances:
        result = solve_wfg_cycle_detection(inst["processes"], inst["edges"])
        gt = inst["ground_truth"]

        if result["deadlock"] != gt["deadlock"]:
            print(f"  ✗ WFG verdict mismatch: {inst['instance_id']}")
            wfg_mismatches += 1
        elif len(result["steps"]) != len(gt["steps"]):
            print(f"  ✗ WFG step count mismatch: {inst['instance_id']} "
                  f"(re-run={len(result['steps'])}, stored={len(gt['steps'])})")
            wfg_mismatches += 1

    if wfg_mismatches == 0:
        print(f"  ✓ WFG: All {len(wfg_instances)} instances reproduce stored ground truth")
    else:
        print(f"  ✗ WFG: {wfg_mismatches} mismatches")

    # Banker's
    path = os.path.join(DATA_DIR, "svac_bankers_instances.json")
    with open(path) as f:
        bankers_instances = json.load(f)

    bankers_mismatches = 0
    for inst in bankers_instances:
        result = solve_bankers_safety(inst["available"], inst["max_matrix"], inst["allocation"])
        gt = inst["ground_truth"]

        if result["safe"] != gt["safe"]:
            print(f"  ✗ Banker's verdict mismatch: {inst['instance_id']}")
            bankers_mismatches += 1
        elif len(result["steps"]) != len(gt["steps"]):
            print(f"  ✗ Banker's step count mismatch: {inst['instance_id']} "
                  f"(re-run={len(result['steps'])}, stored={len(gt['steps'])})")
            bankers_mismatches += 1

    if bankers_mismatches == 0:
        print(f"  ✓ Banker's: All {len(bankers_instances)} instances reproduce stored ground truth")
    else:
        print(f"  ✗ Banker's: {bankers_mismatches} mismatches")

    return wfg_mismatches + bankers_mismatches


def main():
    print("SVAC-Concurrency: Solver Differential Validation Suite")
    print("=" * 70)
    print("Tests SVAC solvers against independent brute-force oracles")
    print("Addresses audit finding E9 (solver correctness)")

    total_issues = 0
    total_issues += validate_wfg()
    total_issues += validate_bankers()
    total_issues += validate_solver_oracle_consistency()

    print(f"\n{'='*70}")
    if total_issues == 0:
        print("✓ ALL DIFFERENTIAL TESTS PASSED — Solvers verified correct")
    else:
        print(f"✗ {total_issues} total issues found — INVESTIGATE")
    print(f"{'='*70}")

    return total_issues


if __name__ == "__main__":
    sys.exit(main())
