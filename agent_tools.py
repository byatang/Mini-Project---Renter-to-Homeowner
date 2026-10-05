"""Tools the model can call during the decision loop.

Each tool wraps numbers the code has already calculated (renters.analyze() -> finance.py)
and returns them pre-formatted ("21 months", "$6,364", "45.6%"). The model never does
arithmetic: even the differences between the two paths are calculated here.
"""

import hashlib
import json

from finance import SAVINGS_APY, Assumptions
from renters import analyze

GOALS = {"buy_sooner": "Buy a home as soon as possible",
         "better_rate": "Buy on the strongest terms (lower DTI), even if it takes longer"}
INCOME_TYPES = {"salaried": "Salaried (steady paycheck)",
                "variable": "Variable (commission or freelance; the lender averages the last "
                            "two years, or uses the current year if income is falling)"}
STRATEGY_NAMES = {"debt_first": "debt first", "deposit_first": "deposit first"}
SCENARIOS = ("today", "debt_first", "deposit_first")
CHECKPOINT_EVERY = 3        # months between checkpoints (quarterly)
CHECKPOINT_EVERY_IF_NEVER = 12  # yearly when the renter can't buy within the projection


# ---------- Formatting ----------

def money(x):
    return f"${x:,.0f}"


def pct(x, places=2):
    return f"{x * 100:.{places}f}%"


def months(n):
    return "not within 10 years" if n is None else f"{n} month" + ("" if n == 1 else "s")


# ---------- Tool definitions shown to the model ----------

def _renter_param():
    return {"renter_id": {"type": "STRING", "description": "The renter's id, e.g. 'maya'."}}


TOOL_DECLARATIONS = [
    {"name": "get_renter_summary",
     "description": "The renter's profile, goal, income, debts with APRs, savings, target home, "
                    "monthly housing cost, cash needed to close, and DTI today vs. the limits.",
     "parameters": {"type": "OBJECT", "properties": _renter_param(), "required": ["renter_id"]}},
    {"name": "project_debt_first",
     "description": "Month-by-month outcome if extra cash goes to the highest-APR debt first, "
                    "then to savings: time until they can buy, interest, quarterly checkpoints, "
                    "and how it compares with deposit first.",
     "parameters": {"type": "OBJECT", "properties": _renter_param(), "required": ["renter_id"]}},
    {"name": "project_deposit_first",
     "description": "Month-by-month outcome if extra cash goes to the deposit first: time until "
                    "they can buy, interest, quarterly checkpoints, and how it compares with "
                    "debt first.",
     "parameters": {"type": "OBJECT", "properties": _renter_param(), "required": ["renter_id"]}},
    {"name": "check_dti",
     "description": "Housing-only and total DTI vs. the limits, today or at the point of "
                    "purchase under a scenario.",
     "parameters": {"type": "OBJECT",
                    "properties": {**_renter_param(),
                                   "scenario": {"type": "STRING", "enum": list(SCENARIOS)}},
                    "required": ["renter_id", "scenario"]}},
    {"name": "submit_decision",
     "description": "Submit the final decision. Call this alone, after reading the tool results.",
     "parameters": {"type": "OBJECT",
                    "properties": {
                        "decision": {"type": "STRING", "enum": ["debt_first", "deposit_first"]},
                        "explanation": {"type": "STRING",
                                        "description": "2 to 4 sentences citing numbers from "
                                                       "the tool results, exactly as written."}},
                    "required": ["decision", "explanation"]}},
]
DATA_TOOLS = ("get_renter_summary", "project_debt_first", "project_deposit_first", "check_dti")


# ---------- The tools for one renter ----------

