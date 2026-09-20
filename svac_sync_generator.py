"""
svac_sync_generator.py
==========================
Generates random problem instances for the Process Synchronization module,
following the exact structural pattern of svac_deadlock_generator.py and
svac_buddy_generator.py:
  - COMPLEXITY dicts keyed by level (1-5), one per sub-task
  - deterministic "mode" builders that steer toward a specific behavior
    shape (mirrors _make_cyclic_wfg / fragmentation mode in Buddy)
  - every instance's ground truth is produced by calling the real solver
    (never fabricated), embedded in the instance JSON
  - a fixed random seed per generation function, for full reproducibility

SEMAPHORE MODES:
  1. "producer_consumer" - alternating wait/signal calls that stay balanced
                            (never more waits than the semaphore + signals
                            can satisfy) -- the "easy" baseline case.
  2. "contention"         - many waits issued before any signal, forcing
                             several threads onto the blocked_queue, then
                             enough signals to drain it via handoff.
  3. "bounded_edge"        - a bounded (max_value) semaphore pushed with
                              extra signals beyond capacity while nobody is
                              waiting -> guaranteed invalid_over_signal.
  4. "random_interleaved"  - random mix of wait/signal across threads.

MUTEX MODES:
  1. "sequential"          - each thread cleanly locks then unlocks in turn,
                              no contention.
  2. "contention"           - multiple threads queue up for the same mutex,
                               forcing lock_blocked + unlock_release_handoff
                               chains.
  3. "invalid_unlock_edge"  - includes an unlock() by a thread that never
                               held the lock.
  4. "self_deadlock_edge"   - a thread locks a mutex it already holds
                               (non-reentrant self-deadlock).

Run this file directly to generate:
    data/instances/svac_semaphore_instances.json
    data/instances/svac_mutex_instances.json
"""

from __future__ import annotations
import json
import random
import uuid
import os
from typing import List, Dict, Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "solvers"))
from svac_sync_solver import solve_semaphore_trace, solve_mutex_trace


# ══════════════════════════════════════════════════════════════════════════
# COMPLEXITY CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

SEMAPHORE_COMPLEXITY = {
    1: {"num_threads": 2, "initial_value": 1, "num_ops": 4},
    2: {"num_threads": 3, "initial_value": 2, "num_ops": 6},
    3: {"num_threads": 4, "initial_value": 2, "num_ops": 8},
    4: {"num_threads": 5, "initial_value": 3, "num_ops": 10},
    5: {"num_threads": 6, "initial_value": 3, "num_ops": 14},
}

MUTEX_COMPLEXITY = {
    1: {"num_threads": 2, "num_ops": 4},
    2: {"num_threads": 3, "num_ops": 6},
    3: {"num_threads": 4, "num_ops": 8},
    4: {"num_threads": 5, "num_ops": 10},
    5: {"num_threads": 6, "num_ops": 14},
}

SEMAPHORE_MODES = ["producer_consumer", "contention", "bounded_edge", "random_interleaved"]
MUTEX_MODES = ["sequential", "contention", "invalid_unlock_edge", "self_deadlock_edge"]


def _thread_ids(n: int) -> List[str]:
    return [f"T{i}" for i in range(n)]


# ══════════════════════════════════════════════════════════════════════════
# SEMAPHORE MODE BUILDERS
# ══════════════════════════════════════════════════════════════════════════

def _sem_producer_consumer(cfg: Dict, rng: random.Random):
    """Balanced alternating wait/signal -- keeps the semaphore comfortably
    satisfiable so calls mostly succeed immediately (few/no blocks)."""
    threads = _thread_ids(cfg["num_threads"])
    ops = []
    for i in range(cfg["num_ops"]):
        thread = threads[i % len(threads)]
        call = "wait" if i % 2 == 0 else "signal"
        ops.append({"thread": thread, "op": call})
    return ops, None


