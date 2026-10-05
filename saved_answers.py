"""Saved AI answers, so a busy Gemini doesn't break the demo.

Each renter's last good decision is saved with a fingerprint of every number the tools
returned. A saved answer is shown only when the fingerprint still matches: same renter
numbers, same rate. Anything changes -> the saved answer is ignored and Gemini is asked again.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from advisor import Advice, check_numbers, decide
from agent_tools import RenterTools

SAVED_FILE = Path(__file__).parent / "data" / "saved_answers.json"


def load(path=SAVED_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(store, path=SAVED_FILE):
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text(json.dumps(store, indent=1), encoding="utf-8")


def from_saved(entry):
    advice = Advice(status="decided", decision=entry["decision"],
                    explanation=entry["explanation"], model=entry["model"],
                    steps=entry["steps"], tool_results=entry["tool_results"])
    # Re-run the number check rather than trusting a stored result.
    advice.mismatches = check_numbers(advice.explanation, advice.tool_results)
    return advice


def peek(renter, rate, path=SAVED_FILE):
    """The saved answer if it still matches the renter's numbers, without calling Gemini.

    Returns (advice, saved_at), or (None, None) when nothing matching is saved.
    """
    entry = load(path).get(renter.id)
    if entry and entry.get("fingerprint") == RenterTools(renter, rate).fingerprint():
        return from_saved(entry), entry["saved_at"]
    return None, None


def get_advice(renter, rate, refresh=False, path=SAVED_FILE, decide_fn=decide, now=datetime.now):
    """The decision for one renter, plus where it came from.

    Returns (advice, source, saved_at): source is "saved", "live", or "none".
    - A matching saved answer is used unless refresh=True.
    - Otherwise Gemini runs; a decision that passes the number check is saved for next time.
    - If Gemini gives no decision but a matching saved answer exists, that is shown instead.
    """
    fingerprint = RenterTools(renter, rate).fingerprint()
    store = load(path)
    entry = store.get(renter.id)
    matches = entry is not None and entry.get("fingerprint") == fingerprint

    if matches and not refresh:
        return from_saved(entry), "saved", entry["saved_at"]

    advice = decide_fn(renter, rate, log=lambda line: None)
    if advice.status == "decided":   # check it here rather than trusting the caller did
        advice.mismatches = check_numbers(advice.explanation, advice.tool_results)
    if advice.status == "decided" and advice.mismatches:
        # Shown (with its flag), but never kept as the fallback: only good answers are saved.
        return advice, "live", None
    if advice.status == "decided":
        saved_at = now().strftime("%Y-%m-%d %H:%M")
        store[renter.id] = {"fingerprint": fingerprint, "saved_at": saved_at,
                            **{k: v for k, v in asdict(advice).items()
                               if k in ("decision", "explanation", "model", "steps", "tool_results")}}
        save(store, path)
        return advice, "live", saved_at
    if matches:
        fallback = from_saved(entry)
        fallback.reason = advice.reason or advice.message   # why the live try didn't work
        return fallback, "saved", entry["saved_at"]
    return advice, "none", None