class RenterTools:
    """Answers tool calls for one renter. Everything is calculated once, up front."""

    def __init__(self, renter, rate, analysis=None):
        self.renter, self.rate = renter, rate
        self.x = analysis or analyze(renter, Assumptions(interest_rate=rate.rate))
        self.paths = self.x["paths"]

    def run(self, name, args):
        """Run one tool call. Returns (result dict, one-line summary). Never raises."""
        handlers = {"get_renter_summary": self.get_renter_summary,
                    "project_debt_first": lambda: self.project("debt_first"),
                    "project_deposit_first": lambda: self.project("deposit_first"),
                    "check_dti": lambda: self.check_dti(args.get("scenario"))}
        if name not in handlers:
            return self._error(f"Unknown tool '{name}'. Available tools: "
                               f"{', '.join(DATA_TOOLS)}, submit_decision.")
        if args.get("renter_id") != self.renter.id:
            return self._error(f"Unknown renter_id '{args.get('renter_id')}'. "
                               f"This decision is for renter_id '{self.renter.id}'.")
        return handlers[name]()

    @staticmethod
    def _error(message):
        return {"error": message}, f"error: {message}"

    def get_renter_summary(self):
        r, x, lim = self.renter, self.x, self.x["limits"]
        # Raw annual income is deliberately left out: the model gets the income the lender
        # counts, and (for variable earners) the direction it's moving, in words only.
        f = {"Renter": r.name, "Story": r.story, "Goal": GOALS[r.goal],
             "Income type": INCOME_TYPES[r.income_type],
             "Monthly income the lender counts": money(x["qualifying_monthly_income"])}
        if r.prior_year_income:
            f["Income trend"] = ("rising this year" if r.annual_income > r.prior_year_income else
                                 "falling this year" if r.annual_income < r.prior_year_income else
                                 "flat")
        f["Savings today"] = money(r.savings)
        f["Extra cash available each month"] = money(r.extra_per_month)
        if not r.debts:
            f["Debts"] = "none"
        for d in r.debts:
            f[f"{d.name} balance"] = money(d.balance)
            f[f"{d.name} interest rate (APR)"] = pct(d.apr)
            f[f"{d.name} monthly payment"] = money(d.monthly_payment)
        f["Savings account yield (what the deposit fund earns)"] = pct(SAVINGS_APY)
        if r.debts:   # no debts -> no APR to compare, so no gap fact
            top = max(r.debts, key=lambda d: d.apr)
            f[f"Gap between {top.name} APR and savings yield"] = (
                f"{(top.apr - SAVINGS_APY) * 100:.2f} percentage points")
        f["Target home price"] = money(r.target_price)
        f["Loan program and down payment"] = f"{r.program}, {pct(r.down_pct, 1)} down"
        f["Mortgage rate"] = f"{pct(self.rate.rate)} ({self.rate.source}, as of {self.rate.as_of})"
        f["Monthly housing cost"] = money(x["housing_cost"]["total"])
        f["Cash needed to close (deposit + closing costs)"] = money(x["cash_to_close"])
        f["Housing-only DTI today"] = pct(x["front_dti_today"], 1)
        f["Housing-only DTI limit"] = pct(lim.front, 1)
        f["Total DTI today"] = pct(x["back_dti_today"], 1)
        f["Total DTI limit"] = pct(lim.back, 1)
        f["Qualifies on DTI today"] = self._yes(x["front_dti_today"], x["back_dti_today"])
        summary = (f"{r.name}, {r.income_type} income, lender counts "
                   f"{f['Monthly income the lender counts']}/mo; total DTI "
                   f"{f['Total DTI today']} vs {f['Total DTI limit']} limit")
        return f, summary

    def project(self, strategy):
        p = self.paths[strategy]
        other_key = next(s for s in STRATEGY_NAMES if s != strategy)
        other = self.paths[other_key]
        name, other_name = STRATEGY_NAMES[strategy], STRATEGY_NAMES[other_key]
        f = {"Strategy": name,
             "How extra cash is used": ("to the highest-APR debt until it is paid off, then to "
                                        "savings" if strategy == "debt_first" else
                                        "to savings for the deposit"),
             "Time until they can buy": months(p.months_to_buy),
             "Savings at purchase": money(p.savings_at_purchase),
             "Debt still owed at purchase": money(p.debt_left_at_purchase),
             "Total DTI at purchase": pct(p.back_dti_at_purchase, 1),
             "Total interest on today's debts": money(p.total_debt_interest),
             "Checkpoints": self._checkpoints(p)}
        if p.months_to_buy is not None and other.months_to_buy is not None:
            gap = other.months_to_buy - p.months_to_buy
            f[f"Timing compared with {other_name}"] = (
                "same timing" if gap == 0 else
                f"{name} is faster by {months(gap)}" if gap > 0 else
                f"{name} is slower by {months(-gap)}")
        saved = other.total_debt_interest - p.total_debt_interest
        f[f"Interest compared with {other_name}"] = (
            f"{name} saves {money(saved)}" if saved >= 0 else
            f"{name} costs {money(-saved)} more")
        interest = f["Total interest on today's debts"]
        summary = (f"buys in {f['Time until they can buy']}; {interest} interest; "
                   f"DTI at purchase {f['Total DTI at purchase']}")
        return f, summary

    def _checkpoints(self, p):
        step = CHECKPOINT_EVERY if p.months_to_buy is not None else CHECKPOINT_EVERY_IF_NEVER
        last = p.months_to_buy if p.months_to_buy is not None else len(p.monthly) - 1
        picks = [m for m in range(step, last, step)] + [last]
        return [f"after {months(m)}: savings {money(p.monthly[m]['savings'])}, "
                f"debt owed {money(p.monthly[m]['debt_balance'])}"
                + (" (can buy)" if m == p.months_to_buy else "") for m in picks]

    def check_dti(self, scenario):
        if scenario not in SCENARIOS:
            return self._error(f"Unknown scenario '{scenario}'. Use one of: {', '.join(SCENARIOS)}.")
        x, lim = self.x, self.x["limits"]
        front = x["front_dti_today"]   # same housing cost and income on every path
        if scenario == "today":
            back, when = x["back_dti_today"], "today"
        else:
            p = self.paths[scenario]
            back = p.back_dti_at_purchase
            when = (f"at purchase with {STRATEGY_NAMES[scenario]}" if p.months_to_buy is not None
                    else f"after 10 years of {STRATEGY_NAMES[scenario]} (still can't buy)")
        f = {"When": when,
             "Housing-only DTI": pct(front, 1), "Housing-only DTI limit": pct(lim.front, 1),
             "Total DTI": pct(back, 1), "Total DTI limit": pct(lim.back, 1),
             "Within limits": self._yes(front, back)}
        verdict = "within limits" if f["Within limits"] == "yes" else "over the limit"
        return f, f"{scenario}: total DTI {f['Total DTI']} vs {f['Total DTI limit']} -> {verdict}"

    def fingerprint(self):
        """Short code for every number the tools could return for this renter.

        Two runs have the same fingerprint only if every tool result would be identical,
        so a saved answer is reused only when the renter's numbers haven't changed.
        """
        calls = [(t, {"renter_id": self.renter.id}) for t in DATA_TOOLS if t != "check_dti"]
        calls += [("check_dti", {"renter_id": self.renter.id, "scenario": s}) for s in SCENARIOS]
        everything = [self.run(name, args)[0] for name, args in calls]
        return hashlib.sha256(json.dumps(everything, sort_keys=True).encode()).hexdigest()[:16]

    def _yes(self, front, back):
        lim = self.x["limits"]
        return "yes" if front <= lim.front and back <= lim.back else "no"


assert {d["name"] for d in TOOL_DECLARATIONS} == {*DATA_TOOLS, "submit_decision"}
