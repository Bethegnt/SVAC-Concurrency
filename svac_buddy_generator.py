"""
svac_buddy_generator.py
==========================
Generates random problem instances for the Buddy System module, following
the exact structural pattern of svac_deadlock_generator.py:
  - a COMPLEXITY dict keyed by level (1-5)
  - deterministic "mode" builders that GUARANTEE a specific outcome shape
    (mirrors _make_cyclic_wfg / _make_acyclic_wfg guaranteeing deadlock /
    no-deadlock)
  - every instance's ground truth is produced by calling the real solver
    (never fabricated), then embedded in the instance JSON
  - a fixed random seed per generation function, for full reproducibility

FIVE LOCALITY MODES (mirrors the "deadlock vs safe" split in the deadlock
module, generalized to 5 modes since Buddy System has richer behavior):

  1. "sequential"     - alloc everything, then free everything in reverse
                         order. Always fully coalesces back to one block.
                         (Easy: no interleaving, simplest trace shape.)
  2. "interleaved"     - random mix of alloc/free on currently-live
                         requests. Exercises partial coalescing.
  3. "fragmentation"   - adversarial pattern (alloc A,B,C,... then free
                         every OTHER one) that leaves free blocks that
                         cannot merge with each other, then attempts one
                         more alloc that requires a larger contiguous
                         block than fragmentation allows -> guaranteed
                         allocation FAILURE despite enough total free
                         memory. (Hard: the classic buddy-system pitfall.)
  4. "overflow"        - a single alloc request larger than total_memory
                         -> guaranteed immediate failure. (Edge case.)
  5. "invalid_ops"     - includes a double-free and/or a free of an
                         unknown request_id mixed into an otherwise normal
                         sequence. (Edge case: malformed operation handling.)

Run this file directly to generate:
    data/instances/svac_buddy_instances.json
"""

from __future__ import annotations
import json
import random
import uuid
import os
from typing import List, Dict, Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "solvers"))
from svac_buddy_solver import solve_buddy_system


# ══════════════════════════════════════════════════════════════════════════
# COMPLEXITY CONFIGURATION  (mirrors WFG_COMPLEXITY / BANKERS_COMPLEXITY)
# ══════════════════════════════════════════════════════════════════════════

BUDDY_COMPLEXITY = {
    1: {"total_memory": 32,  "min_block_size": 4,  "num_base_requests": 3},
    2: {"total_memory": 64,  "min_block_size": 4,  "num_base_requests": 4},
    3: {"total_memory": 128, "min_block_size": 8,  "num_base_requests": 6},
    4: {"total_memory": 256, "min_block_size": 8,  "num_base_requests": 8},
    5: {"total_memory": 512, "min_block_size": 16, "num_base_requests": 10},
}

MODES = ["sequential", "interleaved", "fragmentation", "overflow", "invalid_ops"]


def _request_ids(n: int) -> List[str]:
    return [chr(ord("A") + i) for i in range(n)]


