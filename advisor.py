"""The one judgment the model makes, as a bounded tool loop: debt first or deposit first.

The model starts with nothing but a renter id. Each step it asks for tools (agent_tools.py),
the code runs them and sends back the results, and it repeats until the model calls
submit_decision -- or until MAX_STEPS model calls have been made, in which case the answer
is "No decision reached". A decision is never guessed.

Every number in the final explanation must exactly match a number some tool returned.

Run all four renters live: python advisor.py
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

from agent_tools import DATA_TOOLS, STRATEGY_NAMES, TOOL_DECLARATIONS, RenterTools

# Tried in order; if one is overloaded or unavailable, the next one carries on.
# (gemini-2.5-flash is closed to new API keys.)
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite")
TEMPERATURE = 0.2           # low: we want steady judgments, not creative ones
DECISIONS = ("debt_first", "deposit_first")

MAX_STEPS = 6               # one step = one call to the model (it may request several tools)
REQUIRED_BEFORE_DECIDING = ("project_debt_first", "project_deposit_first")
RETRIES_PER_MODEL = 2       # attempts per model for retryable errors
RETRY_WAIT_SECONDS = 2
RETRY_CODES = {429, 500}    # rate-limited or server error: retry the same model
KEY_ERROR_CODES = {401, 403}  # key rejected: stop right away, retrying can't help

UNAVAILABLE = "AI explanation unavailable"

SYSTEM_PROMPT = f"""You are the explainer in an educational tool about renting vs. buying a home.
You are not a financial adviser, and the renters are fictional.

Your job: decide whether one renter should pay down debt first ("debt_first") or save for the
deposit first ("deposit_first"), then call submit_decision.

How to work:
- You start with no numbers. Get them with the tools: get_renter_summary, project_debt_first,
  project_deposit_first, and check_dti.
- You have at most {MAX_STEPS} turns, so request every tool you need at once (several tool
  calls in one turn is fine). Call submit_decision on its own, after you've read the results.
- A decision is only accepted after you've received results from both project_debt_first
  and project_deposit_first.

Rules for the explanation:
- Every number has already been calculated by the tools. Use only numbers from the tool
  results, written exactly as they appear (same digits, same decimals, same $ or %).
- Always write the unit with every number: "13 months", not "13"; "$1,317", not "1,317".
- Never calculate, add, subtract, round, estimate, or convert a number yourself. If you want a
  comparison the tools don't give as a number, describe it in words without a number.
- Weigh the interest rates, how each path changes DTI and timing, the renter's goal, and how
  steady their income is.
- 2 to 4 plain-English sentences, about the renter in the third person, citing the specific
  numbers that drove the decision. Generic advice is not enough on its own.
- If it's a close call, say so and name the trade-off."""


# ---------- Talking to Gemini ----------

@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ModelTurn:
    """What the model said in one step: tool calls and/or text."""
    calls: list
    text: str = ""
    raw: object = None   # the model's original message, sent back as-is in the history


def make_client():
    from google import genai
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise KeyError("GEMINI_API_KEY is missing")
    return genai.Client(api_key=key)


def _to_gemini(messages, model):
    """Turn our conversation into Gemini's format.

    A model's own earlier turns are sent back exactly as it wrote them (they carry hidden
    "thought signatures" Gemini requires). If a backup model took over mid-run, the earlier
    model's tool calls and results are retold as plain text, which any model accepts.
    """
    from google.genai import types

    def text(role, s):
        return types.Content(role=role, parts=[types.Part.from_text(text=s)])

    contents, retold = [], False
    for m in messages:
        if m["role"] == "user":
            contents.append(text("user", m["text"]))
        elif m["role"] == "model":
            retold = not (m.get("raw") is not None and m.get("model") == model)
            if not retold:
                contents.append(m["raw"])
                continue
            requested = "; ".join(f"{c.name}({json.dumps(c.args)})" for c in m["calls"])
            contents.append(text("model", " ".join(filter(None, [
                m.get("text"), f"I requested these tools: {requested}." if requested else ""]))
                or "(no reply)"))
        elif m["role"] == "tool":
            if retold:
                contents.append(text("user", "Tool results:\n" + json.dumps(
                    [{"tool": name, "result": result} for name, result in m["results"]], indent=1)))
            else:
                contents.append(types.Content(role="user", parts=[
                    types.Part.from_function_response(name=name, response=result)
                    for name, result in m["results"]]))
    return contents


