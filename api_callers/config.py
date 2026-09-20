"""
config.py
===========
Stores API keys used by the SVAC_Concurrency pipeline.

IMPORTANT:
  - Fill in YOUR OWN keys below (from Google AI Studio and OpenRouter).
  - NEVER commit this file to a public GitHub repo with real keys filled in
    (add "api_callers/config.py" to your .gitignore if you use git).
  - Both keys below are FREE TIER. Do NOT enable billing on the associated
    Google Cloud project -- free tier calls simply fail with a rate-limit
    error once you hit the quota; they never silently start charging you.

Where to get each key:
  GEMINI_API_KEY     -> https://aistudio.google.com/apikey  (sign in, "Create API Key")
  OPENROUTER_API_KEY -> https://openrouter.ai  (sign up, Profile -> Keys -> "Create Key")
"""

import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_API_KEY_HERE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")

# Model configurations
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "liquid/lfm-2.5-2.6b:free")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

