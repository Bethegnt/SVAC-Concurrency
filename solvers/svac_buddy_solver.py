"""
svac_buddy_solver.py
========================
Deterministic ground-truth solver for the Buddy System (dynamic memory
allocation) module of the SVAC (Step-Verifiable Algorithm Completions)
benchmark.

Follows the exact conventions established in svac_deadlock_solver.py:
  - A single pure function takes a fully-specified problem instance and
    returns a dict containing a step-by-step trace plus a final summary.
  - Every step records the FULL relevant state snapshot after the action
    (mirrors visited_set/recursion_stack in the deadlock solver -- here
    it is the free_lists snapshot).
  - 100% deterministic: identical input always produces an identical
    trace. All randomness lives in the instance generator, never here.
  - No LLM/API calls anywhere in this file.

ALGORITHM BACKGROUND: The Buddy System manages a memory pool of size
`total_memory` (must be a power of 2). Memory is allocated in blocks
whose size is always a power of 2, no smaller than `min_block_size`.

  ALLOCATION (request size S):
    1. Round S up to the smallest power of 2 that is >= S and >=
       min_block_size. Call this `need`.
    2. Find the SMALLEST free-list size class that is >= need and is
       non-empty. If none exists, allocation fails (not enough memory
       or too fragmented).
    3. Take the block with the SMALLEST starting address in that size
       class (deterministic tie-break, matching textbook convention).
    4. While the block's current size is larger than `need`: split it
       in half. The LOWER-address half is kept (for further splitting
       or final allocation); the HIGHER-address half ("buddy") is
       inserted into the free list for that half-size. Each split is
       recorded as one trace step.
    5. Once the block reaches exactly `need`, it is granted to the
       requester. Recorded as one trace step.

  DEALLOCATION (free a previously allocated block at address A, size S):
    1. Insert (A, S) back into the free list for size S. Recorded as
       one trace step.
    2. Coalescing loop: compute the buddy address as (A XOR S). If that
       buddy is ALSO currently in the free list at size S, remove BOTH
       blocks from the size-S free list, merge them into a single block
       of size 2*S at address min(A, buddy), and repeat the check one
       level up. Each successful merge is recorded as one trace step.
       Stop when the buddy is not free, or the block has grown back to
       `total_memory`. A final "free_settled" step records the resting
       state.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _round_up_to_block_size(requested_size: int, min_block_size: int) -> int:
    """Smallest power-of-2 block size that is >= requested_size and >= min_block_size."""
    size = min_block_size
    while size < requested_size:
        size *= 2
    return size


def _free_lists_snapshot(free_lists: Dict[int, List[int]]) -> Dict[str, List[int]]:
    """String-keyed, sorted, empty-list-filtered snapshot for JSON-friendly output."""
    return {str(size): sorted(addrs) for size, addrs in free_lists.items() if addrs}


# ══════════════════════════════════════════════════════════════════════════
# MAIN SOLVER
# ══════════════════════════════════════════════════════════════════════════

def solve_buddy_system(total_memory: int,
                        min_block_size: int,
                        operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Trace a sequence of alloc/free operations through the Buddy System.

    Args:
        total_memory: total pool size in units (must be a power of 2)
        min_block_size: smallest allocatable block size (must be a power of 2,
                         and must divide total_memory evenly as a power-of-2 factor)
        operations: ordered list of operation dicts, each one of:
            {"op": "alloc", "request_id": "A", "size": 100}
            {"op": "free",  "request_id": "A"}

    Returns:
        {
          "total_memory": int,
          "min_block_size": int,
          "allocation_log": {
              request_id: {"address": int|None, "block_size": int, "status": str}
              # status in {"allocated", "failed", "freed"}
          },
          "final_free_lists": {"<size>": [addr, ...], ...},
          "all_allocations_succeeded": bool,
          "steps": [ ... trace ... ]
        }

    Each step has the shape:
        {
          "step": int,                 # 1-indexed
          "op_index": int,              # 0-indexed position in `operations`
          "request_id": str,
          "action": one of "split", "alloc_placement", "alloc_failed",
                    "free_placement", "coalesce", "free_settled",
                    "free_unknown_request", "double_free", "free_failed_request",
          "block_addr": int or None,
          "block_size": int or None,
          "free_lists": {"<size>": [addr, ...], ...},   # snapshot AFTER this step
          # action-specific extra fields (present only when relevant):
          "buddy_addr": int,
          "resulting_block_size": int,   # for "split": the size of each new half
          "merged_from_size": int,       # for "coalesce": the size level merged FROM
        }
    """
    if not _is_power_of_two(total_memory):
        raise ValueError(f"total_memory must be a power of 2, got {total_memory}")
    if not _is_power_of_two(min_block_size):
        raise ValueError(f"min_block_size must be a power of 2, got {min_block_size}")
    if min_block_size > total_memory:
        raise ValueError("min_block_size cannot exceed total_memory")

    free_lists: Dict[int, List[int]] = {total_memory: [0]}
    allocation_log: Dict[str, Dict[str, Any]] = {}
    steps: List[Dict[str, Any]] = []
    step_counter = [0]

    def record(op_index: int, request_id: str, action: str,
               block_addr: Optional[int], block_size: Optional[int],
               extra: Optional[Dict[str, Any]] = None):
        step_counter[0] += 1
        entry = {
            "step": step_counter[0],
            "op_index": op_index,
            "request_id": request_id,
            "action": action,
            "block_addr": block_addr,
            "block_size": block_size,
            "free_lists": _free_lists_snapshot(free_lists),
        }
        if extra:
            entry.update(extra)
        steps.append(entry)

    def do_alloc(op_index: int, request_id: str, size: int):
        if size <= 0:
            record(op_index, request_id, "alloc_failed", None, None,
                   {"reason": "non_positive_size"})
            allocation_log[request_id] = {"address": None, "block_size": 0, "status": "failed"}
            return

        need = _round_up_to_block_size(size, min_block_size)

        candidate_sizes = sorted(s for s, addrs in free_lists.items() if addrs and s >= need)
        if not candidate_sizes:
            record(op_index, request_id, "alloc_failed", None, need,
                   {"reason": "no_sufficient_free_block"})
            allocation_log[request_id] = {"address": None, "block_size": need, "status": "failed"}
            return

        chosen_size = candidate_sizes[0]
        free_lists[chosen_size].sort()
        addr = free_lists[chosen_size].pop(0)
        current_size = chosen_size

        while current_size > need:
            current_size //= 2
            buddy_addr = addr + current_size
            free_lists.setdefault(current_size, [])
            free_lists[current_size].append(buddy_addr)
            record(op_index, request_id, "split", addr, current_size * 2,
                   {"buddy_addr": buddy_addr, "resulting_block_size": current_size})

        allocation_log[request_id] = {"address": addr, "block_size": need, "status": "allocated"}
        record(op_index, request_id, "alloc_placement", addr, need)

    def do_free(op_index: int, request_id: str):
        info = allocation_log.get(request_id)

        if info is None:
            record(op_index, request_id, "free_unknown_request", None, None)
            return
        if info["status"] == "freed":
            record(op_index, request_id, "double_free", info["address"], info["block_size"])
            return
        if info["status"] == "failed":
            record(op_index, request_id, "free_failed_request", None, info["block_size"])
            return

        addr = info["address"]
        size = info["block_size"]
        allocation_log[request_id]["status"] = "freed"

        free_lists.setdefault(size, [])
        free_lists[size].append(addr)
        record(op_index, request_id, "free_placement", addr, size)

        # Coalescing loop: keep merging with the buddy as long as it is free.
        while size < total_memory:
            buddy_addr = addr ^ size
            if buddy_addr in free_lists.get(size, []):
                free_lists[size].remove(addr)
                free_lists[size].remove(buddy_addr)
                merged_addr = min(addr, buddy_addr)
                merged_from_size = size
                size *= 2
                addr = merged_addr
                free_lists.setdefault(size, [])
                free_lists[size].append(addr)
                record(op_index, request_id, "coalesce", addr, size,
                       {"buddy_addr": buddy_addr, "merged_from_size": merged_from_size})
            else:
                break

        record(op_index, request_id, "free_settled", addr, size)

    for op_index, op in enumerate(operations):
        if op["op"] == "alloc":
            do_alloc(op_index, op["request_id"], op["size"])
        elif op["op"] == "free":
            do_free(op_index, op["request_id"])
        else:
            raise ValueError(f"Unknown operation type: {op['op']}")

    all_succeeded = all(entry["status"] != "failed" for entry in allocation_log.values())

    return {
        "total_memory": total_memory,
        "min_block_size": min_block_size,
        "allocation_log": allocation_log,
        "final_free_lists": _free_lists_snapshot(free_lists),
        "all_allocations_succeeded": all_succeeded,
        "steps": steps,
    }


