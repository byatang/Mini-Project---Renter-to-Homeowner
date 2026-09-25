"""Home-buying math for the Renter-to-Homeowner Roadmap.

Plain formulas, no AI. Every number the app or the agent shows comes from here.
All money is in dollars, all rates are decimals (6.5% -> 0.065), and all
payments and incomes are monthly unless the name says otherwise.
"""

import math
from dataclasses import dataclass, field, replace


@dataclass
class Debt:
    """A debt the user types in (we never pull a credit report)."""
    name: str
    monthly_payment: float
    balance: float


@dataclass
class LoanProgram:
    """Lender rules for one kind of mortgage."""
    name: str
    min_down_pct: float        # smallest down payment allowed
    max_front_dti: float       # housing cost / gross income
    max_back_dti: float        # (housing cost + debts) / gross income
    mortgage_insurance: float  # yearly rate, as a share of the loan
    mi_always: bool            # FHA charges it at any down payment; conventional only under 20%


# Classic underwriting guidelines. Automated underwriting can approve higher
# DTIs, so these are "comfortable" limits, not hard maximums.
PROGRAMS = {
    "Conventional": LoanProgram("Conventional", 0.03, 0.28, 0.36, 0.006, mi_always=False),
    "FHA": LoanProgram("FHA", 0.035, 0.31, 0.43, 0.0055, mi_always=True),
}


@dataclass
class Assumptions:
    """Market assumptions. Defaults are rough DFW figures; the user can change any of them."""
    interest_rate: float = 0.065
    loan_years: int = 30
    property_tax_rate: float = 0.022   # Texas has no income tax, so property tax runs high
    insurance_rate: float = 0.010      # homeowners insurance per year, as a share of price
    hoa_monthly: float = 0.0
    closing_cost_pct: float = 0.03     # buyer's closing costs, as a share of price


# ---------- Monthly housing cost ----------

def monthly_principal_interest(loan_amount, annual_rate, years):
    """Standard fixed-rate mortgage payment."""
    n = years * 12
    if annual_rate == 0:
        return loan_amount / n
    r = annual_rate / 12
    return loan_amount * r * (1 + r) ** n / ((1 + r) ** n - 1)


def _has_mortgage_insurance(down_pct, program):
    return program.mi_always or down_pct < 0.20


def monthly_housing_cost(price, down_pct, program, a=Assumptions()):
    """Full monthly payment (PITI + mortgage insurance + HOA), itemized."""
    loan = price * (1 - down_pct)
    parts = {
        "principal_interest": monthly_principal_interest(loan, a.interest_rate, a.loan_years),
        "property_tax": price * a.property_tax_rate / 12,
        "insurance": price * a.insurance_rate / 12,
        "mortgage_insurance": (loan * program.mortgage_insurance / 12
                               if _has_mortgage_insurance(down_pct, program) else 0.0),
        "hoa": a.hoa_monthly,
    }
    parts["total"] = sum(parts.values())
    return parts


# ---------- Debt-to-income ----------

def total_debt_payments(debts):
    return sum(d.monthly_payment for d in debts)


def dti(gross_monthly_income, housing_cost, debts):
    """Returns (front-end DTI, back-end DTI)."""
    front = housing_cost / gross_monthly_income
    back = (housing_cost + total_debt_payments(debts)) / gross_monthly_income
    return front, back


# Slack for floating-point rounding, so a house priced exactly at the limit still qualifies.
TOLERANCE = 1e-9


@dataclass
class PayoffPlan:
    qualifies_now: bool
    fixable_by_paying_debt: bool   # False when the house alone is over the front-end limit
    debts_to_pay_off: list = field(default_factory=list)
    cash_needed: float = 0.0
    front_dti: float = 0.0
    back_dti_before: float = 0.0
    back_dti_after: float = 0.0


def debt_payoff_to_qualify(gross_monthly_income, debts, price, down_pct, program, a=Assumptions()):
    """Which debts to pay off (and how much cash that takes) to qualify for this price.

    Pays off whole debts, starting with the ones that free up the most monthly
    payment per dollar of balance (usually credit cards and nearly-done car loans).
    """
    housing = monthly_housing_cost(price, down_pct, program, a)["total"]
    front, back = dti(gross_monthly_income, housing, debts)
    front_ok = front <= program.max_front_dti + TOLERANCE
    plan = PayoffPlan(
        qualifies_now=front_ok and back <= program.max_back_dti + TOLERANCE,
        fixable_by_paying_debt=front_ok,
        front_dti=front, back_dti_before=back, back_dti_after=back,
    )
    if plan.qualifies_now or not plan.fixable_by_paying_debt:
        return plan

    allowed_debt_payments = program.max_back_dti * gross_monthly_income - housing
    remaining = list(debts)
    by_relief = sorted(debts, key=lambda d: d.monthly_payment / max(d.balance, 1), reverse=True)
    for debt in by_relief:
        if total_debt_payments(remaining) <= allowed_debt_payments + TOLERANCE:
            break
        remaining.remove(debt)
        plan.debts_to_pay_off.append(debt)
        plan.cash_needed += debt.balance

    _, plan.back_dti_after = dti(gross_monthly_income, housing, remaining)
    return plan


# ---------- Cash to close and savings ----------

def cash_to_close(price, down_pct, a=Assumptions()):
    """Down payment plus closing costs."""
    return price * (down_pct + a.closing_cost_pct)


def months_to_save(target, current_savings, monthly_saving):
    """Whole months until savings reach the target. None if it never will."""
    gap = target - current_savings
    if gap <= 0:
        return 0
    if monthly_saving <= 0:
        return None
    return math.ceil(gap / monthly_saving)


def monthly_saving_needed(target, current_savings, months):
    """How much to save each month to hit the target in the given number of months."""
    return max(0.0, (target - current_savings) / months)


# ---------- How much house ----------

def max_price_by_income(gross_monthly_income, debts, down_pct, program, a=Assumptions()):
    """Highest price whose monthly cost fits under both DTI limits."""
    budget = min(program.max_front_dti * gross_monthly_income,
                 program.max_back_dti * gross_monthly_income - total_debt_payments(debts))
    # Every cost except HOA scales with price, so cost = price * per_dollar + hoa.
    per_dollar = monthly_housing_cost(1.0, down_pct, program, replace(a, hoa_monthly=0.0))["total"]
    return max(0.0, (budget - a.hoa_monthly) / per_dollar)


def max_price_by_cash(cash_available, down_pct, a=Assumptions()):
    """Highest price whose down payment + closing costs the cash covers."""
    return cash_available / (down_pct + a.closing_cost_pct)


def affordable_price(gross_monthly_income, debts, current_savings, monthly_saving, months,
                     down_pct, program, a=Assumptions()):
    """What price is reachable after saving for `months`, and what is holding it back."""
    if down_pct < program.min_down_pct:
        raise ValueError(f"{program.name} needs at least {program.min_down_pct:.1%} down")
    cash = current_savings + monthly_saving * months
    by_income = max_price_by_income(gross_monthly_income, debts, down_pct, program, a)
    by_cash = max_price_by_cash(cash, down_pct, a)
    return {
        "cash_at_purchase": cash,
        "price_by_income": by_income,
        "price_by_cash": by_cash,
        "price": min(by_income, by_cash),
        "limited_by": "income/debts" if by_income < by_cash else "savings",
    }
