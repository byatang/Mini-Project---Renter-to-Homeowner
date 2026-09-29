"""Home-buying math for the Renter-to-Homeowner Roadmap.

Plain formulas, no AI. Every number the app or the agent shows comes from here.
All money is in dollars, all rates are decimals (6.5% -> 0.065), and all
payments and incomes are monthly unless the name says otherwise.
"""

import math
from dataclasses import dataclass, field, replace


# ---------- Named constants: change these, not the formulas ----------

DEFAULT_MORTGAGE_RATE = 0.065  # fallback when the live FRED rate is unavailable (user's placeholder)
SAVINGS_APY = 0.035            # what the deposit fund earns in a high-yield savings account
DEFAULT_LEVEL = "comfortable"  # which DTI limits the renter walkthroughs plan against
MAX_MONTHS = 120               # stop projecting after 10 years


@dataclass
class Debt:
    """A debt entered by hand (we never pull a credit report)."""
    name: str
    monthly_payment: float
    balance: float
    apr: float = 0.0           # yearly interest rate, e.g. 0.2499 for 24.99%


@dataclass
class DtiLimits:
    front: float  # housing cost / gross income
    back: float   # (housing cost + debts) / gross income


@dataclass
class LoanProgram:
    """Lender rules for one kind of mortgage."""
    name: str
    min_down_pct: float        # smallest down payment allowed
    comfortable: DtiLimits     # classic underwriting guidelines
    maximum: DtiLimits         # what automated underwriting typically approves
    mortgage_insurance: float  # yearly rate, as a share of the loan
    mi_always: bool            # FHA charges it at any down payment; conventional only under 20%

    def limits(self, level):
        """level is "comfortable" or "maximum"."""
        return getattr(self, level)


LEVELS = ("comfortable", "maximum")

# Conventional max: Fannie Mae DU allows up to 50% total DTI with no separate
# housing-only limit. FHA max: 46.9% / 56.9% with automated approval.
PROGRAMS = {
    "Conventional": LoanProgram("Conventional", 0.03, DtiLimits(0.28, 0.36),
                                DtiLimits(0.50, 0.50), 0.006, mi_always=False),
    "FHA": LoanProgram("FHA", 0.035, DtiLimits(0.31, 0.43),
                       DtiLimits(0.469, 0.569), 0.0055, mi_always=True),
}


@dataclass
class Assumptions:
    """Market assumptions. Defaults are rough DFW figures; the user can change any of them."""
    interest_rate: float = DEFAULT_MORTGAGE_RATE
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


def debt_payoff_to_qualify(gross_monthly_income, debts, price, down_pct, program,
                           a=Assumptions(), level="comfortable"):
    """Which debts to pay off (and how much cash that takes) to qualify for this price.

    Pays off whole debts, starting with the ones that free up the most monthly
    payment per dollar of balance (usually credit cards and nearly-done car loans).
    """
    limits = program.limits(level)
    housing = monthly_housing_cost(price, down_pct, program, a)["total"]
    front, back = dti(gross_monthly_income, housing, debts)
    front_ok = front <= limits.front + TOLERANCE
    plan = PayoffPlan(
        qualifies_now=front_ok and back <= limits.back + TOLERANCE,
        fixable_by_paying_debt=front_ok,
        front_dti=front, back_dti_before=back, back_dti_after=back,
    )
    if plan.qualifies_now or not plan.fixable_by_paying_debt:
        return plan

    allowed_debt_payments = limits.back * gross_monthly_income - housing
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

def max_price_by_income(gross_monthly_income, debts, down_pct, program, a=Assumptions(),
                        level="comfortable"):
    """Highest price whose monthly cost fits under both DTI limits."""
    limits = program.limits(level)
    budget = min(limits.front * gross_monthly_income,
                 limits.back * gross_monthly_income - total_debt_payments(debts))
    # Every cost except HOA scales with price, so cost = price * per_dollar + hoa.
    per_dollar = monthly_housing_cost(1.0, down_pct, program, replace(a, hoa_monthly=0.0))["total"]
    return max(0.0, (budget - a.hoa_monthly) / per_dollar)


def max_price_by_cash(cash_available, down_pct, a=Assumptions()):
    """Highest price whose down payment + closing costs the cash covers."""
    return cash_available / (down_pct + a.closing_cost_pct)


