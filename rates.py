"""The mortgage rate the app uses: live from FRED if possible, otherwise the hardcoded default.

FRED series MORTGAGE30US is Freddie Mac's weekly average 30-year fixed rate. It needs a free
API key (FRED_API_KEY in .env). Any failure falls back silently so the demo never breaks.
"""

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

from dotenv import load_dotenv

from finance import DEFAULT_MORTGAGE_RATE, DEFAULT_RATE_AS_OF

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = "MORTGAGE30US"
TIMEOUT_SECONDS = 5


@dataclass
class MortgageRate:
    rate: float     # decimal, e.g. 0.0635
    as_of: str      # date of the observation, YYYY-MM-DD
    source: str     # what to show on screen
    is_live: bool


FALLBACK = MortgageRate(DEFAULT_MORTGAGE_RATE, DEFAULT_RATE_AS_OF,
                        "Default rate (project placeholder)", is_live=False)


def fetch_fred_json(api_key):
    query = urllib.parse.urlencode({"series_id": FRED_SERIES, "api_key": api_key,
                                    "file_type": "json", "sort_order": "desc", "limit": 10})
    with urllib.request.urlopen(f"{FRED_URL}?{query}", timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def latest_observation(data):
    """Newest week with a real number (FRED uses "." for missing weeks)."""
    for obs in data["observations"]:
        if obs["value"] not in (".", ""):
            return float(obs["value"]) / 100, obs["date"]
    raise ValueError("no usable observations")


def get_mortgage_rate(api_key=None, fetch=fetch_fred_json):
    """Live FRED rate, or the default if anything at all goes wrong."""
    if api_key is None:
        load_dotenv()
        api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return FALLBACK
    try:
        rate, as_of = latest_observation(fetch(api_key))
        if not 0.01 <= rate <= 0.20:  # sanity check: ignore anything absurd
            return FALLBACK
        return MortgageRate(rate, as_of, "Freddie Mac 30-year fixed average, via FRED", True)
    except Exception:
        return FALLBACK
