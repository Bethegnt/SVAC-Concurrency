"""
svac_sync_prompts.py
========================
Builds the three SVAC prompt variants (zero-shot / few-shot / chain-of-
thought) for both Process Synchronization sub-tasks (Semaphore and Mutex),
following the exact conventions of svac_deadlock_prompts.py and
svac_buddy_prompts.py: strict "no code" system rule, a fixed JSON output
schema whose field names match the ground-truth solver's trace format
exactly, and worked examples generated DIRECTLY from the real solver
(never hand-written) for full consistency.

Run this file directly to produce:
    data/prompts/svac_semaphore_zero_shot_prompts.json
    data/prompts/svac_semaphore_few_shot_prompts.json
    data/prompts/svac_semaphore_cot_prompts.json
    data/prompts/svac_mutex_zero_shot_prompts.json
    data/prompts/svac_mutex_few_shot_prompts.json
    data/prompts/svac_mutex_cot_prompts.json
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "solvers"))
from svac_sync_solver import solve_semaphore_trace, solve_mutex_trace

# Reused verbatim from svac_deadlock_prompts.py / svac_buddy_prompts.py for
# consistency across the unified SVAC_Concurrency pipeline.
SYSTEM_RULE = (
    "You must trace this algorithm MANUALLY, one step at a time, exactly as "
    "a human would on paper. You are STRICTLY FORBIDDEN from writing or "
    "executing any code, pseudocode, or code-like constructs (no Python, no "
    "loops, no variable assignment syntax). Any code in your response "
    "invalidates the entire answer. Respond ONLY with a single JSON object "
    "matching the schema below -- no prose before or after the JSON."
)


# ══════════════════════════════════════════════════════════════════════════
# SEMAPHORE PROMPTS
# ══════════════════════════════════════════════════════════════════════════

SEMAPHORE_ALGORITHM_RULES = """
ALGORITHM: Counting Semaphore Trace (wait/signal, blocking implementation)

You are given a semaphore with an integer `value` and a FIFO `blocked_queue`
of threads currently waiting. You must process a sequence of wait() and
signal() calls, one per thread, IN THE EXACT ORDER GIVEN.

--- WAIT(thread) ---
- If value > 0: decrement value by 1. The thread proceeds immediately
  (it is NOT added to blocked_queue). Record action "wait_acquired".
- If value <= 0: append the thread to the END of blocked_queue. The
  thread is now blocked. Record action "wait_blocked". value does NOT
  change in this case.

--- SIGNAL(thread) ---
- If blocked_queue is NON-EMPTY: remove the thread at the FRONT of
  blocked_queue (FIFO order) and that thread proceeds immediately. This
  is a direct handoff -- value does NOT change. Record action
  "signal_handoff", and set "woken_thread" to the thread that was removed
  from the queue.
- If blocked_queue is EMPTY:
  - If a max_value bound is given AND value is already equal to
    max_value: this is an invalid operation (signalling past capacity
    with nobody waiting). Record action "invalid_over_signal". value does
    NOT change.
  - Otherwise: increment value by 1. Record action "signal_increment".

