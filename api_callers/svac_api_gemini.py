"""
svac_api_gemini.py
=====================
Sends SVAC_Concurrency prompts (deadlock, buddy, sync) to Google's Gemini
API (free tier) via the raw REST endpoint, and saves each raw response to
svac_llm_responses/<model_slug>/.

USAGE:
    python api_callers/svac_api_gemini.py                       # everything
    python api_callers/svac_api_gemini.py --task wfg --limit 3  # cheap pilot
    python api_callers/svac_api_gemini.py --variant zero_shot   # one variant only

REQUIRES: `requests` (pip install requests --break-system-packages)
REQUIRES: config.py filled in with a real GEMINI_API_KEY (see config.py's
          own docstring for where to get one -- it is free, no billing
          needed).

This script makes ONLY single-turn, stateless completion requests -- no
tool use, no code execution, no multi-turn agent loop -- so the model's
response reflects pure manual reasoning, matching the "no code" constraint
baked into every SVAC prompt.
"""

from __future__ import annotations
import time
import sys
import os

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GEMINI_API_KEY, GEMINI_MODEL
from svac_api_common import (
    load_prompts, already_done, save_response,
    make_arg_parser, tasks_and_variants_to_run,
)

GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
MAX_RETRIES = 5
TIMEOUT_SECONDS = 120


def model_slug() -> str:
    """Filesystem-safe folder name for this model's responses."""
    return GEMINI_MODEL.replace(".", "-").replace("/", "_")


def call_gemini(prompt_text: str) -> dict:
    """
    Make one single-turn completion request to Gemini.
    Returns a dict: {"success": bool, "response_text": str, "meta": {...}}
    Never raises -- all failure modes are captured in the return value so
    the caller can decide whether to retry.
    """
    url = GEMINI_ENDPOINT_TEMPLATE.format(model=GEMINI_MODEL)
    params = {"key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.0,   # deterministic-as-possible sampling
            "maxOutputTokens": 8192,
        },
    }

    try:
        resp = requests.post(url, params=params, json=payload, timeout=TIMEOUT_SECONDS)
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
        candidate = data["candidates"][0]
        finish_reason = candidate.get("finishReason", "UNKNOWN")
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return {
            "success": True,
            "response_text": text,
            "meta": {
                "finish_reason": finish_reason,
                "prompt_tokens": usage.get("promptTokenCount"),
                "response_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            },
        }
    except (KeyError, IndexError) as e:
        return {"success": False, "response_text": "",
                "meta": {"error": f"unexpected_response_shape: {e}", "raw": str(data)[:500]}}


def call_with_retries(prompt_text: str, max_retries: int = MAX_RETRIES) -> dict:
    delay = 5
    for attempt in range(1, max_retries + 1):
        result = call_gemini(prompt_text)
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
    if GEMINI_API_KEY.startswith("PASTE_YOUR"):
        print("ERROR: config.py still has the placeholder GEMINI_API_KEY. "
              "Fill in your real key first (see config.py's docstring).")
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
    parser = make_arg_parser("Send SVAC_Concurrency prompts to Gemini (free tier).")
    args = parser.parse_args()
    run(args)