def _sem_contention(cfg: Dict, rng: random.Random):
    """Front-load waits (more than initial_value can satisfy) so several
    threads pile onto blocked_queue, then issue signals to drain it."""
    threads = _thread_ids(cfg["num_threads"])
    n_waits = min(len(threads), cfg["initial_value"] + 2)
    ops = [{"thread": threads[i], "op": "wait"} for i in range(n_waits)]
    n_signals = max(2, cfg["num_ops"] - n_waits)
    for i in range(n_signals):
        ops.append({"thread": threads[i % len(threads)], "op": "signal"})
    return ops, None


def _sem_bounded_edge(cfg: Dict, rng: random.Random):
    """Binary-style bounded semaphore (max_value=1) pushed past capacity."""
    threads = _thread_ids(cfg["num_threads"])
    max_value = 1
    ops = [{"thread": threads[0], "op": "signal"}]  # nobody waiting, at max already -> invalid
    ops.append({"thread": threads[0], "op": "wait"})   # now acquires (value 1->0)
    ops.append({"thread": threads[1 % len(threads)], "op": "signal"})  # value 0->1, valid
    ops.append({"thread": threads[0], "op": "signal"})  # value already at max, invalid again
    return ops, max_value


def _sem_random_interleaved(cfg: Dict, rng: random.Random):
    threads = _thread_ids(cfg["num_threads"])
    ops = []
    for _ in range(cfg["num_ops"]):
        thread = rng.choice(threads)
        call = rng.choice(["wait", "signal"])
        ops.append({"thread": thread, "op": call})
    return ops, None


SEMAPHORE_MODE_BUILDERS = {
    "producer_consumer": _sem_producer_consumer,
    "contention": _sem_contention,
    "bounded_edge": _sem_bounded_edge,
    "random_interleaved": _sem_random_interleaved,
}


def generate_semaphore_instances(seed: int = 45) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    instances = []

    for level, cfg in SEMAPHORE_COMPLEXITY.items():
        for mode in SEMAPHORE_MODES:
            operations, max_value = SEMAPHORE_MODE_BUILDERS[mode](cfg, rng)
            gt = solve_semaphore_trace(cfg["initial_value"], operations, max_value=max_value)
            instances.append({
                "instance_id": f"sem_{uuid.uuid4().hex[:12]}",
                "task": "semaphore",
                "mode": mode,
                "complexity_level": level,
                "initial_value": cfg["initial_value"],
                "max_value": max_value,
                "operations": operations,
                "ground_truth": gt,
            })

    return instances


# ══════════════════════════════════════════════════════════════════════════
# MUTEX MODE BUILDERS
# ══════════════════════════════════════════════════════════════════════════

def _mtx_sequential(cfg: Dict, rng: random.Random):
    """Each thread cleanly locks then unlocks before the next thread starts."""
    threads = _thread_ids(cfg["num_threads"])
    ops = []
    i = 0
    while len(ops) < cfg["num_ops"]:
        thread = threads[i % len(threads)]
        ops.append({"thread": thread, "op": "lock"})
        ops.append({"thread": thread, "op": "unlock"})
        i += 1
    return ops[:cfg["num_ops"]] if cfg["num_ops"] % 2 == 0 else ops[:cfg["num_ops"] + 1]


def _mtx_contention(cfg: Dict, rng: random.Random):
    """First thread locks, several others queue up, then it unlocks
    (triggering a handoff chain as each subsequent thread also unlocks)."""
    threads = _thread_ids(cfg["num_threads"])
    ops = [{"thread": threads[0], "op": "lock"}]
    for t in threads[1:]:
        ops.append({"thread": t, "op": "lock"})  # all block behind threads[0]
    # Now unlock in the same order the locks will be handed off.
    for t in threads:
        ops.append({"thread": t, "op": "unlock"})
    return ops


