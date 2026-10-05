"""Saved answers: reused only when the renter's numbers are identical. No real Gemini calls."""

from dataclasses import replace
from datetime import datetime

import pytest

from advisor import Advice
from agent_tools import RenterTools
from rates import FALLBACK
from renters import load_renters
from saved_answers import get_advice, load, peek, save

RATE = replace(FALLBACK, rate=0.0703, as_of="2026-09-24")
MAYA = next(r for r in load_renters() if r.id == "maya")
NOW = lambda: datetime(2026, 10, 2, 14, 30)  # noqa: E731


def decided(explanation="Debt first: 21 months instead of 41 months."):
    tools = RenterTools(MAYA, RATE)
    results = [tools.run(t, {"renter_id": "maya"})[0]
               for t in ("project_debt_first", "project_deposit_first")]
    return Advice(status="decided", decision="debt_first", explanation=explanation,
                  model="fake-model", steps=["Step 1 -> ..."], tool_results=results)


class FakeDecide:
    def __init__(self, advice):
        self.advice, self.calls = advice, 0

    def __call__(self, renter, rate, log):
        self.calls += 1
        return self.advice


@pytest.fixture
def path(tmp_path):
    return tmp_path / "saved.json"


def test_first_live_answer_is_saved(path):
    fake = FakeDecide(decided())
    advice, source, saved_at = get_advice(MAYA, RATE, path=path, decide_fn=fake, now=NOW)
    assert (source, saved_at, fake.calls) == ("live", "2026-10-02 14:30", 1)
    assert load(path)["maya"]["decision"] == "debt_first"


def test_matching_saved_answer_is_reused_without_calling_gemini(path):
    get_advice(MAYA, RATE, path=path, decide_fn=FakeDecide(decided()), now=NOW)
    fake = FakeDecide(Advice(status="unavailable"))
    advice, source, saved_at = get_advice(MAYA, RATE, path=path, decide_fn=fake)
    assert fake.calls == 0
    assert source == "saved" and saved_at == "2026-10-02 14:30"
    assert advice.decision == "debt_first" and advice.mismatches == []


def test_changed_numbers_ignore_the_saved_answer(path):
    get_advice(MAYA, RATE, path=path, decide_fn=FakeDecide(decided()), now=NOW)
    new_rate = replace(RATE, rate=0.0750, as_of="2026-10-08")       # a new weekly rate
    fake = FakeDecide(Advice(status="unavailable", message="AI explanation unavailable"))
    advice, source, _ = get_advice(MAYA, new_rate, path=path, decide_fn=fake)
    assert fake.calls == 1
    assert source == "none" and advice.decision is None             # old answer NOT reused


def test_refresh_asks_again_and_falls_back_to_saved_if_gemini_is_down(path):
    get_advice(MAYA, RATE, path=path, decide_fn=FakeDecide(decided()), now=NOW)
    down = FakeDecide(Advice(status="unavailable", message="AI explanation unavailable",
                             reason="all models failed (last error: ServerError 503)"))
    advice, source, _ = get_advice(MAYA, RATE, refresh=True, path=path, decide_fn=down)
    assert down.calls == 1
    assert source == "saved" and advice.decision == "debt_first"
    assert "503" in advice.reason


def test_no_decision_is_never_saved(path):
    get_advice(MAYA, RATE, path=path,
               decide_fn=FakeDecide(Advice(status="no_decision", message="No decision reached")))
    assert load(path) == {}


def test_flagged_answer_is_shown_but_not_saved(path):
    advice, source, saved_at = get_advice(
        MAYA, RATE, path=path, now=NOW,
        decide_fn=FakeDecide(decided("Debt first: 21 months instead of 41.")))
    assert source == "live" and saved_at is None
    assert advice.mismatches == ["41"]               # shown, with its flag
    assert load(path) == {}                          # but not kept as the fallback


def test_number_check_is_rerun_on_saved_answers(path):
    get_advice(MAYA, RATE, path=path, decide_fn=FakeDecide(decided()), now=NOW)
    store = load(path)
    store["maya"]["explanation"] = "Debt first saves $12,000."   # file edited by hand
    save(store, path)
    advice, source, _ = get_advice(MAYA, RATE, path=path, decide_fn=FakeDecide(None))
    assert source == "saved" and advice.mismatches == ["$12,000"]


def test_fingerprint_changes_only_when_numbers_change():
    same = RenterTools(MAYA, RATE).fingerprint()
    assert RenterTools(MAYA, RATE).fingerprint() == same
    assert RenterTools(replace(MAYA, savings=9_001), RATE).fingerprint() != same


def test_peek_never_calls_gemini_and_only_returns_matching_answers(path):
    assert peek(MAYA, RATE, path=path) == (None, None)
    get_advice(MAYA, RATE, path=path, decide_fn=FakeDecide(decided()), now=NOW)
    advice, saved_at = peek(MAYA, RATE, path=path)
    assert advice.decision == "debt_first" and saved_at == "2026-10-02 14:30"
    assert peek(replace(MAYA, extra_per_month=700), RATE, path=path) == (None, None)


def test_missing_or_broken_file_is_treated_as_empty(tmp_path):
    assert load(tmp_path / "nope.json") == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert load(broken) == {}
