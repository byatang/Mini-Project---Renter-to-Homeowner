"""The one judgment the model makes: debt first or deposit first.

1. fact_sheet()   code turns its own calculations into labeled, pre-formatted numbers
2. decide()       Gemini sees only that fact sheet and returns a decision + explanation
3. check_numbers() every number in the explanation must match a number on the fact sheet

Run all four renters live: python advisor.py
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

from finance import SAVINGS_APY

# Tried in order; if one is overloaded or unavailable, the next one answers.
# (gemini-2.5-flash is closed to new API keys.)
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite")
TEMPERATURE = 0.2          # low: we want steady judgments, not creative ones
DECISIONS = ("debt_first", "deposit_first")

GOALS = {"buy_sooner": "Buy a home as soon as possible",
         "better_rate": "Buy on the strongest terms (lower DTI), even if it takes longer"}
INCOME_TYPES = {"salaried": "Salaried (steady paycheck)",
                "variable": "Variable (commission or freelance; the lender averages the last "
                            "two years, or uses the current year if income is falling)"}


# ---------- 1. Fact sheet: every number the model may use ----------

def money(x):
    return f"${x:,.0f}"


def pct(x, places=2):
    return f"{x * 100:.{places}f}%"


def months(n):
    return "not within 10 years" if n is None else f"{n} month" + ("" if n == 1 else "s")


def fact_sheet(renter, analysis, rate):
    """Ordered {label: value} of everything the model is allowed to cite."""
    lim = analysis["limits"]
    debt, deposit = analysis["paths"]["debt_first"], analysis["paths"]["deposit_first"]
    f = {
        "Renter": renter.name,
        "Goal": GOALS[renter.goal],
        "Income type": INCOME_TYPES[renter.income_type],
        "Annual income this year": money(renter.annual_income),
    }
    if renter.prior_year_income:
        f["Annual income last year"] = money(renter.prior_year_income)
    f["Monthly income the lender counts"] = money(analysis["qualifying_monthly_income"])
    f["Savings today"] = money(renter.savings)
    f["Extra cash available each month"] = money(renter.extra_per_month)

    for d in renter.debts:
        f[f"{d.name} balance"] = money(d.balance)
        f[f"{d.name} interest rate (APR)"] = pct(d.apr)
        f[f"{d.name} monthly payment"] = money(d.monthly_payment)
    top = max(renter.debts, key=lambda d: d.apr)
    f["Savings account yield (what the deposit fund earns)"] = pct(SAVINGS_APY)
    f[f"Gap between {top.name} APR and savings yield"] = (
        f"{(top.apr - SAVINGS_APY) * 100:.2f} percentage points")

    f["Target home price"] = money(renter.target_price)
    f["Loan program and down payment"] = f"{renter.program}, {pct(renter.down_pct, 1)} down"
    f["Mortgage rate"] = f"{pct(rate.rate)} ({rate.source}, as of {rate.as_of})"
    f["Monthly housing cost"] = money(analysis["housing_cost"]["total"])
    f["Cash needed to close (deposit + closing costs)"] = money(analysis["cash_to_close"])
    f["Housing-only DTI today"] = pct(analysis["front_dti_today"], 1)
    f["Housing-only DTI limit"] = pct(lim.front, 1)
    f["Total DTI today"] = pct(analysis["back_dti_today"], 1)
    f["Total DTI limit"] = pct(lim.back, 1)
    f["Qualifies on DTI today"] = ("yes" if analysis["front_dti_today"] <= lim.front
                                  and analysis["back_dti_today"] <= lim.back else "no")

    for label, p in (("Debt first", debt), ("Deposit first", deposit)):
        f[f"{label}: time until they can buy"] = months(p.months_to_buy)
        f[f"{label}: total interest on today's debts"] = money(p.total_debt_interest)
        f[f"{label}: total DTI at purchase"] = pct(p.back_dti_at_purchase, 1)
        f[f"{label}: debt still owed at purchase"] = money(p.debt_left_at_purchase)

    if debt.months_to_buy is not None and deposit.months_to_buy is not None:
        gap = debt.months_to_buy - deposit.months_to_buy
        f["Faster path"] = ("same timing" if gap == 0 else
                            f"{'deposit first' if gap > 0 else 'debt first'} by {months(abs(gap))}")
    saved = deposit.total_debt_interest - debt.total_debt_interest
    f["Interest difference"] = (f"debt first saves {money(saved)}" if saved >= 0 else
                                f"deposit first saves {money(-saved)}")
    return f


# ---------- 2. The decision ----------

SYSTEM_PROMPT = """You are the explainer in an educational tool about renting vs. buying a home.
You are not a financial adviser, and the renters are fictional.

