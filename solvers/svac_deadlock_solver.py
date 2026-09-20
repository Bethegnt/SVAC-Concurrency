"""
svac_deadlock_solver.py
========================
Deterministic ground-truth solvers for the Deadlock Detection module of the
SVAC (Step-Verifiable Algorithm Completions) benchmark.

Two sub-tasks are covered, matching the two classical deadlock-handling
techniques taught in Operating Systems courses:

  1. WAIT-FOR-GRAPH (WFG) CYCLE DETECTION
     Given a directed graph where an edge Pi -> Pj means "process Pi is
     waiting for a resource held by process Pj", detect whether a cycle
     exists (a cycle in a single-instance-resource WFG implies deadlock).
     Implemented via iterative-trace DFS so every visit/backtrack/cycle
     event is recorded as a step (mirrors how the LLM will be asked to
     "manually" trace the algorithm).

  2. BANKER'S ALGORITHM (Safety Algorithm)
     Given Available, Max, and Allocation matrices, compute the Need
     matrix and run the safety algorithm to find a safe sequence (or
     prove none exists, i.e. system is NOT in a safe state).

Both solvers are 100% deterministic: identical input always produces an
identical trace. No randomness lives in this file -- randomness belongs
only in the instance generator.
"""

from __future__ import annotations
from typing import List, Dict, Any


# ══════════════════════════════════════════════════════════════════════════
# 1. WAIT-FOR-GRAPH CYCLE DETECTION
# ══════════════════════════════════════════════════════════════════════════

