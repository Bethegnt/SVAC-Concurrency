"""
checkapi.py
==============
Quick connectivity and key-validity test. Run this FIRST, before any full
batch run, to confirm both API keys actually work -- uses ONE tiny request
per provider (a trivial prompt, not a real SVAC instance) so it costs
essentially nothing even against free-tier quotas.

USAGE:
    python api_callers/checkapi.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import GEMINI_API_KEY, OPENROUTER_API_KEY, GEMINI_MODEL, OPENROUTER_MODEL

TEST_PROMPT = 'Respond with exactly this JSON and nothing else: {"status": "ok"}'


def check_gemini():
    print("Checking Gemini API...")
    if GEMINI_API_KEY.startswith("PASTE_YOUR"):
        print("  SKIPPED: config.py still has the placeholder GEMINI_API_KEY.\n")
        return False

    from svac_api_gemini import call_gemini
    result = call_gemini(TEST_PROMPT)
    if result["success"]:
        print(f"  OK -- Gemini responded: {result['response_text'][:100]!r}")
        print(f"  Tokens used: {result['meta'].get('total_tokens')}\n")
        return True
    else:
        print(f"  FAILED: {result['meta']}\n")
        return False


def check_openrouter():
    print("Checking OpenRouter API...")
    if OPENROUTER_API_KEY.startswith("PASTE_YOUR"):
        print("  SKIPPED: config.py still has the placeholder OPENROUTER_API_KEY.\n")
        return False
    if not OPENROUTER_MODEL.endswith(":free"):
        print(f"  REFUSED: OPENROUTER_MODEL='{OPENROUTER_MODEL}' does not end in "
              f"':free' -- fix config.py before running anything.\n")
        return False

    from svac_api_openrouter import call_openrouter
    result = call_openrouter(TEST_PROMPT)
    if result["success"]:
        print(f"  OK -- OpenRouter ({OPENROUTER_MODEL}) responded: "
              f"{result['response_text'][:100]!r}")
        print(f"  Tokens used: {result['meta'].get('total_tokens')}\n")
        return True
    else:
        print(f"  FAILED: {result['meta']}\n")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("SVAC_Concurrency — API connectivity check")
    print("=" * 60)
    print(f"Gemini model configured:     {GEMINI_MODEL}")
    print(f"OpenRouter model configured: {OPENROUTER_MODEL}\n")

    gemini_ok = check_gemini()
    openrouter_ok = check_openrouter()

    print("=" * 60)
    if gemini_ok and openrouter_ok:
        print("BOTH providers working. Safe to run a pilot batch, e.g.:")
        print("  python api_callers/svac_api_gemini.py --task wfg --limit 3")
        print("  python api_callers/svac_api_openrouter.py --task wfg --limit 3")
    else:
        print("At least one provider failed or was skipped -- fix config.py "
              "and re-run this check before doing a full batch.")