For the renter in the fact sheet, make exactly one judgment: should they pay down debt first
("debt_first") or save for the deposit first ("deposit_first")?

Rules:
- Every number has already been calculated. Use only numbers that appear in the fact sheet,
  written exactly as they appear there (same digits, same decimals, same $ or %).
- Never calculate, add, subtract, round, estimate, or convert a number yourself. If you want a
  comparison the fact sheet doesn't give as a number, describe it in words without a number.
- Weigh the interest rates, how each path changes DTI and timing, the renter's goal, and how
  steady their income is.
- Explain in 2 to 4 plain-English sentences, about the renter in the third person. Cite the
  specific numbers that drove the decision. Generic advice like "pay down high-interest debt
  first" is not enough on its own.
- If it's a close call, say so and name the trade-off."""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "decision": {"type": "STRING", "enum": list(DECISIONS)},
        "explanation": {"type": "STRING"},
    },
    "required": ["decision", "explanation"],
}


def make_client():
    from google import genai
    load_dotenv()
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())


def ask_gemini(client, facts, model):
    from google.genai import types
    response = client.models.generate_content(
        model=model,
        contents="Fact sheet:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items()),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT, temperature=TEMPERATURE,
            response_mime_type="application/json", response_schema=RESPONSE_SCHEMA,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)),
    )
    return response.text


@dataclass
class Advice:
    decision: str | None          # "debt_first", "deposit_first", or None if unavailable
    explanation: str
    mismatches: list = field(default_factory=list)   # numbers cited that aren't on the sheet
    model: str | None = None      # which model answered
    error: str | None = None


RETRIES_PER_MODEL = 2     # attempts per model when Google is temporarily busy
RETRY_WAIT_SECONDS = 2
TRANSIENT_CODES = {429, 500, 502, 503, 504}   # rate-limited or overloaded: worth retrying


def parse_reply(text):
    reply = json.loads(text)
    decision, explanation = reply["decision"], reply["explanation"].strip()
    if decision not in DECISIONS or not explanation:
        raise ValueError(f"unusable reply: decision={decision!r}")
    return decision, explanation


def decide(facts, client=None, ask=ask_gemini, models=GEMINI_MODELS, sleep=time.sleep):
    """Ask the model for its one decision, then check its numbers. Never raises.

    Tries each model in turn (with a short retry for temporary errors) and returns
    the first usable answer.
    """
    last_error = "no models configured"
    try:
        client = client or make_client()
    except Exception as e:
        return Advice(None, "", error=f"AI explanation unavailable ({type(e).__name__}).")
    for model in models:
        for attempt in range(RETRIES_PER_MODEL):
            try:
                decision, explanation = parse_reply(ask(client, facts, model))
                return Advice(decision, explanation, check_numbers(explanation, facts), model)
            except Exception as e:
                code = getattr(e, "code", None)
                last_error = f"{type(e).__name__}{f' {code}' if code else ''}"
                if code not in TRANSIENT_CODES:
                    break                        # this model won't work; try the next one
                if attempt < RETRIES_PER_MODEL - 1:
                    sleep(RETRY_WAIT_SECONDS)
    return Advice(None, "", error=f"AI explanation unavailable right now ({last_error}).")


# ---------- 3. Number check ----------

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


def check_numbers(explanation, facts):
    """Numbers in the explanation that don't match any number on the fact sheet.

    A cited number matches a fact only if the units agree and the values are exactly equal.
    "31%" matches "31.0%" (same number), but "27%" does not match "26.99%" and "$6,400"
    does not match "$6,364" -- rounding is math the model isn't allowed to do.
    """
    known = [n for value in facts.values() for n in find_numbers(str(value))]
    mismatches = []
    for cited in find_numbers(explanation):
        ok = any((cited.unit is None or cited.unit == k.unit)
                 and abs(k.value - cited.value) < 1e-9 for k in known)
        if not ok:
            mismatches.append(cited.text)
    return mismatches


if __name__ == "__main__":
    from finance import Assumptions
    from rates import get_mortgage_rate
    from renters import analyze, load_renters

    rate = get_mortgage_rate()
    client = make_client()
    print(f"Mortgage rate {rate.rate:.2%} as of {rate.as_of} | models {', '.join(GEMINI_MODELS)}\n")
    for r in load_renters():
        facts = fact_sheet(r, analyze(r, Assumptions(interest_rate=rate.rate)), rate)
        advice = decide(facts, client)
        if advice.error:
            print(f"=== {r.name}: {advice.error}\n")
            continue
        check = ("all numbers match the fact sheet" if not advice.mismatches
                 else "MISMATCH: " + ", ".join(advice.mismatches))
        print(f"=== {r.name}: {advice.decision}  (answered by {advice.model})\n"
              f"    {advice.explanation}\n    Number check: {check}\n")
