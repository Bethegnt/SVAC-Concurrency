"""
svac_deadlock_generator.py
============================
Generates random problem instances for the Deadlock Detection module,
mirroring the structure of svac_page_replacement_generator.py from Paper 4.

Two instance families are produced:
  - "wfg"      : Wait-For-Graph cycle-detection instances
  - "bankers"  : Banker's Algorithm safety-check instances

Each family is generated across 5 complexity levels. At every level we
generate a controlled MIX of positive and negative cases (deadlock /
no-deadlock, safe / unsafe) so the benchmark can measure false-positive
and false-negative behaviour separately -- this directly targets the
"positive response bias" (over-predicting cycles) documented in prior
LLM graph-reasoning literature.

Run this file directly to generate:
    data/instances/svac_wfg_instances.json
    data/instances/svac_bankers_instances.json
"""

from __future__ import annotations
import json
import random
import uuid
import os
from typing import List, Dict, Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "solvers"))
from svac_deadlock_solver import solve_wfg_cycle_detection, solve_bankers_safety


# ══════════════════════════════════════════════════════════════════════════
# COMPLEXITY CONFIGURATION  (mirrors the Level 1-5 table from Paper 4)
# ══════════════════════════════════════════════════════════════════════════

WFG_COMPLEXITY = {
    1: {"num_processes": 3,  "extra_edges": 0},
    2: {"num_processes": 4,  "extra_edges": 1},
    3: {"num_processes": 6,  "extra_edges": 2},
    4: {"num_processes": 8,  "extra_edges": 3},
    5: {"num_processes": 12, "extra_edges": 4},
}

BANKERS_COMPLEXITY = {
    1: {"num_processes": 3, "num_resources": 2},
    2: {"num_processes": 4, "num_resources": 3},
    3: {"num_processes": 5, "num_resources": 3},
    4: {"num_processes": 6, "num_resources": 4},
    5: {"num_processes": 8, "num_resources": 4},
}

INSTANCES_PER_LEVEL = 6   # 3 deadlock/unsafe + 3 safe, per level (tune as needed)


# ══════════════════════════════════════════════════════════════════════════
# 1. WFG INSTANCE GENERATION
# ══════════════════════════════════════════════════════════════════════════

def _make_cyclic_wfg(num_processes: int, extra_edges: int, rng: random.Random) -> Dict[str, List[str]]:
    """Build a WFG that is GUARANTEED to contain at least one cycle."""
    procs = [f"P{i}" for i in range(num_processes)]
    edges: Dict[str, List[str]] = {p: [] for p in procs}

    # Plant one guaranteed cycle among a random subset (size >= 2).
    cycle_len = rng.randint(2, min(num_processes, 5))
    cycle_nodes = rng.sample(procs, cycle_len)
    for i in range(cycle_len):
        edges[cycle_nodes[i]].append(cycle_nodes[(i + 1) % cycle_len])

    # Add extra random edges (not necessarily creating more cycles, just noise)
    for _ in range(extra_edges):
        a, b = rng.sample(procs, 2)
        if b not in edges[a]:
            edges[a].append(b)

    return edges


def _make_acyclic_wfg(num_processes: int, extra_edges: int, rng: random.Random) -> Dict[str, List[str]]:
    """Build a WFG that is GUARANTEED to be acyclic (a DAG)."""
    procs = [f"P{i}" for i in range(num_processes)]
    edges: Dict[str, List[str]] = {p: [] for p in procs}

    # Only allow edges that go from a lower index to a higher index -> no cycle possible.
    possible_edges = [(procs[i], procs[j]) for i in range(num_processes)
                       for j in range(i + 1, num_processes)]
    rng.shuffle(possible_edges)

    num_edges = min(len(possible_edges), num_processes - 1 + extra_edges)
    chosen = possible_edges[:num_edges]
    for a, b in chosen:
        edges[a].append(b)

    return edges


def generate_wfg_instances(seed: int = 42) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    instances = []

    for level, cfg in WFG_COMPLEXITY.items():
        num_deadlock = INSTANCES_PER_LEVEL // 2
        num_safe = INSTANCES_PER_LEVEL - num_deadlock

        for _ in range(num_deadlock):
            edges = _make_cyclic_wfg(cfg["num_processes"], cfg["extra_edges"], rng)
            processes = [f"P{i}" for i in range(cfg["num_processes"])]
            gt = solve_wfg_cycle_detection(processes, edges)
            instances.append({
                "instance_id": f"wfg_{uuid.uuid4().hex[:12]}",
                "task": "wfg",
                "complexity_level": level,
                "num_processes": cfg["num_processes"],
                "processes": processes,
                "edges": edges,
                "ground_truth": gt,
            })

        for _ in range(num_safe):
            edges = _make_acyclic_wfg(cfg["num_processes"], cfg["extra_edges"], rng)
            processes = [f"P{i}" for i in range(cfg["num_processes"])]
            gt = solve_wfg_cycle_detection(processes, edges)
            instances.append({
                "instance_id": f"wfg_{uuid.uuid4().hex[:12]}",
                "task": "wfg",
                "complexity_level": level,
                "num_processes": cfg["num_processes"],
                "processes": processes,
                "edges": edges,
                "ground_truth": gt,
            })

    return instances


