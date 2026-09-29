"""Tests for the model layer. No real Gemini calls: the model is replaced with fakes."""

import json

import pytest

from advisor import Advice, check_numbers, decide, fact_sheet, find_numbers
from finance import Assumptions
from rates import MortgageRate
from renters import analyze, load_renters

RATE = MortgageRate(0.0703, "2026-09-24", "Freddie Mac 30-year fixed average, via FRED", True)


@pytest.fixture(scope="module")
def maya_facts():
    maya = next(r for r in load_renters() if r.id == "maya")
    return fact_sheet(maya, analyze(maya, Assumptions(interest_rate=RATE.rate)), RATE)


# ---------- Fact sheet ----------

def test_fact_sheet_has_the_numbers_the_model_needs(maya_facts):
    assert maya_facts["Credit card interest rate (APR)"] == "26.99%"
    assert maya_facts["Total DTI today"] == "45.6%"
    assert maya_facts["Total DTI limit"] == "43.0%"
    assert maya_facts["Qualifies on DTI today"] == "no"
    assert maya_facts["Debt first: time until they can buy"] == "21 months"
    assert maya_facts["Deposit first: time until they can buy"] == "41 months"
    # Differences are calculated by code, so the model never has to subtract.
    assert maya_facts["Faster path"] == "debt first by 20 months"
    assert maya_facts["Interest difference"].startswith("debt first saves $")
    assert "7.03%" in maya_facts["Mortgage rate"] and "2026-09-24" in maya_facts["Mortgage rate"]


def test_fact_sheet_labels_contain_no_digits(maya_facts):
    """Numbers only live in values, so the model can't cite a number from a label."""
    assert not any(ch.isdigit() for label in maya_facts for ch in label)


# ---------- Number check ----------

def test_find_numbers_reads_units():
    found = {n.text: (n.value, n.unit) for n in find_numbers(
        "Pay $9,726 on the 26.99% card, buy in 21 months, 3 paths, 23.49 percentage points")}
    assert found == {"$9,726": (9726, "money"), "26.99%": (26.99, "pct"),
                     "21 months": (21, "months"), "3": (3, None),
                     "23.49 percentage points": (23.49, "pct")}


def test_good_explanation_passes(maya_facts):
    text = ("Maya should pay the card first: at 26.99% it costs far more than the 3.50% savings "
            "yield, her total DTI of 45.6% is over the 43.0% limit, and debt first lets her buy "
            "in 21 months instead of 41 months.")
    assert check_numbers(text, maya_facts) == []


def test_same_number_written_differently_passes(maya_facts):
    assert check_numbers("Her total DTI limit is 43%.", maya_facts) == []  # 43% == 43.0%


def test_invented_or_rounded_numbers_are_flagged(maya_facts):
    text = ("The card at 27% costs about $9,700 more, and she could buy in 18 months "
            "at a 5% rate.")
    assert check_numbers(text, maya_facts) == ["27%", "$9,700", "18 months", "5%"]


def test_right_number_wrong_unit_is_flagged(maya_facts):
    assert check_numbers("She can buy in 21%.", maya_facts) == ["21%"]  # 21 is months, not %


# ---------- Decision (fake model) ----------

class Busy(Exception):
    code = 503


class NotFound(Exception):
    code = 404


def reply(decision="debt_first", explanation="Debt first saves time: 21 months vs 41 months."):
    return json.dumps({"decision": decision, "explanation": explanation})


def test_decide_returns_decision_and_checked_numbers(maya_facts):
    advice = decide(maya_facts, client=object(), ask=lambda c, f, m: reply(), models=("m1",))
    assert advice == Advice("debt_first", "Debt first saves time: 21 months vs 41 months.",
                            [], "m1")


def test_decide_flags_bad_numbers(maya_facts):
    bad = reply(explanation="Debt first saves $12,000.")
    advice = decide(maya_facts, client=object(), ask=lambda c, f, m: bad, models=("m1",))
    assert advice.decision == "debt_first" and advice.mismatches == ["$12,000"]


def test_busy_model_is_retried_then_the_next_model_answers(maya_facts):
    calls = []

    def ask(client, facts, model):
        calls.append(model)
        if model == "busy":
            raise Busy()
        return reply("deposit_first", "Deposit first.")

    advice = decide(maya_facts, client=object(), ask=ask, models=("busy", "ok"),
                    sleep=lambda s: None)
    assert calls == ["busy", "busy", "ok"]      # retried once, then moved on
    assert advice.decision == "deposit_first" and advice.model == "ok"


def test_missing_model_is_skipped_without_retry(maya_facts):
    calls = []

    def ask(client, facts, model):
        calls.append(model)
        if model == "gone":
            raise NotFound()
        return reply()

    decide(maya_facts, client=object(), ask=ask, models=("gone", "ok"), sleep=lambda s: None)
    assert calls == ["gone", "ok"]


@pytest.mark.parametrize("bad_reply", [
    "not json", json.dumps({"decision": "maybe", "explanation": "x"}),
    json.dumps({"decision": "debt_first"}), json.dumps({"decision": "debt_first", "explanation": " "}),
])
def test_unusable_replies_never_crash(maya_facts, bad_reply):
    advice = decide(maya_facts, client=object(), ask=lambda c, f, m: bad_reply,
                    models=("m1",), sleep=lambda s: None)
    assert advice.decision is None and "unavailable" in advice.error


def test_all_models_down_gives_a_friendly_error(maya_facts):
    def ask(client, facts, model):
        raise Busy()
    advice = decide(maya_facts, client=object(), ask=ask, models=("a", "b"), sleep=lambda s: None)
    assert advice.decision is None
    assert advice.error == "AI explanation unavailable right now (Busy 503)."