def _mtx_invalid_unlock_edge(cfg: Dict, rng: random.Random):
    threads = _thread_ids(cfg["num_threads"])
    ops = [
        {"thread": threads[1 % len(threads)], "op": "unlock"},  # invalid: nobody owns it
        {"thread": threads[0], "op": "lock"},
        {"thread": threads[1 % len(threads)], "op": "unlock"},  # invalid: wrong owner
        {"thread": threads[0], "op": "unlock"},                  # valid
    ]
    return ops


def _mtx_self_deadlock_edge(cfg: Dict, rng: random.Random):
    threads = _thread_ids(cfg["num_threads"])
    ops = [
        {"thread": threads[0], "op": "lock"},
        {"thread": threads[0], "op": "lock"},   # self-deadlock
        {"thread": threads[1 % len(threads)], "op": "lock"},  # also queues behind
    ]
    return ops


MUTEX_MODE_BUILDERS = {
    "sequential": _mtx_sequential,
    "contention": _mtx_contention,
    "invalid_unlock_edge": _mtx_invalid_unlock_edge,
    "self_deadlock_edge": _mtx_self_deadlock_edge,
}


def generate_mutex_instances(seed: int = 46) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    instances = []

    for level, cfg in MUTEX_COMPLEXITY.items():
        for mode in MUTEX_MODES:
            operations = MUTEX_MODE_BUILDERS[mode](cfg, rng)
            gt = solve_mutex_trace(operations)
            instances.append({
                "instance_id": f"mtx_{uuid.uuid4().hex[:12]}",
                "task": "mutex",
                "mode": mode,
                "complexity_level": level,
                "operations": operations,
                "ground_truth": gt,
            })

    return instances


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from collections import Counter

    out_dir = os.path.join(os.path.dirname(__file__), "data", "instances")
    os.makedirs(out_dir, exist_ok=True)

    sem_instances = generate_semaphore_instances()
    mtx_instances = generate_mutex_instances()

    sem_path = os.path.join(out_dir, "svac_semaphore_instances.json")
    mtx_path = os.path.join(out_dir, "svac_mutex_instances.json")

    with open(sem_path, "w") as f:
        json.dump(sem_instances, f, indent=2)
    with open(mtx_path, "w") as f:
        json.dump(mtx_instances, f, indent=2)

    print(f"Generated {len(sem_instances)} Semaphore instances -> {sem_path}")
    print("  By mode:", dict(Counter(i["mode"] for i in sem_instances)))
    invalid_sem = sum(
        1 for i in sem_instances
        if any(s["action"] == "invalid_over_signal" for s in i["ground_truth"]["steps"])
    )
    print(f"  Instances containing invalid_over_signal: {invalid_sem}")
    blocked_sem = sum(
        1 for i in sem_instances
        if any(s["action"] == "wait_blocked" for s in i["ground_truth"]["steps"])
    )
    print(f"  Instances containing at least one wait_blocked: {blocked_sem}")

    print(f"\nGenerated {len(mtx_instances)} Mutex instances -> {mtx_path}")
    print("  By mode:", dict(Counter(i["mode"] for i in mtx_instances)))
    invalid_mtx = sum(
        1 for i in mtx_instances
        if any(s["action"] == "invalid_unlock" for s in i["ground_truth"]["steps"])
    )
    print(f"  Instances containing invalid_unlock: {invalid_mtx}")
    deadlock_mtx = sum(
        1 for i in mtx_instances
        if any(s["action"] == "lock_self_deadlock" for s in i["ground_truth"]["steps"])
    )
    print(f"  Instances containing lock_self_deadlock: {deadlock_mtx}")

    print("\n--- Example Semaphore instance (Level 1, contention mode) ---")
    example_sem = next(i for i in sem_instances if i["complexity_level"] == 1 and i["mode"] == "contention")
    print(json.dumps(example_sem, indent=2)[:800], "...")

    print("\n--- Example Mutex instance (Level 1, contention mode) ---")
    example_mtx = next(i for i in mtx_instances if i["complexity_level"] == 1 and i["mode"] == "contention")
    print(json.dumps(example_mtx, indent=2)[:800], "...")
