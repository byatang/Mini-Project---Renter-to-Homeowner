"""Tests for the bounded tool loop. No real Gemini calls: a scripted fake model plays each turn."""

from dataclasses import replace

import pytest

from advisor import (
    MAX_STEPS, UNAVAILABLE, ModelTurn, ToolCall, check_numbers, decide, find_numbers,
)
from agent_tools import RenterTools
from rates import FALLBACK
from renters import load_renters

RATE = replace(FALLBACK, rate=0.0703, as_of="2026-09-24", source="test rate", is_live=True)
MAYA = next(r for r in load_renters() if r.id == "maya")

GOOD_EXPLANATION = (
    "Maya should pay down debt first: her total DTI of 45.6% is over the 43.0% limit and her "
    "card charges 26.99%. Debt first lets her buy in 21 months instead of 41 months and saves "
    "$9,726.")


def call(name, **args):
    return ToolCall(name, args)


def submit(decision="debt_first", explanation=GOOD_EXPLANATION):
    return ModelTurn([call("submit_decision", decision=decision, explanation=explanation)])


NORMAL_RUN = [
    ModelTurn([call("get_renter_summary", renter_id="maya")]),
    ModelTurn([call("project_debt_first", renter_id="maya"),
               call("project_deposit_first", renter_id="maya")]),
    submit(),
]


class FakeModel:
    """Plays scripted turns in order (repeating the last one) and records every call."""

    def __init__(self, turns, errors=None):
        self.turns, self.errors = list(turns), errors or {}
        self.calls = []          # (model name, copy of the conversation it was sent)
        self.answered = 0        # successful turns so far

    def __call__(self, client, messages, model):
        self.calls.append((model, list(messages)))
        queue = self.errors.get(model)
        if queue:
            raise queue.pop(0)
        turn = self.turns[min(self.answered, len(self.turns) - 1)]
        self.answered += 1
        return turn


class ApiError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{code} {message}")
        self.code = code


def run(fake, models=("m1",), **kwargs):
    lines = []
    advice = decide(MAYA, RATE, client=object(), ask=fake, models=models,
                    sleep=lambda s: None, log=lines.append, **kwargs)
    return advice, lines


# ---------- The three required behaviors ----------

def test_normal_renter_reaches_a_decision_in_under_max_steps():
    fake = FakeModel(NORMAL_RUN)
    advice, lines = run(fake)
    assert advice.status == "decided" and advice.decision == "debt_first"
    assert len(fake.calls) == 3 < MAX_STEPS
    assert advice.mismatches == []                 # every cited number came from a tool
    assert lines[0].startswith("Step 1 -> get_renter_summary(maya): Maya")
    assert lines[1].startswith("Step 2 -> project_debt_first(maya): buys in 21 months")
    assert "project_deposit_first(maya): buys in 41 months" in lines[2]
    assert lines[3] == "Step 3 -> submit_decision: debt first"


def test_model_that_never_finishes_stops_at_max_steps():
    fake = FakeModel([ModelTurn([call("get_renter_summary", renter_id="maya")])])
    advice, lines = run(fake)
    assert len(fake.calls) == MAX_STEPS
    assert advice.status == "no_decision" and advice.decision is None
    assert advice.message == f"No decision reached after {MAX_STEPS} steps"
    assert lines[-1] == advice.message


def test_model_that_only_chats_also_stops_at_max_steps():
    fake = FakeModel([ModelTurn([], text="Let me think about it...")])
    advice, _ = run(fake)
    assert len(fake.calls) == MAX_STEPS and advice.decision is None


def test_unknown_tool_is_handled_without_crashing():
    fake = FakeModel([ModelTurn([call("fly_to_moon", renter_id="maya")])] + NORMAL_RUN)
    advice, lines = run(fake, max_steps=5)
    assert "Step 1 -> fly_to_moon(maya): error: Unknown tool 'fly_to_moon'" in lines[0]
    # The error went back to the model as a tool result, and the loop carried on.
    _, second_conversation = fake.calls[1]
    assert second_conversation[-1]["results"][0][1]["error"].startswith("Unknown tool")
    assert advice.status == "decided"


# ---------- submit_decision is checked ----------

