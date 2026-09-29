"""Check that the API keys in .env are present and working. Never prints the keys.

Run: python check_keys.py
"""

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

from rates import get_mortgage_rate

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def check_gemini(key):
    request = urllib.request.Request(GEMINI_MODELS_URL, headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            models = [m["name"].removeprefix("models/") for m in json.load(response)["models"]
                      if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [m for m in models if "flash" in m]
        return True, f"works ({len(models)} models available, e.g. {', '.join(flash[:3])})"
    except urllib.error.HTTPError as e:
        return False, f"rejected by Google (HTTP {e.code}). Check the key was copied fully."
    except OSError:
        return False, "couldn't reach Google (internet connection?)"


def main():
    found = load_dotenv()
    print(f"Key file found: {'yes' if found else 'NO - copy .env.example to .env first'}")

    gemini = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini:
        ok, note = check_gemini(gemini)
        print(f"Gemini key: {note}")
    else:
        print("Gemini key: missing")

    fred = os.getenv("FRED_API_KEY", "").strip()
    rate = get_mortgage_rate()
    if not fred:
        print("FRED key: missing")
    elif rate.is_live:
        print(f"FRED key: works (30-year rate {rate.rate:.2%} as of {rate.as_of})")
    else:
        print("FRED key: present but the live call failed; the app will use the default rate")
    print(f"Rate the app will use: {rate.rate:.2%} as of {rate.as_of} - {rate.source}")


if __name__ == "__main__":
    main()