def ask_gemini(client, messages, model):
    """One step: send the whole conversation, get back the model's next turn."""
    from google.genai import types
    response = client.models.generate_content(
        model=model, contents=_to_gemini(messages, model),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT, temperature=TEMPERATURE,
            tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
    if not response.candidates or response.candidates[0].content is None:
        raise ValueError("empty response")
    content = response.candidates[0].content
    calls = [ToolCall(fc.name, dict(fc.args or {})) for fc in (response.function_calls or [])]
    text = " ".join(p.text for p in (content.parts or []) if p.text and not p.thought).strip()
    return ModelTurn(calls, text, content)


# ---------- The result ----------

@dataclass
class Advice:
    status: str                       # "decided", "no_decision", or "unavailable"
    decision: str | None = None       # "debt_first" / "deposit_first", only when decided
    explanation: str = ""
    mismatches: list = field(default_factory=list)   # cited numbers no tool returned
    model: str | None = None          # model that made the final call
    message: str = ""                 # what to show when there is no decision
    reason: str | None = None         # technical detail behind the message
    steps: list = field(default_factory=list)        # printable step log
    tool_results: list = field(default_factory=list)  # every tool result from the run


def is_key_error(e):
    code = getattr(e, "code", None)
    return code in KEY_ERROR_CODES or (code == 400 and "api key" in str(e).lower())


class Unavailable(Exception):
    pass


def ask_with_fallback(ask, client, messages, models, start, sleep):
    """Ask the current model; retry 429/500, move to the next model on other errors,
    stop immediately on a rejected key. Returns (turn, index of the model that answered)."""
    last = "no models configured"
    for i in range(start, len(models)):
        for attempt in range(RETRIES_PER_MODEL):
            try:
                return ask(client, messages, models[i]), i
            except Exception as e:
                if is_key_error(e):
                    raise Unavailable(f"API key rejected ({getattr(e, 'code', '?')})")
                code = getattr(e, "code", None)
                last = f"{type(e).__name__}{f' {code}' if code else ''}"
                if code not in RETRY_CODES:
                    break                   # this model won't work; try the next one
                if attempt < RETRIES_PER_MODEL - 1:
                    sleep(RETRY_WAIT_SECONDS)
    raise Unavailable(f"all models failed (last error: {last})")


# ---------- The bounded loop ----------

def decide(renter, rate, client=None, ask=ask_gemini, models=GEMINI_MODELS,
           max_steps=MAX_STEPS, sleep=time.sleep, log=print, analysis=None):
    """Run the tool loop for one renter. Never raises and never guesses a decision."""
    tools = RenterTools(renter, rate, analysis)
    advice = Advice(status="no_decision")

    def note(line):
        advice.steps.append(line)
        log(line)

    try:
        client = client or make_client()
    except Exception as e:
        return _unavailable(advice, note, f"no Gemini client ({type(e).__name__})")

    messages = [{"role": "user", "text": f"Decide for renter_id '{renter.id}' ({renter.name})."}]
    model_index, received = 0, set()   # tools whose results the model has been sent
    for step in range(1, max_steps + 1):
        try:
            turn, model_index = ask_with_fallback(ask, client, messages, models, model_index, sleep)
        except Unavailable as e:
            return _unavailable(advice, note, str(e))
        messages.append({"role": "model", "calls": turn.calls, "text": turn.text,
                         "raw": turn.raw, "model": models[model_index]})

        if not turn.calls:
            note(f"Step {step} -> no tool chosen (model replied with text); reminded it to use the tools")
            messages.append({"role": "user", "text": "Use the tools, then call submit_decision."})
            continue

        results = []
        for n, call in enumerate(turn.calls):
            prefix = f"Step {step} -> " if n == 0 else " " * len(f"Step {step} ") + "-> "
            if call.name == "submit_decision":
                problem = _submit_problem(call, alone=len(turn.calls) == 1, received=received)
                if problem is None:
                    note(f"{prefix}submit_decision: {STRATEGY_NAMES[call.args['decision']]}")
                    advice.status, advice.model = "decided", models[model_index]
                    advice.decision = call.args["decision"]
                    advice.explanation = call.args["explanation"].strip()
                    advice.mismatches = check_numbers(advice.explanation, advice.tool_results)
                    return advice
                result, summary = {"error": problem}, f"rejected: {problem}"
            else:
                result, summary = tools.run(call.name, call.args)
                if "error" not in result:
                    received.add(call.name)
                    advice.tool_results.append(result)
            args = ", ".join(str(call.args[k]) for k in ("renter_id", "scenario") if k in call.args)
            note(f"{prefix}{call.name}({args}): {summary}")
            results.append((call.name, result))
        messages.append({"role": "tool", "results": results})

    advice.message = f"No decision reached after {max_steps} steps"
    note(advice.message)
    return advice


def _submit_problem(call, alone, received):
    """Why a submit_decision call can't be accepted, or None if it's fine.

    submit_decision must arrive in a turn of its own, so every tool in `received` was
    already answered in an earlier step: the model has seen those results.
    """
    if not alone:
        return "Call submit_decision on its own, after reading the other tool results."
    missing = [t for t in REQUIRED_BEFORE_DECIDING if t not in received]
    if missing:
        return (f"Not accepted yet: no results from {' or '.join(missing)}. Call "
                f"{'it' if len(missing) == 1 else 'them'}, then submit your decision.")
    if call.args.get("decision") not in DECISIONS:
        return f"decision must be one of {', '.join(DECISIONS)}."
    if not str(call.args.get("explanation", "")).strip():
        return "explanation is empty."
    return None


def _unavailable(advice, note, reason):
    advice.status, advice.message, advice.reason = "unavailable", UNAVAILABLE, reason
    note(f"{UNAVAILABLE} ({reason})")
    return advice


# ---------- Number check ----------

NUMBER = re.compile(
    r"(?<![\w.])(\$)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?"
    r"(?:\s*(%|percent\b|percentage points?\b|months?\b))?", re.I)


@dataclass(frozen=True)
class Cited:
    text: str
    value: float
    decimals: int
    unit: str | None   # "money", "pct", "months", or None


def find_numbers(text):
    found = []
    for m in NUMBER.finditer(text):
        dollar, whole, frac, suffix = m.groups()
        value = float(whole.replace(",", "") + (frac or ""))
        unit = ("money" if dollar else
                "pct" if suffix and suffix.lower().startswith("percent") or suffix == "%" else
                "months" if suffix else None)
        found.append(Cited(m.group(0).strip(), value, len(frac) - 1 if frac else 0, unit))
    return found


def _values(obj):
    """Every string value inside nested tool results."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _values(v)
    else:
        yield str(obj)


def check_numbers(explanation, sources):
    """Numbers in the explanation that don't match any number the tools returned.

    A cited number matches only if the units are the same and the values are exactly equal.
    "31%" matches "31.0%" (same number), but "27%" does not match "26.99%" and "$6,400"
    does not match "$6,364" -- rounding is math the model isn't allowed to do. A bare "21"
    does not match "21 months": if the fact has a unit, the citation must carry it too.
    """
    known = [n for value in _values(sources) for n in find_numbers(value)]
    mismatches = []
    for cited in find_numbers(explanation):
        ok = any(cited.unit == k.unit and abs(k.value - cited.value) < 1e-9 for k in known)
        if not ok:
            mismatches.append(cited.text)
    return mismatches


if __name__ == "__main__":
    from renters import DISCLAIMER
    print(DISCLAIMER + "\n")

    from rates import get_mortgage_rate
    from renters import load_renters

    rate = get_mortgage_rate()
    client = None
    try:
        client = make_client()
    except Exception:
        pass   # decide() reports "AI explanation unavailable"
    print(f"Mortgage rate {rate.rate:.2%} as of {rate.as_of} | models {', '.join(GEMINI_MODELS)} "
          f"| max {MAX_STEPS} steps\n")
    for r in load_renters():
        print(f"=== {r.name}")
        advice = decide(r, rate, client)
        if advice.status != "decided":
            print(f"    Result: {advice.message}\n")
            continue
        check = ("all numbers match the tool results" if not advice.mismatches
                 else "MISMATCH: " + ", ".join(advice.mismatches))
        print(f"    Decision: {STRATEGY_NAMES[advice.decision]}  (by {advice.model}, "
              f"{len(advice.steps)} step lines)\n    {advice.explanation}\n    Number check: {check}\n")