def affordable_price(gross_monthly_income, debts, current_savings, monthly_saving, months,
                     down_pct, program, a=Assumptions(), level="comfortable"):
    """What price is reachable after saving for `months`, and what is holding it back."""
    if down_pct < program.min_down_pct:
        raise ValueError(f"{program.name} needs at least {program.min_down_pct:.1%} down")
    cash = current_savings + monthly_saving * months
    by_income = max_price_by_income(gross_monthly_income, debts, down_pct, program, a, level)
    by_cash = max_price_by_cash(cash, down_pct, a)
    return {
        "cash_at_purchase": cash,
        "price_by_income": by_income,
        "price_by_cash": by_cash,
        "price": min(by_income, by_cash),
        "limited_by": "income/debts" if by_income < by_cash else "savings",
    }


# ---------- Income ----------

def qualifying_monthly_income(annual_income, income_type="salaried", prior_year_income=None):
    """Income a lender would count. Variable income (commission, gig, self-employed) is
    averaged over two years, or the current year if income is falling."""
    if income_type == "variable" and prior_year_income is not None:
        return min(annual_income, (annual_income + prior_year_income) / 2) / 12
    return annual_income / 12


# ---------- Debt first vs. deposit first, month by month ----------

STRATEGIES = ("debt_first", "deposit_first")
PAID_OFF = 0.005  # balances under half a cent count as paid off


@dataclass
class PathResult:
    strategy: str
    months_to_buy: int | None      # None = can't buy within MAX_MONTHS
    debt_interest_paid: float      # interest paid on debts until purchase
    savings_interest_earned: float
    savings_at_purchase: float
    debt_left_at_purchase: float
    back_dti_at_purchase: float
    monthly: list                  # one dict per month: the projection table
    debt_interest_after_purchase: float = 0.0  # on debt still owed, paid at its minimum

    @property
    def total_debt_interest(self):
        """Interest on today's debts from now until they are gone. Compare paths on this."""
        return self.debt_interest_paid + self.debt_interest_after_purchase


def interest_to_pay_off(balance, apr, monthly_payment, max_months=600):
    """Interest paid if a balance is paid at a fixed monthly payment until it's gone."""
    interest_total = 0.0
    for _ in range(max_months):
        if balance <= PAID_OFF:
            break
        interest = balance * apr / 12
        interest_total += interest
        balance += interest - min(monthly_payment, balance + interest)
    return interest_total


def project_path(strategy, monthly_income, debts, savings, extra_per_month, price, down_pct,
                 program, a=Assumptions(), level=DEFAULT_LEVEL, savings_apy=SAVINGS_APY,
                 max_months=MAX_MONTHS):
    """Simulate one strategy month by month until the renter can buy.

    Every month each debt charges interest and gets its minimum payment. The renter's
    extra cash (plus any payment freed up by a paid-off debt) goes to:
      debt_first    -> the highest-APR debt until it is gone, then savings
      deposit_first -> savings
    They can buy once savings cover the deposit + closing costs AND DTI is within limits.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    limits = program.limits(level)
    need = cash_to_close(price, down_pct, a)
    housing = monthly_housing_cost(price, down_pct, program, a)["total"]
    balances = {d.name: d.balance for d in debts}
    focus = max(debts, key=lambda d: d.apr) if strategy == "debt_first" and debts else None
    debt_interest = savings_interest = 0.0
    rows = []

    for month in range(max_months + 1):
        payments = sum(d.monthly_payment for d in debts if balances[d.name] > PAID_OFF)
        front, back = dti(monthly_income, housing, [Debt("all", payments, 0)])
        rows.append({"month": month, "savings": savings, "debt_balance": sum(balances.values()),
                     "debt_interest_paid": debt_interest, "back_dti": back})
        if (savings >= need and front <= limits.front + TOLERANCE
                and back <= limits.back + TOLERANCE):
            after = sum(interest_to_pay_off(balances[d.name], d.apr, d.monthly_payment)
                        for d in debts)
            return PathResult(strategy, month, debt_interest, savings_interest, savings,
                              sum(balances.values()), back, rows, after)
        if month == max_months:
            break

        cash = extra_per_month
        for d in debts:
            if balances[d.name] <= PAID_OFF:
                cash += d.monthly_payment          # paid off: its payment is now free cash
                continue
            interest = balances[d.name] * d.apr / 12
            debt_interest += interest
            paid = min(d.monthly_payment, balances[d.name] + interest)
            balances[d.name] += interest - paid
            cash += d.monthly_payment - paid       # last payment can be smaller than usual
        if focus and balances[focus.name] > PAID_OFF:
            to_debt = min(cash, balances[focus.name])
            balances[focus.name] -= to_debt
            cash -= to_debt
        growth = savings * savings_apy / 12
        savings_interest += growth
        savings += growth + cash

    return PathResult(strategy, None, debt_interest, savings_interest, savings,
                      sum(balances.values()), back, rows)