@pytest.mark.parametrize("turns, expected", [
    ([submit()], "Get the numbers from the tools"),                       # no data yet
    ([NORMAL_RUN[0], ModelTurn([call("project_debt_first", renter_id="maya"),
                                submit().calls[0]])], "on its own"),        # bundled with tools
    ([NORMAL_RUN[0], submit(decision="maybe")], "decision must be one of"),
    ([NORMAL_RUN[0], submit(explanation="  ")], "explanation is empty"),
])
def test_bad_submissions_are_rejected_not_accepted(turns, expected):
    advice, lines = run(FakeModel(turns + [ModelTurn([], text="...")]))
    assert advice.decision is None
    assert any("rejected" in line and expected in line for line in lines)


# ---------- Number check uses every tool result from the run ----------

def test_numbers_not_returned_by_any_tool_are_flagged():
    bad = submit(explanation="Debt first saves $12,000 and takes 21 months.")
    advice, _ = run(FakeModel(NORMAL_RUN[:2] + [bad]))
    assert advice.mismatches == ["$12,000"]


def test_number_from_a_tool_that_was_never_called_is_flagged():
    # The model only asked for the debt-first projection, so "41 months" (deposit first)
    # was never in front of it.
    turns = [ModelTurn([call("project_debt_first", renter_id="maya")]),
             submit(explanation="Debt first takes 21 months, not 41 months.")]
    advice, _ = run(FakeModel(turns))
    assert advice.mismatches == ["41 months"]


def test_find_numbers_reads_units():
    found = {n.text: (n.value, n.unit) for n in find_numbers(
        "Pay $9,726 on the 26.99% card, buy in 21 months, 3 paths, 23.49 percentage points")}
    assert found == {"$9,726": (9726, "money"), "26.99%": (26.99, "pct"),
                     "21 months": (21, "months"), "3": (3, None),
                     "23.49 percentage points": (23.49, "pct")}


def test_exact_match_rules():
    sources = [{"limit": "43.0%", "apr": "26.99%", "time": "21 months"}]
    assert check_numbers("The limit is 43%.", sources) == []          # same number
    assert check_numbers("The card is 27%.", sources) == ["27%"]       # rounded: flagged
    assert check_numbers("She buys in 21%.", sources) == ["21%"]       # wrong unit: flagged


# ---------- Retries, fallback, and key errors ----------

def test_429_and_500_are_retried_then_the_next_model_continues():
    fake = FakeModel(NORMAL_RUN, errors={"busy": [ApiError(429), ApiError(500)]})
    advice, _ = run(fake, models=("busy", "ok"))
    assert [m for m, _ in fake.calls[:3]] == ["busy", "busy", "ok"]
    assert advice.status == "decided" and advice.model == "ok"


def test_other_server_errors_skip_to_the_next_model_without_retry():
    fake = FakeModel(NORMAL_RUN, errors={"overloaded": [ApiError(503)]})
    advice, _ = run(fake, models=("overloaded", "ok"))
    assert [m for m, _ in fake.calls[:2]] == ["overloaded", "ok"]
    assert advice.status == "decided"


def test_failed_attempts_do_not_use_up_steps():
    fake = FakeModel(NORMAL_RUN, errors={"flaky": [ApiError(429)]})
    advice, lines = run(fake, models=("flaky",))
    assert advice.status == "decided" and len(fake.calls) == 4   # 1 failed try + 3 real steps
    assert lines[-1].startswith("Step 3 ->")                      # still only 3 steps counted


@pytest.mark.parametrize("error", [ApiError(401), ApiError(403),
                                   ApiError(400, "API key not valid. Please pass a valid API key.")])
def test_key_errors_stop_right_away(error):
    fake = FakeModel(NORMAL_RUN, errors={"m1": [error]})
    advice, lines = run(fake, models=("m1", "m2"))
    assert len(fake.calls) == 1                     # no retry, no other model
    assert advice.status == "unavailable" and advice.decision is None
    assert advice.message == UNAVAILABLE
    assert lines[-1].startswith(UNAVAILABLE)