def solve_wfg_cycle_detection(processes: List[str],
                               edges: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Detect a cycle in a Wait-For-Graph using DFS with an explicit
    recursion stack, recording one trace step per visit/backtrack event.

    Args:
        processes: list of process names, e.g. ["P0", "P1", "P2"]
        edges: adjacency list, e.g. {"P0": ["P1"], "P1": ["P2"], "P2": ["P0"]}
               means P0 waits for P1, P1 waits for P2, P2 waits for P0.

    Returns:
        {
          "deadlock": bool,
          "cycle_nodes": [...] or None,   # nodes forming the cycle, if any
          "steps": [ ... trace ... ]
        }

    Each step in "steps" has the shape:
        {
          "step": int,                # 1-indexed step counter
          "action": "visit" | "backtrack" | "cycle_detected",
          "node": str,
          "visited_set": [...],       # sorted list, nodes fully processed
          "recursion_stack": [...],   # current DFS path (ordered)
        }
    """
    visited = set()
    rec_stack: List[str] = []
    steps: List[Dict[str, Any]] = []
    step_counter = [0]

    def record(action: str, node: str):
        step_counter[0] += 1
        steps.append({
            "step": step_counter[0],
            "action": action,
            "node": node,
            "visited_set": sorted(visited),
            "recursion_stack": list(rec_stack),
        })

    cycle_nodes = None

    def dfs(node: str) -> bool:
        nonlocal cycle_nodes
        visited.add(node)
        rec_stack.append(node)
        record("visit", node)

        for neighbor in edges.get(node, []):
            if neighbor in rec_stack:
                # Back-edge found -> cycle. Extract the cycle segment.
                idx = rec_stack.index(neighbor)
                cycle_nodes = rec_stack[idx:] + [neighbor]
                step_counter[0] += 1
                steps.append({
                    "step": step_counter[0],
                    "action": "cycle_detected",
                    "node": neighbor,
                    "visited_set": sorted(visited),
                    "recursion_stack": list(rec_stack),
                    "cycle": list(cycle_nodes),
                })
                return True
            if neighbor not in visited:
                if dfs(neighbor):
                    return True

        rec_stack.pop()
        record("backtrack", node)
        return False

    found = False
    for p in processes:
        if p not in visited:
            if dfs(p):
                found = True
                break

    return {
        "deadlock": found,
        "cycle_nodes": cycle_nodes,
        "steps": steps,
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. BANKER'S ALGORITHM (SAFETY ALGORITHM)
# ══════════════════════════════════════════════════════════════════════════

def solve_bankers_safety(available: List[int],
                          max_matrix: List[List[int]],
                          allocation: List[List[int]]) -> Dict[str, Any]:
    """
    Run the Banker's Algorithm safety check.

    Args:
        available: list of available units per resource type, len = R
        max_matrix: max_matrix[i][j] = max demand of process i for resource j
        allocation: allocation[i][j] = currently allocated units of resource
                    j to process i

    Returns:
        {
          "safe": bool,
          "safe_sequence": [...] or None,
          "need_matrix": [[...], ...],
          "steps": [ ... trace ... ]
        }

    Each step in "steps" has the shape:
        {
          "step": int,
          "work_before": [...],
          "candidate_process": int or None,   # index chosen this round, or
                                               # None if no candidate found
          "need_row": [...] or None,          # need row of the candidate
          "work_after": [...] or None,        # work + allocation[candidate]
          "finish": [...],                    # finish[] state AFTER this step
        }
    """
    n = len(allocation)                 # number of processes
    r = len(available)                  # number of resource types

    need_matrix = [
        [max_matrix[i][j] - allocation[i][j] for j in range(r)]
        for i in range(n)
    ]

    work = list(available)
    finish = [False] * n
    safe_sequence: List[int] = []
    steps: List[Dict[str, Any]] = []
    step_counter = 0

    while len(safe_sequence) < n:
        progressed = False
        for i in range(n):
            if finish[i]:
                continue
            if all(need_matrix[i][j] <= work[j] for j in range(r)):
                step_counter += 1
                work_before = list(work)
                work = [work[j] + allocation[i][j] for j in range(r)]
                finish[i] = True
                safe_sequence.append(i)
                steps.append({
                    "step": step_counter,
                    "work_before": work_before,
                    "candidate_process": i,
                    "need_row": list(need_matrix[i]),
                    "work_after": list(work),
                    "finish": list(finish),
                })
                progressed = True
                break  # restart scan from P0 each round (textbook convention)

        if not progressed:
            # No process could be satisfied this round -> unsafe state.
            step_counter += 1
            steps.append({
                "step": step_counter,
                "work_before": list(work),
                "candidate_process": None,
                "need_row": None,
                "work_after": None,
                "finish": list(finish),
            })
            return {
                "safe": False,
                "safe_sequence": None,
                "need_matrix": need_matrix,
                "steps": steps,
            }

    return {
        "safe": True,
        "safe_sequence": [f"P{i}" for i in safe_sequence],
        "need_matrix": need_matrix,
        "steps": steps,
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. SELF-TEST (manual textbook examples — run this file directly to verify)
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("TEST 1: WFG with a cycle (P0 -> P1 -> P2 -> P0)")
    print("=" * 70)
    result = solve_wfg_cycle_detection(
        processes=["P0", "P1", "P2"],
        edges={"P0": ["P1"], "P1": ["P2"], "P2": ["P0"]},
    )
    print("Deadlock:", result["deadlock"])
    print("Cycle:", result["cycle_nodes"])
    for s in result["steps"]:
        print(" ", s)

    print()
    print("=" * 70)
    print("TEST 2: WFG with NO cycle (P0 -> P1 -> P2, P3 -> P1)")
    print("=" * 70)
    result2 = solve_wfg_cycle_detection(
        processes=["P0", "P1", "P2", "P3"],
        edges={"P0": ["P1"], "P1": ["P2"], "P3": ["P1"]},
    )
    print("Deadlock:", result2["deadlock"])
    print("Cycle:", result2["cycle_nodes"])
    for s in result2["steps"]:
        print(" ", s)

    print()
    print("=" * 70)
    print("TEST 3: Banker's Algorithm — classic Silberschatz textbook example")
    print("(5 processes, 3 resource types A/B/C -> expect SAFE, seq P1,P3,P4,P0,P2)")
    print("=" * 70)
    available = [3, 3, 2]
    max_matrix = [
        [7, 5, 3],
        [3, 2, 2],
        [9, 0, 2],
        [2, 2, 2],
        [4, 3, 3],
    ]
    allocation = [
        [0, 1, 0],
        [2, 0, 0],
        [3, 0, 2],
        [2, 1, 1],
        [0, 0, 2],
    ]
    result3 = solve_bankers_safety(available, max_matrix, allocation)
    print("Safe:", result3["safe"])
    print("Safe sequence:", result3["safe_sequence"])
    print("Need matrix:", result3["need_matrix"])
    for s in result3["steps"]:
        print(" ", s)
