"""
svac_buddy_prompts.py
========================
Builds the three SVAC prompt variants (zero-shot / few-shot / chain-of-
thought) for the Buddy System module, following the exact conventions of
svac_deadlock_prompts.py: strict "no code" system rule, a fixed JSON
output schema whose field names match the ground-truth solver's trace
format exactly (so scoring can align field-by-field), and the same
three-variant structure.

Run this file directly to produce:
    data/prompts/svac_buddy_zero_shot_prompts.json
    data/prompts/svac_buddy_few_shot_prompts.json
    data/prompts/svac_buddy_cot_prompts.json
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "solvers"))
from svac_buddy_solver import solve_buddy_system

# Reused verbatim from svac_deadlock_prompts.py for consistency across the
# unified SVAC_Concurrency pipeline.
SYSTEM_RULE = (
    "You must trace this algorithm MANUALLY, one step at a time, exactly as "
    "a human would on paper. You are STRICTLY FORBIDDEN from writing or "
    "executing any code, pseudocode, or code-like constructs (no Python, no "
    "loops, no variable assignment syntax). Any code in your response "
    "invalidates the entire answer. Respond ONLY with a single JSON object "
    "matching the schema below -- no prose before or after the JSON."
)


BUDDY_ALGORITHM_RULES = """
ALGORITHM: Buddy System Dynamic Memory Allocation

You are given a memory pool of size total_memory (a power of 2), and a
minimum allocatable block size min_block_size (also a power of 2). You must
process a sequence of ALLOC and FREE operations, maintaining a set of free
lists (one list per power-of-2 block size) at all times.

Initially, the ENTIRE pool is one single free block of size total_memory,
starting at address 0.

--- ALLOC(request_id, size) ---
1. Round `size` up to the smallest power of 2 that is >= size AND >=
   min_block_size. Call this value `need`.
2. Look through the free lists for the SMALLEST size class that is both
   >= need AND currently non-empty.
   - If no such size class exists, the allocation FAILS. Record one step
     with action "alloc_failed" (block_addr = null).
3. Otherwise, take the block with the SMALLEST starting address in that
   size class.
4. While the block's current size is STILL LARGER than `need`: split it
   into two equal halves.
   - The LOWER-address half is kept (for further splitting or final
     allocation).
   - The HIGHER-address half (its "buddy") is inserted into the free list
     for that half-size.
   - Record ONE step per split with action "split". "block_addr" is the
     starting address (the lower half you keep), "block_size" is the
     size BEFORE this split (i.e. double the new half-size),
     "buddy_addr" is the address of the newly freed higher half, and
     "resulting_block_size" is the size of each new half.
5. Once the block's size equals `need` exactly, it is granted to
   request_id. Record one step with action "alloc_placement",
   "block_addr" = the final address, "block_size" = need.

--- FREE(request_id) ---
1. Look up the address and size that were allocated to request_id.
   - If request_id was NEVER allocated, record one step with action
     "free_unknown_request" and stop (no state changes).
   - If request_id's allocation previously FAILED, record one step with
     action "free_failed_request" and stop (no state changes).
   - If request_id was ALREADY freed earlier, record one step with action
     "double_free" and stop (no state changes).
2. Otherwise, insert (address, size) into the free list for that size.
   Record one step with action "free_placement".
3. Coalescing loop: while the current block's size is less than
   total_memory:
   - Compute buddy_addr = block_addr XOR block_size.
   - If buddy_addr is ALSO currently present in the free list for this
     SAME size, merge them: remove BOTH addresses from that size's free
     list, and insert ONE new block of DOUBLE the size at address =
     min(block_addr, buddy_addr) into the free list for the new size.
     Record one step with action "coalesce" -- "block_addr"/"block_size"
     describe the NEW merged block, "buddy_addr" is the buddy just merged
     with, and "merged_from_size" is the size level you merged FROM (i.e.
     half of the new block_size).
   - If the buddy is NOT free, stop the coalescing loop.
4. After the coalescing loop ends (whether or not any merges happened),
   record one final step with action "free_settled" describing the
   block's final resting address and size.

