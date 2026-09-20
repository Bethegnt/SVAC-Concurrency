"""
svac_api_common.py
=====================
Shared helpers used by both svac_api_gemini.py and svac_api_openrouter.py:
  - the registry of all 5 SVAC_Concurrency task types and 3 prompt variants
  - prompt-file loading
  - checkpointed response saving (skip instances already completed, so a
    run can be safely interrupted and resumed)
  - a tiny CLI arg parser shared by both callers (--task, --variant, --limit)

This mirrors the role of api_callers/config.py in the original Page
Replacement pipeline: infrastructure that both provider-specific callers
depend on, kept in one place so there is exactly one source of truth for
"where do prompts live" and "where do responses get saved".
"""

from __future__ import annotations
import json
import os
import argparse
from typing import List, Dict, Any

# All five task types across the three completed modules.
ALL_TASKS = ["wfg", "bankers", "buddy", "semaphore", "mutex"]
ALL_VARIANTS = ["zero_shot", "few_shot", "cot"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "data", "prompts")
RESPONSES_DIR = os.path.join(BASE_DIR, "svac_llm_responses")


def load_prompts(task: str, variant: str) -> List[Dict[str, Any]]:
    """Load the prompt list for one (task, variant) pair, e.g. ('wfg', 'zero_shot')."""
    path = os.path.join(PROMPTS_DIR, f"svac_{task}_{variant}_prompts.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No prompt file at {path}. Did you run the generator + prompt "
            f"scripts for '{task}' yet?"
        )
    with open(path) as f:
        return json.load(f)


def response_path(model_slug: str, task: str, variant: str, instance_id: str) -> str:
    """
    Deterministic path for a single instance's raw response, used both to
    write new responses and to check whether one already exists (checkpoint).
    model_slug should be filesystem-safe (e.g. "gemini-2-5-flash-lite" or
    "nvidia_nemotron-3-ultra_free" -- slashes/dots replaced by callers).
    """
    out_dir = os.path.join(RESPONSES_DIR, model_slug)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{task}__{variant}__{instance_id}.json")


def already_done(model_slug: str, task: str, variant: str, instance_id: str) -> bool:
    """
    A response counts as 'done' only if the file exists AND contains a
    non-empty response_text -- this way, empty/failed attempts (e.g. from
    a previous run that hit a rate limit mid-way) are correctly retried
    rather than silently skipped forever.
    """
    path = response_path(model_slug, task, variant, instance_id)
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            data = json.load(f)
        return bool(data.get("response_text", "").strip())
    except (json.JSONDecodeError, OSError):
        return False


def save_response(model_slug: str, task: str, variant: str, instance_id: str,
                   response_text: str, meta: Dict[str, Any]) -> None:
    """
    Save one raw LLM response to disk. `meta` should include whatever the
    provider call returned that's useful for debugging/reporting later:
    e.g. tokens used, latency, finish_reason, http status, retry count.
    """
    path = response_path(model_slug, task, variant, instance_id)
    payload = {
        "instance_id": instance_id,
        "task": task,
        "variant": variant,
        "model_slug": model_slug,
        "response_text": response_text,
        "meta": meta,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def make_arg_parser(description: str) -> argparse.ArgumentParser:
    """Shared CLI options for both provider callers."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--task", choices=ALL_TASKS, default=None,
                         help="Only run this task (default: all 5 tasks)")
    parser.add_argument("--variant", choices=ALL_VARIANTS, default=None,
                         help="Only run this prompt variant (default: all 3 variants)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Only send the first N prompts per (task, variant) pair "
                              "-- use this for a cheap pilot run before scaling up")
    parser.add_argument("--sleep", type=float, default=2.0,
                         help="Seconds to sleep between successive API calls "
                              "(stay well under free-tier rate limits)")
    return parser


def tasks_and_variants_to_run(args) -> List[tuple]:
    tasks = [args.task] if args.task else ALL_TASKS
    variants = [args.variant] if args.variant else ALL_VARIANTS
    return [(t, v) for t in tasks for v in variants]


if __name__ == "__main__":
    # Quick sanity check: confirm all 15 prompt files are present and loadable.
    print("Checking that all (task, variant) prompt files exist and parse...")
    missing = []
    for task in ALL_TASKS:
        for variant in ALL_VARIANTS:
            try:
                prompts = load_prompts(task, variant)
                print(f"  OK: {task:10s} / {variant:10s} -> {len(prompts)} prompts")
            except FileNotFoundError as e:
                missing.append((task, variant))
                print(f"  MISSING: {task} / {variant}")
    if missing:
        print(f"\n{len(missing)} prompt file(s) missing -- run the corresponding "
              f"generator + prompts scripts first.")
    else:
        print("\nAll 15 prompt files present and loadable.")
