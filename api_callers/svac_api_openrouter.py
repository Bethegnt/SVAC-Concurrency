"""
svac_api_openrouter.py
=========================
Sends SVAC_Concurrency prompts (deadlock, buddy, sync) to a free-tier
model on OpenRouter (default: nvidia/nemotron-3-ultra:free, set in
config.py) via OpenRouter's OpenAI-compatible chat completions endpoint,
and saves each raw response to svac_llm_responses/<model_slug>/.

USAGE:
    python api_callers/svac_api_openrouter.py                       # everything
    python api_callers/svac_api_openrouter.py --task mutex --limit 3  # cheap pilot
    python api_callers/svac_api_openrouter.py --variant cot            # one variant only

REQUIRES: `requests` (pip install requests --break-system-packages)
REQUIRES: config.py filled in with a real OPENROUTER_API_KEY.

SAFETY: this script hard-refuses to run if OPENROUTER_MODEL in config.py
does not end in ":free" -- this is a deliberate guard rail so a typo or a
copy-pasted paid model slug can never accidentally rack up a bill.
"""

from __future__ import annotations
import time
import sys
import os

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from svac_api_common import (
    load_prompts, already_done, save_response,
    make_arg_parser, tasks_and_variants_to_run,
)

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 5
TIMEOUT_SECONDS = 120


def model_slug() -> str:
    """Filesystem-safe folder name for this model's responses."""
    return OPENROUTER_MODEL.replace("/", "_").replace(":", "_")


def call_openrouter(prompt_text: str) -> dict:
    """
    Make one single-turn chat completion request to OpenRouter.
    Returns a dict: {"success": bool, "response_text": str, "meta": {...}}
    Never raises -- all failure modes are captured in the return value.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0.0,
        "max_tokens": 8192,
    }

    try:
        resp = requests.post(OPENROUTER_ENDPOINT, headers=headers, json=payload,
                              timeout=TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        return {"success": False, "response_text": "", "meta": {"error": f"network_error: {e}"}}

    if resp.status_code == 429:
        return {"success": False, "response_text": "",
                "meta": {"error": "rate_limited", "status_code": 429}}

    if resp.status_code != 200:
        return {"success": False, "response_text": "",
                "meta": {"error": f"http_{resp.status_code}", "body": resp.text[:500]}}

    data = resp.json()
    try:
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason", "unknown")
        text = choice["message"]["content"]
        usage = data.get("usage", {})
        return {
            "success": True,
            "response_text": text or "",
            "meta": {
                "finish_reason": finish_reason,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        }
    except (KeyError, IndexError) as e:
        return {"success": False, "response_text": "",
                "meta": {"error": f"unexpected_response_shape: {e}", "raw": str(data)[:500]}}


def call_with_retries(prompt_text: str, max_retries: int = MAX_RETRIES) -> dict:
    delay = 5
    for attempt in range(1, max_retries + 1):
        result = call_openrouter(prompt_text)
        if result["success"]:
            result["meta"]["attempts"] = attempt
            return result
        if result["meta"].get("error") == "rate_limited":
            print(f"      rate limited, backing off {delay}s (attempt {attempt}/{max_retries})...")
            time.sleep(delay)
            delay = min(delay * 2, 60)
        else:
            print(f"      call failed ({result['meta'].get('error')}), "
                  f"retrying in {delay}s (attempt {attempt}/{max_retries})...")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    result["meta"]["attempts"] = max_retries
    return result


def run(args):
    if OPENROUTER_API_KEY.startswith("PASTE_YOUR"):
        print("ERROR: config.py still has the placeholder OPENROUTER_API_KEY. "
              "Fill in your real key first (see config.py's docstring).")
        return

    if not OPENROUTER_MODEL.endswith(":free"):
        print(f"ERROR: OPENROUTER_MODEL is set to '{OPENROUTER_MODEL}', which does NOT "
              f"end in ':free'. Refusing to run -- this guard exists so a non-free model "
              f"can never accidentally be billed. Fix OPENROUTER_MODEL in config.py, or "
              f"check https://openrouter.ai/models?max_price=0 for valid free slugs.")
        return

    slug = model_slug()
    total_calls = 0
    total_skipped = 0
    total_failed = 0

    for task, variant in tasks_and_variants_to_run(args):
        prompts = load_prompts(task, variant)
        if args.limit:
            prompts = prompts[: args.limit]

        print(f"\n=== {task} / {variant} ({len(prompts)} prompts) ===")
        for entry in prompts:
            instance_id = entry["instance_id"]

            if already_done(slug, task, variant, instance_id):
                total_skipped += 1
                continue

            print(f"  calling: {instance_id} ...", end=" ", flush=True)
            result = call_with_retries(entry["prompt"])
            total_calls += 1

            if result["success"]:
                print(f"OK ({result['meta'].get('total_tokens', '?')} tokens)")
            else:
                total_failed += 1
                print(f"FAILED ({result['meta'].get('error')})")

            save_response(slug, task, variant, instance_id,
                           result["response_text"], result["meta"])

            time.sleep(args.sleep)

    print(f"\n{'=' * 60}")
    print(f"Done. Calls made: {total_calls} | Skipped (already done): {total_skipped} "
          f"| Failed: {total_failed}")
    print(f"Responses saved under: svac_llm_responses/{slug}/")


if __name__ == "__main__":
    parser = make_arg_parser(f"Send SVAC_Concurrency prompts to OpenRouter (free tier only).")
    args = parser.parse_args()
    run(args)