def test_all_models_failing_is_unavailable_not_a_crash():
    fake = FakeModel(NORMAL_RUN, errors={"a": [ApiError(503)], "b": [ApiError(429), ApiError(429)]})
    advice, _ = run(fake, models=("a", "b"))
    assert advice.status == "unavailable" and advice.message == UNAVAILABLE
    assert "429" in advice.reason


# ---------- History sent to Gemini when a backup model takes over ----------

def history(raw):
    return [
        {"role": "user", "text": "Decide for renter_id 'maya' (Maya)."},
        {"role": "model", "calls": [call("get_renter_summary", renter_id="maya")], "text": "",
         "raw": raw, "model": "model-a"},
        {"role": "tool", "results": [("get_renter_summary", {"Total DTI today": "46.1%"})]},
    ]


def test_same_model_gets_its_own_turn_back_untouched():
    from google.genai import types
    from advisor import _to_gemini
    raw = types.Content(role="model", parts=[
        types.Part.from_function_call(name="get_renter_summary", args={"renter_id": "maya"})])
    contents = _to_gemini(history(raw), "model-a")
    assert contents[1] is raw                                   # sealed original, as-is
    assert contents[2].parts[0].function_response.name == "get_renter_summary"


def test_backup_model_gets_earlier_steps_retold_as_plain_text():
    from google.genai import types
    from advisor import _to_gemini
    raw = types.Content(role="model", parts=[
        types.Part.from_function_call(name="get_renter_summary", args={"renter_id": "maya"})])
    contents = _to_gemini(history(raw), "model-b")
    parts = [p for c in contents for p in c.parts]
    assert not any(p.function_call or p.function_response for p in parts)   # nothing sealed
    assert "I requested these tools: get_renter_summary" in contents[1].parts[0].text
    assert "46.1%" in contents[2].parts[0].text                 # same numbers, as text


# ---------- The tools themselves ----------

@pytest.fixture(scope="module")
def tools():
    return RenterTools(MAYA, RATE)


def test_tools_return_the_code_calculated_numbers(tools):
    summary, _ = tools.run("get_renter_summary", {"renter_id": "maya"})
    assert summary["Total DTI today"] == "45.6%" and summary["Total DTI limit"] == "43.0%"
    debt, _ = tools.run("project_debt_first", {"renter_id": "maya"})
    p = tools.paths["debt_first"]
    assert debt["Time until they can buy"] == f"{p.months_to_buy} months" == "21 months"
    assert debt["Timing compared with deposit first"] == "debt first is faster by 20 months"
    deposit, _ = tools.run("project_deposit_first", {"renter_id": "maya"})
    assert deposit["Timing compared with debt first"] == "deposit first is slower by 20 months"


def test_checkpoints_are_quarterly_and_end_at_purchase(tools):
    result, _ = tools.run("project_debt_first", {"renter_id": "maya"})
    points = result["Checkpoints"]
    assert [p.split(":")[0] for p in points] == [f"after {m} months" for m in (3, 6, 9, 12, 15, 18, 21)]
    assert points[-1].endswith("(can buy)")


def test_check_dti_scenarios(tools):
    today, line = tools.run("check_dti", {"renter_id": "maya", "scenario": "today"})
    assert today["Within limits"] == "no" and "over the limit" in line
    later, _ = tools.run("check_dti", {"renter_id": "maya", "scenario": "debt_first"})
    assert later["Within limits"] == "yes"


@pytest.mark.parametrize("name, args, expected", [
    ("check_dti", {"renter_id": "maya", "scenario": "tomorrow"}, "Unknown scenario"),
    ("get_renter_summary", {"renter_id": "jordan"}, "Unknown renter_id"),
    ("get_renter_summary", {}, "Unknown renter_id"),
    ("fly_to_moon", {"renter_id": "maya"}, "Unknown tool"),
])
def test_bad_tool_calls_return_errors(tools, name, args, expected):
    result, _ = tools.run(name, args)
    assert result["error"].startswith(expected)


def test_tool_labels_contain_no_digits(tools):
    """Numbers only live in values, so the model can't cite a number from a label."""
    for name in ("get_renter_summary", "project_debt_first", "project_deposit_first"):
        result, _ = tools.run(name, {"renter_id": "maya"})
        assert not any(ch.isdigit() for label in result for ch in label)
