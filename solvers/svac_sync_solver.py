"""
svac_sync_solver.py
========================
Deterministic ground-truth solvers for the Process Synchronization module
of the SVAC (Step-Verifiable Algorithm Completions) benchmark.

Two sub-tasks are covered, matching svac_deadlock_solver.py's pattern of
housing two related sub-tasks in one file (there: WFG + Banker's; here:
Semaphore + Mutex):

  1. COUNTING SEMAPHORE (wait/signal trace)
     A semaphore has an integer `value` and a FIFO `blocked_queue` of
     threads currently waiting. This implementation uses the standard
     "blocking semaphore with explicit wait list" model taught in OS
     courses (as opposed to busy-waiting): a thread that calls wait()
     while value <= 0 is placed on the blocked_queue rather than
     decrementing value below zero; a thread that calls signal() first
     tries to wake the oldest blocked thread (handing the resource
     directly to it, value unchanged) and only increments value if no
     thread was waiting. An optional `max_value` models a BOUNDED
     semaphore (e.g. max_value=1 behaves like a binary semaphore) --
     signalling past max_value with nobody waiting is an invalid_over_signal.

  2. MUTEX (lock/unlock trace)
     A mutex has a single `owner` (or None) and a FIFO `wait_queue`. This
     implementation models a standard NON-REENTRANT mutex: a thread that
     locks a mutex it already owns blocks on itself (a classic
     self-deadlock bug), and unlock() by any thread other than the
     current owner is an invalid_unlock (rejected, no state change).

Both solvers are 100% deterministic: identical input always produces an
identical trace. No randomness lives in this file -- randomness belongs
only in the instance generator. No LLM/API calls anywhere in this file.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional


# ══════════════════════════════════════════════════════════════════════════
# 1. COUNTING SEMAPHORE TRACE
# ══════════════════════════════════════════════════════════════════════════

def solve_semaphore_trace(initial_value: int,
                           operations: List[Dict[str, Any]],
                           max_value: Optional[int] = None) -> Dict[str, Any]:
    """
    Trace a sequence of wait()/signal() calls on a single counting semaphore.

    Args:
        initial_value: starting value of the semaphore (>= 0)
        operations: ordered list of operation dicts, each one of:
            {"thread": "T0", "op": "wait"}
            {"thread": "T1", "op": "signal"}
        max_value: optional upper bound (e.g. 1 for a binary semaphore).
                   If None, the semaphore is unbounded and signal() always
                   succeeds by incrementing value when nobody is waiting.

    Returns:
        {
          "final_value": int,
          "final_blocked_queue": [...],
          "thread_final_state": {thread: "running"|"blocked"},
          "steps": [ ... trace ... ]
        }

    Each step has the shape:
        {
          "step": int,                 # 1-indexed
          "op_index": int,              # 0-indexed position in `operations`
          "thread": str,                # thread performing this call
          "action": "wait_acquired" | "wait_blocked" |
                    "signal_handoff" | "signal_increment" |
                    "invalid_over_signal",
          "value_before": int,
          "value_after": int,
          "blocked_queue_before": [...],
          "blocked_queue_after": [...],
          "woken_thread": str or None,  # only set for "signal_handoff"
        }
    """
    value = initial_value
    blocked_queue: List[str] = []
    thread_state: Dict[str, str] = {}
    steps: List[Dict[str, Any]] = []
    step_counter = 0

    def record(op_index, thread, action, value_before, value_after,
               bq_before, bq_after, woken_thread=None):
        nonlocal step_counter
        step_counter += 1
        steps.append({
            "step": step_counter,
            "op_index": op_index,
            "thread": thread,
            "action": action,
            "value_before": value_before,
            "value_after": value_after,
            "blocked_queue_before": list(bq_before),
            "blocked_queue_after": list(bq_after),
            "woken_thread": woken_thread,
        })

    for op_index, op in enumerate(operations):
        thread = op["thread"]
        call = op["op"]
        bq_before = list(blocked_queue)
        value_before = value

        if call == "wait":
            if value > 0:
                value -= 1
                thread_state[thread] = "running"
                record(op_index, thread, "wait_acquired", value_before, value,
                       bq_before, blocked_queue)
            else:
                blocked_queue.append(thread)
                thread_state[thread] = "blocked"
                record(op_index, thread, "wait_blocked", value_before, value,
                       bq_before, blocked_queue)

        elif call == "signal":
            if blocked_queue:
                woken = blocked_queue.pop(0)
                thread_state[woken] = "running"
                # value is unchanged: the resource is handed directly to
                # the woken thread rather than incrementing then re-decrementing.
                record(op_index, thread, "signal_handoff", value_before, value,
                       bq_before, blocked_queue, woken_thread=woken)
            else:
                if max_value is not None and value >= max_value:
                    record(op_index, thread, "invalid_over_signal", value_before,
                           value, bq_before, blocked_queue)
                else:
                    value += 1
                    record(op_index, thread, "signal_increment", value_before,
                           value, bq_before, blocked_queue)
        else:
            raise ValueError(f"Unknown semaphore operation: {call}")

    return {
        "final_value": value,
        "final_blocked_queue": list(blocked_queue),
        "thread_final_state": thread_state,
        "steps": steps,
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. MUTEX (LOCK/UNLOCK) TRACE
# ══════════════════════════════════════════════════════════════════════════

def solve_mutex_trace(operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Trace a sequence of lock()/unlock() calls on a single NON-REENTRANT mutex.

    Args:
        operations: ordered list of operation dicts, each one of:
            {"thread": "T0", "op": "lock"}
            {"thread": "T0", "op": "unlock"}

    Returns:
        {
          "final_owner": str or None,
          "final_wait_queue": [...],
          "thread_final_state": {thread: "running"|"blocked"},
          "steps": [ ... trace ... ]
        }

    Each step has the shape:
        {
          "step": int,
          "op_index": int,
          "thread": str,
          "action": "lock_acquired" | "lock_blocked" | "lock_self_deadlock" |
                    "unlock_release_handoff" | "unlock_release_idle" |
                    "invalid_unlock",
          "owner_before": str or None,
          "owner_after": str or None,
          "wait_queue_before": [...],
          "wait_queue_after": [...],
          "woken_thread": str or None,   # only set for "unlock_release_handoff"
        }
    """
    owner: Optional[str] = None
    wait_queue: List[str] = []
    thread_state: Dict[str, str] = {}
    steps: List[Dict[str, Any]] = []
    step_counter = 0

    def record(op_index, thread, action, owner_before, owner_after,
               wq_before, wq_after, woken_thread=None):
        nonlocal step_counter
        step_counter += 1
        steps.append({
            "step": step_counter,
            "op_index": op_index,
            "thread": thread,
            "action": action,
            "owner_before": owner_before,
            "owner_after": owner_after,
            "wait_queue_before": list(wq_before),
            "wait_queue_after": list(wq_after),
            "woken_thread": woken_thread,
        })

    for op_index, op in enumerate(operations):
        thread = op["thread"]
        call = op["op"]
        wq_before = list(wait_queue)
        owner_before = owner

        if call == "lock":
            if owner is None:
                owner = thread
                thread_state[thread] = "running"
                record(op_index, thread, "lock_acquired", owner_before, owner,
                       wq_before, wait_queue)
            elif owner == thread:
                # Non-reentrant mutex: locking a mutex you already hold
                # blocks forever on yourself -- a classic self-deadlock bug.
                wait_queue.append(thread)
                thread_state[thread] = "blocked"
                record(op_index, thread, "lock_self_deadlock", owner_before,
                       owner, wq_before, wait_queue)
            else:
                wait_queue.append(thread)
                thread_state[thread] = "blocked"
                record(op_index, thread, "lock_blocked", owner_before, owner,
                       wq_before, wait_queue)

        elif call == "unlock":
            if owner != thread:
                # Either nobody owns it, or a different thread owns it --
                # both are invalid unlocks. No state change.
                record(op_index, thread, "invalid_unlock", owner_before,
                       owner_before, wq_before, wait_queue)
            else:
                if wait_queue:
                    next_owner = wait_queue.pop(0)
                    owner = next_owner
                    thread_state[next_owner] = "running"
                    record(op_index, thread, "unlock_release_handoff",
                           owner_before, owner, wq_before, wait_queue,
                           woken_thread=next_owner)
                else:
                    owner = None
                    record(op_index, thread, "unlock_release_idle",
                           owner_before, owner, wq_before, wait_queue)
        else:
            raise ValueError(f"Unknown mutex operation: {call}")

    return {
        "final_owner": owner,
        "final_wait_queue": list(wait_queue),
        "thread_final_state": thread_state,
        "steps": steps,
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. SELF-TEST (hand-verifiable examples — run this file directly to verify)
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("TEST 1: Semaphore — classic producer/consumer, value starts at 0")
    print("T0 waits (blocks, value=0), T1 signals (hands off directly to T0)")
    print("=" * 70)
    result1 = solve_semaphore_trace(
        initial_value=0,
        operations=[
            {"thread": "T0", "op": "wait"},
            {"thread": "T1", "op": "signal"},
        ],
    )
    for s in result1["steps"]:
        print(" ", s)
    assert result1["steps"][0]["action"] == "wait_blocked"
    assert result1["steps"][1]["action"] == "signal_handoff"
    assert result1["steps"][1]["woken_thread"] == "T0"
    assert result1["final_value"] == 0  # handoff, not increment
    print("PASS\n")

    print("=" * 70)
    print("TEST 2: Semaphore — value=1, single wait succeeds immediately")
    print("=" * 70)
    result2 = solve_semaphore_trace(
        initial_value=1,
        operations=[{"thread": "T0", "op": "wait"}],
    )
    for s in result2["steps"]:
        print(" ", s)
    assert result2["steps"][0]["action"] == "wait_acquired"
    assert result2["final_value"] == 0
    print("PASS\n")

    print("=" * 70)
    print("TEST 3: Semaphore — bounded (max_value=1, binary semaphore),")
    print("signalling when already at max with nobody waiting -> invalid")
    print("=" * 70)
    result3 = solve_semaphore_trace(
        initial_value=1, max_value=1,
        operations=[{"thread": "T0", "op": "signal"}],
    )
    for s in result3["steps"]:
        print(" ", s)
    assert result3["steps"][0]["action"] == "invalid_over_signal"
    assert result3["final_value"] == 1  # unchanged
    print("PASS\n")

    print("=" * 70)
    print("TEST 4: Mutex — simple lock/unlock, no contention")
    print("=" * 70)
    result4 = solve_mutex_trace(
        operations=[
            {"thread": "T0", "op": "lock"},
            {"thread": "T0", "op": "unlock"},
        ],
    )
    for s in result4["steps"]:
        print(" ", s)
    assert result4["steps"][0]["action"] == "lock_acquired"
    assert result4["steps"][1]["action"] == "unlock_release_idle"
    assert result4["final_owner"] is None
    print("PASS\n")

    print("=" * 70)
    print("TEST 5: Mutex — contention with handoff")
    print("T0 locks, T1 tries to lock (blocks), T0 unlocks (hands off to T1)")
    print("=" * 70)
    result5 = solve_mutex_trace(
        operations=[
            {"thread": "T0", "op": "lock"},
            {"thread": "T1", "op": "lock"},
            {"thread": "T0", "op": "unlock"},
        ],
    )
    for s in result5["steps"]:
        print(" ", s)
    assert result5["steps"][1]["action"] == "lock_blocked"
    assert result5["steps"][2]["action"] == "unlock_release_handoff"
    assert result5["steps"][2]["woken_thread"] == "T1"
    assert result5["final_owner"] == "T1"
    print("PASS\n")

    print("=" * 70)
    print("TEST 6: Mutex — edge cases: invalid_unlock and self-deadlock")
    print("=" * 70)
    result6 = solve_mutex_trace(
        operations=[
            {"thread": "T1", "op": "unlock"},   # invalid: nobody owns it
            {"thread": "T0", "op": "lock"},      # T0 acquires
            {"thread": "T0", "op": "lock"},      # T0 relocks itself -> self-deadlock
            {"thread": "T1", "op": "unlock"},    # invalid: T1 doesn't own it
        ],
    )
    for s in result6["steps"]:
        print(" ", s)
    actions = [s["action"] for s in result6["steps"]]
    assert actions == ["invalid_unlock", "lock_acquired", "lock_self_deadlock", "invalid_unlock"]
    assert result6["thread_final_state"]["T0"] == "blocked"  # T0 deadlocked on itself
    print("PASS\n")

    print("ALL SELF-TESTS PASSED.")