IMPORTANT: after EVERY step (split, alloc_placement, alloc_failed,
free_placement, coalesce, free_settled, free_unknown_request, double_free,
free_failed_request), you must report the COMPLETE free_lists state as it
stands immediately after that step -- a dictionary mapping each non-empty
block size (as a string) to the SORTED list of starting addresses
currently free at that size. Omit any size with an empty free list.
"""

BUDDY_OUTPUT_SCHEMA = """
OUTPUT FORMAT (strict JSON, no other text):
{
  "steps": [
    {
      "step": <int, 1-indexed>,
      "op_index": <int, 0-indexed position of this operation in the input list>,
      "request_id": "<string>",
      "action": "split" | "alloc_placement" | "alloc_failed" | "free_placement"
               | "coalesce" | "free_settled" | "free_unknown_request"
               | "double_free" | "free_failed_request",
      "block_addr": <int> or null,
      "block_size": <int> or null,
      "free_lists": { "<size>": [<addr>, ...], ... }
      // include "buddy_addr" and "resulting_block_size" ONLY for "split" steps
      // include "buddy_addr" and "merged_from_size" ONLY for "coalesce" steps
    },
    ...
  ],
  "allocation_log": {
    "<request_id>": {"address": <int> or null, "block_size": <int>, "status": "allocated" | "failed" | "freed"},
    ...
  },
  "final_free_lists": { "<size>": [<addr>, ...], ... }
}
"""


def _build_worked_example() -> str:
    """
    Generate a small, fully worked example DIRECTLY from the real solver
    (never hand-written), guaranteeing the example is 100% consistent with
    the ground-truth format the model will be scored against.
    """
    gt = solve_buddy_system(
        total_memory=8, min_block_size=2,
        operations=[
            {"op": "alloc", "request_id": "A", "size": 3},
            {"op": "free", "request_id": "A"},
        ],
    )
    output = {
        "steps": gt["steps"],
        "allocation_log": gt["allocation_log"],
        "final_free_lists": gt["final_free_lists"],
    }
    return (
        "\nWORKED EXAMPLE:\n"
        "total_memory: 8, min_block_size: 2\n"
        'Operations: [{"op": "alloc", "request_id": "A", "size": 3}, '
        '{"op": "free", "request_id": "A"}]\n\n'
        "Correct output:\n" + json.dumps(output, indent=2) + "\n"
    )


def build_buddy_prompt(instance: dict, variant: str) -> str:
    total_memory = instance["total_memory"]
    min_block_size = instance["min_block_size"]
    operations = instance["operations"]

    parts = [SYSTEM_RULE, BUDDY_ALGORITHM_RULES, BUDDY_OUTPUT_SCHEMA]

    if variant == "few_shot":
        parts.append(_build_worked_example())

    if variant == "cot":
        parts.append(
            'For EACH step object, also include a "thought" field FIRST '
            '(before "step"), containing one short sentence explaining your '
            'reasoning for that step, e.g. "thought": "Need a block of size '
            '8 for this 5-unit request; smallest free block of size >= 8 is '
            'at address 0 with size 16, so split it."'
        )

    parts.append(f"\nPROBLEM INSTANCE:\ntotal_memory: {total_memory}")
    parts.append(f"min_block_size: {min_block_size}")
    parts.append(f"Operations (process in this exact order): {json.dumps(operations)}")
    parts.append("\nNow produce the complete JSON trace.")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def _load(path):
    with open(path) as f:
        return json.load(f)


def _build_variant_file(instances, variant, out_path):
    prompts = []
    for inst in instances:
        prompts.append({
            "instance_id": inst["instance_id"],
            "complexity_level": inst["complexity_level"],
            "mode": inst["mode"],
            "variant": variant,
            "prompt": build_buddy_prompt(inst, variant),
        })
    with open(out_path, "w") as f:
        json.dump(prompts, f, indent=2)
    print(f"  wrote {len(prompts)} prompts -> {out_path}")


if __name__ == "__main__":
    base = os.path.dirname(__file__)
    instances_dir = os.path.join(base, "data", "instances")
    prompts_dir = os.path.join(base, "data", "prompts")
    os.makedirs(prompts_dir, exist_ok=True)

    buddy_instances = _load(os.path.join(instances_dir, "svac_buddy_instances.json"))

    print("Building Buddy System prompts...")
    for variant in ["zero_shot", "few_shot", "cot"]:
        _build_variant_file(
            buddy_instances, variant,
            os.path.join(prompts_dir, f"svac_buddy_{variant}_prompts.json"))

    print("\n" + "=" * 70)
    print("EXAMPLE ZERO-SHOT BUDDY PROMPT (first instance):")
    print("=" * 70)
    print(build_buddy_prompt(buddy_instances[0], "zero_shot"))
