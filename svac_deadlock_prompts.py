"""
svac_deadlock_prompts.py
==========================
Builds the three SVAC prompt variants (zero-shot / few-shot / chain-of-
thought) for both Deadlock Detection sub-tasks (WFG cycle detection and
Banker's Algorithm), matching the prompting conventions used in Paper 4
(Page Replacement): strict "no code" system rule, fixed JSON output
schema, explicit field names matching the ground-truth solver's trace
format so scoring can align field-by-field.

Run this file directly to produce:
    data/prompts/svac_wfg_zero_shot_prompts.json
    data/prompts/svac_wfg_few_shot_prompts.json
    data/prompts/svac_wfg_cot_prompts.json
    data/prompts/svac_bankers_zero_shot_prompts.json
    data/prompts/svac_bankers_few_shot_prompts.json
    data/prompts/svac_bankers_cot_prompts.json
"""

import json
import os

SYSTEM_RULE = (
    "You must trace this algorithm MANUALLY, one step at a time, exactly as "
    "a human would on paper. You are STRICTLY FORBIDDEN from writing or "
    "executing any code, pseudocode, or code-like constructs (no Python, no "
    "loops, no variable assignment syntax). Any code in your response "
    "invalidates the entire answer. Respond ONLY with a single JSON object "
    "matching the schema below -- no prose before or after the JSON."
)


# ══════════════════════════════════════════════════════════════════════════
# WFG CYCLE DETECTION PROMPTS
# ══════════════════════════════════════════════════════════════════════════

WFG_ALGORITHM_RULES = """
ALGORITHM: Wait-For-Graph (WFG) Cycle Detection via DFS

You are given a directed graph where an edge "Pi -> Pj" means process Pi is
waiting for a resource currently held by process Pj. A cycle in this graph
means the processes involved are deadlocked (each is waiting on the next,
forming a closed loop with no way to proceed).

Perform a Depth-First Search starting from the processes in the order given.
Maintain two things at all times:
  - visited_set: the set of nodes that have been fully explored so far
  - recursion_stack: the current DFS path from the start node to your
    current position (this is NOT the same as visited_set -- a node leaves
    the recursion_stack when you backtrack from it, but stays in visited_set)

For each node you visit, before exploring its outgoing edges, record a
"visit" step. When you finish exploring all of a node's edges and are about
to backtrack, record a "backtrack" step. If, while exploring a node's edges,
you find an edge pointing to a node that is CURRENTLY in your recursion_stack
(not just visited_set), you have found a cycle -- record a "cycle_detected"
step and stop immediately (do not continue exploring further nodes).

Explore a node's outgoing edges in the exact order they are listed in the
input. Process the starting nodes in the exact order given.
"""

WFG_OUTPUT_SCHEMA = """
OUTPUT FORMAT (strict JSON, no other text):
{
  "steps": [
    {
      "step": <int, 1-indexed>,
      "action": "visit" | "backtrack" | "cycle_detected",
      "node": "<process name>",
      "visited_set": [<sorted list of process names fully explored so far>],
      "recursion_stack": [<current DFS path, in order>]
      // if action == "cycle_detected", also include:
      // "cycle": [<the sequence of nodes forming the cycle, ending back at the repeated node>]
    },
    ...
  ],
  "deadlock": true | false,
  "cycle_nodes": [<cycle sequence>] or null
}
"""

WFG_WORKED_EXAMPLE = """
WORKED EXAMPLE:
Processes: ["P0", "P1"]
Edges: {"P0": ["P1"], "P1": ["P0"]}

Correct output:
{
  "steps": [
    {"step": 1, "action": "visit", "node": "P0", "visited_set": ["P0"], "recursion_stack": ["P0"]},
    {"step": 2, "action": "visit", "node": "P1", "visited_set": ["P0", "P1"], "recursion_stack": ["P0", "P1"]},
    {"step": 3, "action": "cycle_detected", "node": "P0", "visited_set": ["P0", "P1"], "recursion_stack": ["P0", "P1"], "cycle": ["P0", "P1", "P0"]}
  ],
  "deadlock": true,
  "cycle_nodes": ["P0", "P1", "P0"]
}
"""


def build_wfg_prompt(instance: dict, variant: str) -> str:
    processes = instance["processes"]
    edges = instance["edges"]

    parts = [SYSTEM_RULE, WFG_ALGORITHM_RULES, WFG_OUTPUT_SCHEMA]

    if variant == "few_shot":
        parts.append(WFG_WORKED_EXAMPLE)

    if variant == "cot":
        parts.append(
            'For EACH step object, also include a "thought" field FIRST '
            '(before "step"), containing one short sentence explaining your '
            'reasoning for that step, e.g. "thought": "Checking P1\'s edges; '
            'P1 -> P2 and P2 is not in the recursion stack, so continue."'
        )

    parts.append(f"\nPROBLEM INSTANCE:\nProcesses (explore in this order): {processes}")
    parts.append(f"Edges: {json.dumps(edges)}")
    parts.append("\nNow produce the complete JSON trace.")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# BANKER'S ALGORITHM PROMPTS