def _random_size(total_memory: int, min_block_size: int, rng: random.Random) -> int:
    """A plausible request size: somewhere between min_block_size and total_memory//2."""
    upper = max(min_block_size, total_memory // 2)
    return rng.randint(min_block_size, upper)


# ══════════════════════════════════════════════════════════════════════════
# MODE BUILDERS — each returns a list of operations
# ══════════════════════════════════════════════════════════════════════════

def _build_sequential(cfg: Dict, rng: random.Random) -> List[Dict[str, Any]]:
    """Alloc everything first, then free everything in reverse order."""
    ids = _request_ids(cfg["num_base_requests"])
    ops = [{"op": "alloc", "request_id": rid,
            "size": _random_size(cfg["total_memory"], cfg["min_block_size"], rng)}
           for rid in ids]
    ops += [{"op": "free", "request_id": rid} for rid in reversed(ids)]
    return ops


def _build_interleaved(cfg: Dict, rng: random.Random) -> List[Dict[str, Any]]:
    """Random mix: alloc new requests or free a currently-live one, in random order."""
    ids = _request_ids(cfg["num_base_requests"])
    ops: List[Dict[str, Any]] = []
    live: List[str] = []
    pending = list(ids)
    rng.shuffle(pending)

    while pending or live:
        # Occasionally free a live request; otherwise allocate the next pending one.
        can_free = len(live) > 0
        can_alloc = len(pending) > 0
        do_free = can_free and (not can_alloc or rng.random() < 0.4)

        if do_free:
            rid = rng.choice(live)
            live.remove(rid)
            ops.append({"op": "free", "request_id": rid})
        else:
            rid = pending.pop()
            ops.append({"op": "alloc", "request_id": rid,
                        "size": _random_size(cfg["total_memory"], cfg["min_block_size"], rng)})
            live.append(rid)

    # Free anything still live at the end so the trace has a clean resolution.
    for rid in live:
        ops.append({"op": "free", "request_id": rid})
    return ops


def _build_fragmentation(cfg: Dict, rng: random.Random) -> List[Dict[str, Any]]:
    """
    Adversarial: allocate several equal, minimum-sized blocks back-to-back,
    free every OTHER one (so freed blocks are never adjacent buddies of each
    other), then request a block larger than any single fragment -- this is
    guaranteed to fail even though total free memory may be sufficient.
    """
    total_memory = cfg["total_memory"]
    min_block_size = cfg["min_block_size"]
    # Fill the entire pool with minimum-sized blocks.
    num_blocks = total_memory // min_block_size
    ids = _request_ids(min(num_blocks, cfg["num_base_requests"] + 2))

    ops = [{"op": "alloc", "request_id": rid, "size": min_block_size} for rid in ids]
    # Free every other one -> fragmented free list, no two adjacent free buddies.
    for i, rid in enumerate(ids):
        if i % 2 == 0:
            ops.append({"op": "free", "request_id": rid})

    # Now request something bigger than a single min_block_size fragment.
    big_request_size = min(total_memory, min_block_size * 4)
    ops.append({"op": "alloc", "request_id": "FRAG_TEST", "size": big_request_size})
    return ops


def _build_overflow(cfg: Dict, rng: random.Random) -> List[Dict[str, Any]]:
    """A single request larger than total_memory -> guaranteed immediate failure."""
    return [{"op": "alloc", "request_id": "OVERFLOW", "size": cfg["total_memory"] * 4}]


def _build_invalid_ops(cfg: Dict, rng: random.Random) -> List[Dict[str, Any]]:
    """Normal alloc/free plus a double-free and a free of a never-allocated id."""
    ids = _request_ids(min(cfg["num_base_requests"], 3))
    ops = [{"op": "alloc", "request_id": rid,
            "size": _random_size(cfg["total_memory"], cfg["min_block_size"], rng)}
           for rid in ids]
    first = ids[0]
    ops.append({"op": "free", "request_id": first})
    ops.append({"op": "free", "request_id": first})          # double free
    ops.append({"op": "free", "request_id": "NEVER_ALLOCATED"})  # unknown id
    # Clean up remaining live allocations.
    for rid in ids[1:]:
        ops.append({"op": "free", "request_id": rid})
    return ops


MODE_BUILDERS = {
    "sequential": _build_sequential,
    "interleaved": _build_interleaved,
    "fragmentation": _build_fragmentation,
    "overflow": _build_overflow,
    "invalid_ops": _build_invalid_ops,
}


# ══════════════════════════════════════════════════════════════════════════
# TOP-LEVEL GENERATION
# ══════════════════════════════════════════════════════════════════════════

def generate_buddy_instances(seed: int = 44) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    instances = []

    for level, cfg in BUDDY_COMPLEXITY.items():
        for mode in MODES:
            operations = MODE_BUILDERS[mode](cfg, rng)
            gt = solve_buddy_system(cfg["total_memory"], cfg["min_block_size"], operations)
            instances.append({
                "instance_id": f"buddy_{uuid.uuid4().hex[:12]}",
                "task": "buddy",
                "mode": mode,
                "complexity_level": level,
                "total_memory": cfg["total_memory"],
                "min_block_size": cfg["min_block_size"],
                "operations": operations,
                "ground_truth": gt,
            })

    return instances


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "data", "instances")
    os.makedirs(out_dir, exist_ok=True)

    buddy_instances = generate_buddy_instances()
    out_path = os.path.join(out_dir, "svac_buddy_instances.json")
    with open(out_path, "w") as f:
        json.dump(buddy_instances, f, indent=2)

    print(f"Generated {len(buddy_instances)} Buddy System instances -> {out_path}")

    # Sanity breakdown by mode and level
    from collections import Counter
    mode_counts = Counter(i["mode"] for i in buddy_instances)
    print("By mode:", dict(mode_counts))
    level_counts = Counter(i["complexity_level"] for i in buddy_instances)
    print("By level:", dict(sorted(level_counts.items())))

    failure_count = sum(1 for i in buddy_instances if not i["ground_truth"]["all_allocations_succeeded"])
    print(f"Instances containing at least one allocation FAILURE: {failure_count}")

    invalid_op_actions = {"double_free", "free_unknown_request", "free_failed_request"}
    edge_case_count = sum(
        1 for i in buddy_instances
        if any(s["action"] in invalid_op_actions for s in i["ground_truth"]["steps"])
    )
    print(f"Instances containing at least one invalid-operation edge case: {edge_case_count}")

    # Print one example instance so the format can be sanity-checked
    print("\n--- Example instance (Level 1, sequential mode) ---")
    example = next(i for i in buddy_instances if i["complexity_level"] == 1 and i["mode"] == "sequential")
    print(json.dumps(example, indent=2)[:900], "...")
