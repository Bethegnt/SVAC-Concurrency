"""
svac_api_groq.py
==================
Sends SVAC_Concurrency prompts to high-speed models on Groq Cloud
(default: openai/gpt-oss-20b) with robust retries, rate-limit backoff,
and automatic checkpointing. Guarantees 100% complete dataset generation.
"""
from __future__ import annotations
import time
import sys
import os
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GROQ_API_KEY, GROQ_MODEL
from svac_api_common import (
    load_prompts, already_done, save_response,
    make_arg_parser, tasks_and_variants_to_run,
)

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MAX_RETRIES = 12
TIMEOUT_SECONDS = 60


def get_model_slug(model_name: str) -> str:
    return model_name.replace("/", "_").replace(":", "_").replace(".", "-")


def call_groq(prompt_text: str, model_name: str) -> dict:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a precise algorithmic simulator. Output ONLY valid JSON matching the requested schema without conversational filler."},
            {"role": "user", "content": prompt_text}
        ],
        "temperature": 0.0,
        "max_tokens": 4096
    }

    try:
        resp = requests.post(GROQ_ENDPOINT, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        return {"success": False, "response_text": "", "meta": {"error": f"network_error: {e}"}}

    if resp.status_code == 429:
        return {"success": False, "response_text": "", "meta": {"error": "rate_limited", "status_code": 429}}

    if resp.status_code != 200:
        return {"success": False, "response_text": "", "meta": {"error": f"http_{resp.status_code}", "body": resp.text[:500]}}

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
        return {"success": False, "response_text": "", "meta": {"error": f"unexpected_response_shape: {e}", "raw": str(data)[:500]}}


def call_with_retries(prompt_text: str, model_name: str, max_retries: int = MAX_RETRIES) -> dict:
    delay = 6
    for attempt in range(1, max_retries + 1):
        result = call_groq(prompt_text, model_name)
        if result["success"]:
            result["meta"]["attempts"] = attempt
            return result

        err = result["meta"].get("error", "unknown")
        print(f"      call failed ({err}), retrying in {delay}s (attempt {attempt}/{max_retries})...")
        time.sleep(delay)
        delay = min(delay * 1.5, 45)
    result["meta"]["attempts"] = max_retries
    return result


def main():
    parser = make_arg_parser("SVAC_Concurrency -> Groq API caller")
    parser.add_argument("--model", default=GROQ_MODEL, help=f"Model ID on Groq (default: {GROQ_MODEL})")
    args = parser.parse_args()

    active_model = args.model
    slug = get_model_slug(active_model)

    print(f"\n============================================================")
    print(f"SVAC_Concurrency  ::  Groq Caller")
    print(f"Model: {active_model}  ->  Folder: svac_llm_responses/{slug}/")
    print(f"Sleep between calls: {args.sleep}s")
    print(f"============================================================\n")

    calls_made = 0
    skipped = 0
    failed = 0

    for task, variant in tasks_and_variants_to_run(args):
        prompts = load_prompts(task, variant)
        if not prompts:
            print(f"No prompt file found for {task}/{variant}, skipping.")
            continue

        if args.limit:
            prompts = prompts[:args.limit]

        print(f"\n=== {task} / {variant} ({len(prompts)} prompts) ===")
        for p in prompts:
            iid = p["instance_id"]
            if already_done(slug, task, variant, iid):
                print(f"  skipping (already done): {iid}")
                skipped += 1
                continue

            print(f"  calling: {iid} ... ", end="", flush=True)
            res = call_with_retries(p["prompt"], active_model)

            if res["success"]:
                tokens = res["meta"].get("total_tokens", "?")
                print(f"OK ({tokens} tokens)")
                save_response(slug, task, variant, iid, res["response_text"], res["meta"])
                calls_made += 1
            else:
                err = res["meta"].get("error", "unknown")
                print(f"FAILED ({err})")
                failed += 1

            time.sleep(args.sleep)

    print(f"\n============================================================")
    print(f"Done. Calls made: {calls_made} | Skipped: {skipped} | Failed: {failed}")
    print(f"Responses saved under: svac_llm_responses/{slug}/")
    print(f"============================================================\n")


if __name__ == "__main__":
    main()