# ══════════════════════════════════════════════════════════════════════════
# SELF-TEST (hand-verifiable examples — run this file directly to verify)
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    print("=" * 70)
    print("TEST 1: Single alloc + free, full coalesce back to original block")
    print("total_memory=8, min_block_size=2, alloc A(size=3), free A")
    print("Expect: split 8->4+4, alloc A at addr0 size4, free+coalesce back to {8:[0]}")
    print("=" * 70)
    result1 = solve_buddy_system(
        total_memory=8, min_block_size=2,
        operations=[
            {"op": "alloc", "request_id": "A", "size": 3},
            {"op": "free", "request_id": "A"},
        ],
    )
    for s in result1["steps"]:
        print(" ", s)
    print("Final free_lists:", result1["final_free_lists"])
    assert result1["final_free_lists"] == {"8": [0]}, "Expected full coalesce back to single block!"
    print("PASS: memory fully coalesced back to original single free block.\n")

    print("=" * 70)
    print("TEST 2: Two allocations that are NOT buddies -> no coalesce on free")
    print("total_memory=16, min_block_size=2")
    print("alloc A(size=3)->need4 at addr0 (splits 16->8+8->4+4)")
    print("alloc B(size=3)->need4, should land at addr4 (buddy of A's block)")
    print("free A only -> A's block(addr0,size4) should NOT merge (B at addr4 still allocated)")
    print("=" * 70)
    result2 = solve_buddy_system(
        total_memory=16, min_block_size=2,
        operations=[
            {"op": "alloc", "request_id": "A", "size": 3},
            {"op": "alloc", "request_id": "B", "size": 3},
            {"op": "free", "request_id": "A"},
        ],
    )
    for s in result2["steps"]:
        print(" ", s)
    print("Final free_lists:", result2["final_free_lists"])
    # A's block (addr0, size4) is free but its buddy (addr4) is still allocated to B,
    # so no coalesce should happen -- addr0 stays alone at size4.
    assert result2["final_free_lists"].get("4") == [0], "A's freed block should stay unmerged!"
    print("PASS: correctly did NOT coalesce (buddy still allocated).\n")

    print("=" * 70)
    print("TEST 3: Allocation failure — request larger than total_memory")
    print("total_memory=8, min_block_size=2, alloc A(size=100)")
    print("=" * 70)
    result3 = solve_buddy_system(
        total_memory=8, min_block_size=2,
        operations=[{"op": "alloc", "request_id": "A", "size": 100}],
    )
    for s in result3["steps"]:
        print(" ", s)
    assert result3["allocation_log"]["A"]["status"] == "failed"
    assert result3["all_allocations_succeeded"] is False
    print("PASS: correctly reported allocation failure.\n")

    print("=" * 70)
    print("TEST 4: Fragmentation-induced failure — enough TOTAL free memory,")
    print("but no single block large enough (classic buddy-system pitfall)")
    print("total_memory=16, min_block_size=2")
    print("alloc A(size=4), alloc B(size=4), alloc C(size=4), free B")
    print("-> now 4 units free (B's block) + whatever's left, but can C-sized")
    print("   allocs still merge? We test alloc D(size=8) which needs a size-8")
    print("   block that does NOT exist due to fragmentation -> should fail")
    print("=" * 70)
    result4 = solve_buddy_system(
        total_memory=16, min_block_size=2,
        operations=[
            {"op": "alloc", "request_id": "A", "size": 4},
            {"op": "alloc", "request_id": "B", "size": 4},
            {"op": "alloc", "request_id": "C", "size": 4},
            {"op": "free", "request_id": "B"},
            {"op": "alloc", "request_id": "D", "size": 8},
        ],
    )
    for s in result4["steps"]:
        print(" ", s)
    print("Allocation log:", json.dumps(result4["allocation_log"], indent=2))
    assert result4["allocation_log"]["D"]["status"] == "failed", "D should fail due to fragmentation!"
    print("PASS: correctly demonstrated fragmentation-induced allocation failure.\n")

    print("=" * 70)
    print("TEST 5: Edge cases — double free, free of unknown request")
    print("=" * 70)
    result5 = solve_buddy_system(
        total_memory=8, min_block_size=2,
        operations=[
            {"op": "alloc", "request_id": "A", "size": 2},
            {"op": "free", "request_id": "A"},
            {"op": "free", "request_id": "A"},        # double free
            {"op": "free", "request_id": "GHOST"},    # unknown request
        ],
    )
    for s in result5["steps"]:
        print(" ", s)
    actions = [s["action"] for s in result5["steps"]]
    assert "double_free" in actions
    assert "free_unknown_request" in actions
    print("PASS: double_free and free_unknown_request correctly detected.\n")

    print("=" * 70)
    print("TEST 6: Alloc request exactly equal to total_memory (no splits at all)")
    print("=" * 70)
    result6 = solve_buddy_system(
        total_memory=8, min_block_size=2,
        operations=[{"op": "alloc", "request_id": "A", "size": 8}],
    )
    for s in result6["steps"]:
        print(" ", s)
    assert len(result6["steps"]) == 1, "Exact-size alloc should need zero splits, just placement!"
    assert result6["steps"][0]["action"] == "alloc_placement"
    print("PASS: exact-size allocation used the whole block with no splitting.\n")

    print("ALL SELF-TESTS PASSED.")