# ══════════════════════════════════════════════════════════════════════════
# 2. BANKER'S ALGORITHM INSTANCE GENERATION
# ══════════════════════════════════════════════════════════════════════════

def _random_bankers_instance(num_processes: int, num_resources: int,
                              rng: random.Random, force_safe: bool):
    """
    Generate an Allocation/Max/Available triple.
    force_safe=True  -> keep resampling until the safety algorithm says SAFE
    force_safe=False -> keep resampling until the safety algorithm says UNSAFE
    Bounded retries to avoid infinite loops on awkward configurations.
    """
    for _attempt in range(200):
        allocation = [[rng.randint(0, 4) for _ in range(num_resources)]
                      for _ in range(num_processes)]
        max_matrix = [[allocation[i][j] + rng.randint(0, 4) for j in range(num_resources)]
                      for i in range(num_processes)]
        total_allocated = [sum(allocation[i][j] for i in range(num_processes))
                            for j in range(num_resources)]
        # total resources in the system, then available = total - allocated
        total_resources = [total_allocated[j] + rng.randint(0, 3) for j in range(num_resources)]
        available = [total_resources[j] - total_allocated[j] for j in range(num_resources)]

        result = solve_bankers_safety(available, max_matrix, allocation)
        if result["safe"] == force_safe:
            return available, max_matrix, allocation, result

    # Fallback: return whatever the last attempt produced (rare edge case)
    return available, max_matrix, allocation, result


def generate_bankers_instances(seed: int = 43) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    instances = []

    for level, cfg in BANKERS_COMPLEXITY.items():
        num_safe = INSTANCES_PER_LEVEL // 2
        num_unsafe = INSTANCES_PER_LEVEL - num_safe

        for _ in range(num_safe):
            available, max_matrix, allocation, gt = _random_bankers_instance(
                cfg["num_processes"], cfg["num_resources"], rng, force_safe=True)
            instances.append({
                "instance_id": f"bankers_{uuid.uuid4().hex[:12]}",
                "task": "bankers",
                "complexity_level": level,
                "num_processes": cfg["num_processes"],
                "num_resources": cfg["num_resources"],
                "available": available,
                "max_matrix": max_matrix,
                "allocation": allocation,
                "ground_truth": gt,
            })

        for _ in range(num_unsafe):
            available, max_matrix, allocation, gt = _random_bankers_instance(
                cfg["num_processes"], cfg["num_resources"], rng, force_safe=False)
            instances.append({
                "instance_id": f"bankers_{uuid.uuid4().hex[:12]}",
                "task": "bankers",
                "complexity_level": level,
                "num_processes": cfg["num_processes"],
                "num_resources": cfg["num_resources"],
                "available": available,
                "max_matrix": max_matrix,
                "allocation": allocation,
                "ground_truth": gt,
            })

    return instances


# ══════════════════════════════════════════════════════════════════════════
# MAIN — generate and save both instance sets
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "data", "instances")
    os.makedirs(out_dir, exist_ok=True)

    wfg_instances = generate_wfg_instances()
    bankers_instances = generate_bankers_instances()

    wfg_path = os.path.join(out_dir, "svac_wfg_instances.json")
    bankers_path = os.path.join(out_dir, "svac_bankers_instances.json")

    with open(wfg_path, "w") as f:
        json.dump(wfg_instances, f, indent=2)
    with open(bankers_path, "w") as f:
        json.dump(bankers_instances, f, indent=2)

    print(f"Generated {len(wfg_instances)} WFG instances -> {wfg_path}")
    deadlock_count = sum(1 for i in wfg_instances if i["ground_truth"]["deadlock"])
    print(f"  -> {deadlock_count} deadlock cases, {len(wfg_instances) - deadlock_count} safe cases")

    print(f"Generated {len(bankers_instances)} Banker's instances -> {bankers_path}")
    safe_count = sum(1 for i in bankers_instances if i["ground_truth"]["safe"])
    print(f"  -> {safe_count} safe cases, {len(bankers_instances) - safe_count} unsafe cases")

    # Print one example of each so you can sanity-check the format
    print("\n--- Example WFG instance (Level 1) ---")
    example_wfg = next(i for i in wfg_instances if i["complexity_level"] == 1)
    print(json.dumps(example_wfg, indent=2)[:800], "...")

    print("\n--- Example Banker's instance (Level 1) ---")
    example_bankers = next(i for i in bankers_instances if i["complexity_level"] == 1)
    print(json.dumps(example_bankers, indent=2)[:800], "...")
