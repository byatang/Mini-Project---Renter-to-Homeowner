"""The four fictional renters and the numbers the code calculates for each one.

Renter details live in data/renters.json, not in this file.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from finance import (
    DEFAULT_LEVEL, PROGRAMS, STRATEGIES, Assumptions, Debt, cash_to_close, dti,
    monthly_housing_cost, project_path, qualifying_monthly_income,
)

RENTERS_FILE = Path(__file__).parent / "data" / "renters.json"

# Shown at the start of every run, word for word.
DISCLAIMER = "Educational tool, not personalized financial advice. Rates shown are not guaranteed."


@dataclass
class Renter:
    id: str
    name: str
    story: str
    income_type: str           # "salaried" or "variable"
    annual_income: float
    prior_year_income: float | None
    rent: float
    savings: float
    extra_per_month: float     # cash left each month after rent, bills, and minimum payments
    goal: str                  # "buy_sooner" or "better_rate"
    county: str
    target_price: float
    program: str               # key in finance.PROGRAMS
    down_pct: float
    debts: list


def load_renters(path=RENTERS_FILE):
    with open(path) as f:
        rows = json.load(f)
    renters = [Renter(**{**r, "debts": [Debt(**d) for d in r["debts"]]}) for r in rows]
    for r in renters:
        validate(r)
    return renters


def validate(renter):
    """Catch bad renter data when it's loaded, with a message that names the renter."""
    income = qualifying_monthly_income(renter.annual_income, renter.income_type,
                                       renter.prior_year_income)
    if renter.annual_income <= 0 or income <= 0:
        raise ValueError(f"Renter '{renter.id}': income must be greater than zero "
                         f"(annual_income={renter.annual_income}, "
                         f"prior_year_income={renter.prior_year_income}).")
    # The projection tracks balances by debt name, so two debts with one name would merge.
    names = [d.name for d in renter.debts]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"Renter '{renter.id}': duplicate debt names {duplicates}. "
                         f"Give each debt a unique name, e.g. 'Credit card 1', 'Credit card 2'.")


def analyze(renter, a=Assumptions(), level=DEFAULT_LEVEL):
    """Everything the code calculates for one renter: today's picture plus both paths."""
    program = PROGRAMS[renter.program]
    income = qualifying_monthly_income(renter.annual_income, renter.income_type,
                                       renter.prior_year_income)
    housing = monthly_housing_cost(renter.target_price, renter.down_pct, program, a)
    front, back = dti(income, housing["total"], renter.debts)
    paths = {s: project_path(s, income, renter.debts, renter.savings, renter.extra_per_month,
                             renter.target_price, renter.down_pct, program, a, level)
             for s in STRATEGIES}
    return {
        "qualifying_monthly_income": income,
        "housing_cost": housing,
        "cash_to_close": cash_to_close(renter.target_price, renter.down_pct, a),
        "front_dti_today": front,
        "back_dti_today": back,
        "limits": program.limits(level),
        "paths": paths,
    }