Process every operation in the input list, in order, without skipping any.
"""

SEMAPHORE_OUTPUT_SCHEMA = """
OUTPUT FORMAT (strict JSON, no other text):
{
  "steps": [
    {
      "step": <int, 1-indexed>,
      "op_index": <int, 0-indexed position of this operation in the input list>,
      "thread": "<string>",
      "action": "wait_acquired" | "wait_blocked" | "signal_handoff"
               | "signal_increment" | "invalid_over_signal",
      "value_before": <int>,
      "value_after": <int>,
      "blocked_queue_before": [<thread>, ...],
      "blocked_queue_after": [<thread>, ...],
      "woken_thread": "<thread>" or null   // only non-null for "signal_handoff"
    },
    ...
  ],
  "final_value": <int>,
  "final_blocked_queue": [<thread>, ...],
  "thread_final_state": { "<thread>": "running" | "blocked", ... }
}
"""


def _semaphore_worked_example() -> str:
    gt = solve_semaphore_trace(
        initial_value=0,
        operations=[
            {"thread": "T0", "op": "wait"},
            {"thread": "T1", "op": "signal"},
        ],
    )
    output = {
        "steps": gt["steps"],
        "final_value": gt["final_value"],
        "final_blocked_queue": gt["final_blocked_queue"],
        "thread_final_state": gt["thread_final_state"],
    }
    return (
        "\nWORKED EXAMPLE:\n"
        "initial_value: 0, max_value: null\n"
        'Operations: [{"thread": "T0", "op": "wait"}, {"thread": "T1", "op": "signal"}]\n\n'
        "Correct output:\n" + json.dumps(output, indent=2) + "\n"
    )


def build_semaphore_prompt(instance: dict, variant: str) -> str:
    initial_value = instance["initial_value"]
    max_value = instance["max_value"]
    operations = instance["operations"]

    parts = [SYSTEM_RULE, SEMAPHORE_ALGORITHM_RULES, SEMAPHORE_OUTPUT_SCHEMA]

    if variant == "few_shot":
        parts.append(_semaphore_worked_example())

    if variant == "cot":
        parts.append(
            'For EACH step object, also include a "thought" field FIRST '
            '(before "step"), containing one short sentence explaining your '
            'reasoning for that step, e.g. "thought": "value is currently 0 '
            'and nobody is queued, so T0 must block."'
        )

    parts.append(f"\nPROBLEM INSTANCE:\ninitial_value: {initial_value}")
    parts.append(f"max_value: {json.dumps(max_value)}  (null means unbounded)")
    parts.append(f"Operations (process in this exact order): {json.dumps(operations)}")
    parts.append("\nNow produce the complete JSON trace.")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# MUTEX PROMPTS
# ══════════════════════════════════════════════════════════════════════════

MUTEX_ALGORITHM_RULES = """
ALGORITHM: Mutex Lock/Unlock Trace (non-reentrant mutex)

You are given a mutex with a single `owner` (a thread name, or null if
unlocked) and a FIFO `wait_queue` of threads currently blocked trying to
acquire it. You must process a sequence of lock() and unlock() calls, one
per thread, IN THE EXACT ORDER GIVEN. This mutex is NON-REENTRANT: a
thread that locks a mutex it ALREADY owns does not succeed -- it blocks on
itself, just like any other thread would.

--- LOCK(thread) ---
- If owner is null (nobody holds it): the thread immediately becomes the
  owner. Record action "lock_acquired".
- If owner == thread (the thread already holds this exact mutex): the
  thread is appended to wait_queue and becomes blocked -- it is now
  waiting on a lock it itself holds, which can never be released by
  itself (a self-deadlock bug). Record action "lock_self_deadlock".
- If owner is some OTHER thread: the thread is appended to wait_queue and
  becomes blocked. Record action "lock_blocked".

--- UNLOCK(thread) ---
- If owner != thread (including owner == null, i.e. nobody holds it, or
  a DIFFERENT thread holds it): this is an invalid operation. Nothing
  changes. Record action "invalid_unlock".
- If owner == thread:
  - If wait_queue is NON-EMPTY: remove the thread at the FRONT of
    wait_queue (FIFO order) and that thread immediately becomes the new
    owner (a direct handoff). Record action "unlock_release_handoff", and
    set "woken_thread" to the thread that became the new owner.
  - If wait_queue is EMPTY: owner becomes null. Record action
    "unlock_release_idle".