# ══════════════════════════════════════════════════════════════════════════

BANKERS_ALGORITHM_RULES = """
ALGORITHM: Banker's Algorithm (Safety Algorithm)

You are given:
  - Available: a vector of currently available units for each resource type
  - Max: a matrix where Max[i][j] is the maximum units of resource j that
    process i may ever request
  - Allocation: a matrix where Allocation[i][j] is the units of resource j
    currently allocated to process i

First compute Need[i][j] = Max[i][j] - Allocation[i][j] for every process
and resource.

Then repeatedly scan the processes IN INDEX ORDER (P0, P1, P2, ...) looking
for a process i that is not yet finished and whose Need row is fully
satisfiable by the current Work vector (i.e. Need[i][j] <= Work[j] for all
j). On finding such a process:
  - record this as one step
  - add Allocation[i] to Work (Work[j] += Allocation[i][j] for all j)
  - mark process i as finished
  - restart the scan from P0 on the next round

If a full scan completes without finding ANY unfinished process whose Need
is satisfiable, the system is in an UNSAFE state -- record one final step
with candidate_process = null and stop.

If all processes become finished, the system is SAFE, and the order in
which processes finished is the safe sequence.
"""

BANKERS_OUTPUT_SCHEMA = """
OUTPUT FORMAT (strict JSON, no other text):
{
  "need_matrix": [[<Need[i][j] for each resource j>, ...], ...],
  "steps": [
    {
      "step": <int, 1-indexed>,
      "work_before": [<Work vector at the start of this step>],
      "candidate_process": <int index of chosen process, or null if none found>,
      "need_row": [<Need row of the candidate process>] or null,
      "work_after": [<Work vector after adding the candidate's allocation>] or null,
      "finish": [<finish[] boolean array state AFTER this step, for all processes in index order>]
    },
    ...
  ],
  "safe": true | false,
  "safe_sequence": ["P<index>", ...] or null
}
"""

BANKERS_WORKED_EXAMPLE = """
WORKED EXAMPLE:
Available: [2, 1]
Max: [[3, 2], [2, 2]]
Allocation: [[1, 1], [1, 0]]
(so Need = [[2,1], [1,2]])

Correct output:
{
  "need_matrix": [[2, 1], [1, 2]],
  "steps": [
    {"step": 1, "work_before": [2, 1], "candidate_process": 0, "need_row": [2, 1], "work_after": [3, 2], "finish": [true, false]},
    {"step": 2, "work_before": [3, 2], "candidate_process": 1, "need_row": [1, 2], "work_after": [4, 2], "finish": [true, true]}
  ],
  "safe": true,
  "safe_sequence": ["P0", "P1"]
}
"""


def build_bankers_prompt(instance: dict, variant: str) -> str:
    available = instance["available"]
    max_matrix = instance["max_matrix"]
    allocation = instance["allocation"]
    n = instance["num_processes"]

    parts = [SYSTEM_RULE, BANKERS_ALGORITHM_RULES, BANKERS_OUTPUT_SCHEMA]

    if variant == "few_shot":
        parts.append(BANKERS_WORKED_EXAMPLE)

    if variant == "cot":
        parts.append(
            'For EACH step object, also include a "thought" field FIRST '
            '(before "step"), containing one short sentence explaining which '
            'process you checked and why it did or did not qualify this round.'
        )

    parts.append(f"\nPROBLEM INSTANCE ({n} processes, indices P0..P{n-1}):")
    parts.append(f"Available: {available}")
    parts.append(f"Max: {max_matrix}")
    parts.append(f"Allocation: {allocation}")
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

    wfg_instances = _load(os.path.join(instances_dir, "svac_wfg_instances.json"))
    bankers_instances = _load(os.path.join(instances_dir, "svac_bankers_instances.json"))

    print("Building WFG prompts...")
    for variant in ["zero_shot", "few_shot", "cot"]:
        _build_variant_file(
            wfg_instances, build_wfg_prompt, variant,
            os.path.join(prompts_dir, f"svac_wfg_{variant}_prompts.json"))

    print("Building Banker's Algorithm prompts...")
    for variant in ["zero_shot", "few_shot", "cot"]:
        _build_variant_file(
            bankers_instances, build_bankers_prompt, variant,
            os.path.join(prompts_dir, f"svac_bankers_{variant}_prompts.json"))

    # Show one example prompt so you can sanity-check what the model will see
    print("\n" + "=" * 70)
    print("EXAMPLE ZERO-SHOT WFG PROMPT (first instance):")
    print("=" * 70)
    print(build_wfg_prompt(wfg_instances[0], "zero_shot"))