Process every operation in the input list, in order, without skipping any.
"""

MUTEX_OUTPUT_SCHEMA = """
OUTPUT FORMAT (strict JSON, no other text):
{
  "steps": [
    {
      "step": <int, 1-indexed>,
      "op_index": <int, 0-indexed position of this operation in the input list>,
      "thread": "<string>",
      "action": "lock_acquired" | "lock_blocked" | "lock_self_deadlock"
               | "unlock_release_handoff" | "unlock_release_idle" | "invalid_unlock",
      "owner_before": "<thread>" or null,
      "owner_after": "<thread>" or null,
      "wait_queue_before": [<thread>, ...],
      "wait_queue_after": [<thread>, ...],
      "woken_thread": "<thread>" or null   // only non-null for "unlock_release_handoff"
    },
    ...
  ],
  "final_owner": "<thread>" or null,
  "final_wait_queue": [<thread>, ...],
  "thread_final_state": { "<thread>": "running" | "blocked", ... }
}
"""


def _mutex_worked_example() -> str:
    gt = solve_mutex_trace(
        operations=[
            {"thread": "T0", "op": "lock"},
            {"thread": "T1", "op": "lock"},
            {"thread": "T0", "op": "unlock"},
        ],
    )
    output = {
        "steps": gt["steps"],
        "final_owner": gt["final_owner"],
        "final_wait_queue": gt["final_wait_queue"],
        "thread_final_state": gt["thread_final_state"],
    }
    return (
        "\nWORKED EXAMPLE:\n"
        'Operations: [{"thread": "T0", "op": "lock"}, {"thread": "T1", "op": "lock"}, '
        '{"thread": "T0", "op": "unlock"}]\n\n'
        "Correct output:\n" + json.dumps(output, indent=2) + "\n"
    )


def build_mutex_prompt(instance: dict, variant: str) -> str:
    operations = instance["operations"]

    parts = [SYSTEM_RULE, MUTEX_ALGORITHM_RULES, MUTEX_OUTPUT_SCHEMA]

    if variant == "few_shot":
        parts.append(_mutex_worked_example())

    if variant == "cot":
        parts.append(
            'For EACH step object, also include a "thought" field FIRST '
            '(before "step"), containing one short sentence explaining your '
            'reasoning for that step, e.g. "thought": "T1 is already the '
            'owner, so T0 must queue and block."'
        )

    parts.append(f"\nPROBLEM INSTANCE:\nOperations (process in this exact order): {json.dumps(operations)}")
    parts.append("\nNow produce the complete JSON trace.")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def _load(path):
    with open(path) as f:
        return json.load(f)


def _build_variant_file(instances, builder_fn, variant, out_path):
    prompts = []
    for inst in instances:
        prompts.append({
            "instance_id": inst["instance_id"],
            "complexity_level": inst["complexity_level"],
            "mode": inst["mode"],
            "variant": variant,
            "prompt": builder_fn(inst, variant),
        })
    with open(out_path, "w") as f:
        json.dump(prompts, f, indent=2)
    print(f"  wrote {len(prompts)} prompts -> {out_path}")


if __name__ == "__main__":
    base = os.path.dirname(__file__)
    instances_dir = os.path.join(base, "data", "instances")
    prompts_dir = os.path.join(base, "data", "prompts")
    os.makedirs(prompts_dir, exist_ok=True)

    sem_instances = _load(os.path.join(instances_dir, "svac_semaphore_instances.json"))
    mtx_instances = _load(os.path.join(instances_dir, "svac_mutex_instances.json"))

    print("Building Semaphore prompts...")
    for variant in ["zero_shot", "few_shot", "cot"]:
        _build_variant_file(
            sem_instances, build_semaphore_prompt, variant,
            os.path.join(prompts_dir, f"svac_semaphore_{variant}_prompts.json"))

    print("Building Mutex prompts...")
    for variant in ["zero_shot", "few_shot", "cot"]:
        _build_variant_file(
            mtx_instances, build_mutex_prompt, variant,
            os.path.join(prompts_dir, f"svac_mutex_{variant}_prompts.json"))

    print("\n" + "=" * 70)
    print("EXAMPLE ZERO-SHOT SEMAPHORE PROMPT (first instance):")
    print("=" * 70)
    print(build_semaphore_prompt(sem_instances[0], "zero_shot"))
