import json
import math

import pytest

from finance import (
    MAX_MONTHS, PROGRAMS, STRATEGIES, Assumptions, Debt, cash_to_close, dti, interest_to_pay_off,
    project_path, qualifying_monthly_income,
)
from renters import RENTERS_FILE, analyze, load_renters

FHA = PROGRAMS["FHA"]


# ---------- Income ----------

def test_salaried_income_is_just_divided_by_12():
    assert qualifying_monthly_income(60_000) == 5_000


def test_variable_income_is_averaged_when_rising_and_current_when_falling():
    assert qualifying_monthly_income(96_000, "variable", 72_000) == 7_000  # average of 2 years
    assert qualifying_monthly_income(60_000, "variable", 72_000) == 5_000  # falling: use current


# ---------- Interest ----------

def test_interest_to_pay_off():
    assert interest_to_pay_off(1_200, 0.0, 100) == 0
    assert interest_to_pay_off(0, 0.25, 100) == 0
    # $1,000 at 1%/month paid $100/month: after 10 payments $58.40 is left, and the 11th
    # payment is $58.40 * 1.01 = $58.98. Total paid $1,058.98 -> $58.98 interest.
    assert interest_to_pay_off(1_000, 0.12, 100) == pytest.approx(58.98, abs=0.01)


# ---------- Month-by-month projection ----------

def test_no_debts_both_strategies_save_the_same_way():
    kwargs = dict(monthly_income=10_000, debts=[], savings=0, extra_per_month=1_000,
                  price=200_000, down_pct=0.035, program=FHA, savings_apy=0.0)
    first, second = (project_path(s, **kwargs) for s in STRATEGIES)
    expected = math.ceil(cash_to_close(200_000, 0.035) / 1_000)
    assert first.months_to_buy == second.months_to_buy == expected
    assert first.monthly[1]["savings"] == 1_000


def test_debt_first_clears_the_highest_apr_debt_before_saving():
    debts = [Debt("student loan", 100, 10_000, 0.0), Debt("card", 50, 1_000, 0.24)]
    p = project_path("debt_first", 10_000, debts, 0, 1_000, 200_000, 0.035, FHA,
                     savings_apy=0.0)
    # Month 1: card is $1,000 + $20 interest - $50 minimum = $970. The $1,000 extra pays
    # that off and the $30 left over goes to savings. The student loan just gets its minimum.
    assert p.monthly[1]["savings"] == pytest.approx(30)
    assert p.monthly[1]["debt_balance"] == pytest.approx(9_900)


def test_deposit_first_waits_when_debt_blocks_the_dti():
    # Housing ~$1,750 on $6,000 income is fine on its own (29% < 31%), but a $900 car payment
    # pushes total DTI to 44% (> 43%), so the renter can't buy until the car is paid off.
    car = Debt("car", 900, 9_000, 0.0)
    p = project_path("deposit_first", 6_000, [car], 50_000, 0, 190_000, 0.035, FHA)
    assert p.months_to_buy == 10
    assert p.debt_left_at_purchase == pytest.approx(0)


def test_unreachable_goal_returns_none():
    p = project_path("deposit_first", 3_000, [], 0, 100, 400_000, 0.035, FHA)
    assert p.months_to_buy is None
    assert len(p.monthly) == MAX_MONTHS + 1


def test_bad_strategy_name_is_rejected():
    with pytest.raises(ValueError):
        project_path("yolo", 5_000, [], 0, 100, 200_000, 0.035, FHA)


# ---------- Bad data is rejected (findings 4 and 7) ----------

@pytest.mark.parametrize("income", [0, -5_000])
def test_dti_rejects_zero_or_negative_income(income):
    with pytest.raises(ValueError, match="income must be greater than zero"):
        dti(income, 1_500, [])


def write_renters(tmp_path, **changes):
    """A one-renter file based on Maya, with some fields changed."""
    row = json.loads(RENTERS_FILE.read_text())[0]
    row.update(changes)
    path = tmp_path / "renters.json"
    path.write_text(json.dumps([row]))
    return path


@pytest.mark.parametrize("income", [0, -78_000])
def test_loading_rejects_zero_or_negative_income(tmp_path, income):
    with pytest.raises(ValueError, match="Renter 'maya': income must be greater than zero"):
        load_renters(write_renters(tmp_path, annual_income=income))


def test_loading_rejects_variable_income_that_averages_to_nothing(tmp_path):
    path = write_renters(tmp_path, income_type="variable", annual_income=40_000,
                         prior_year_income=-60_000)
    with pytest.raises(ValueError, match="income must be greater than zero"):
        load_renters(path)


def test_loading_rejects_duplicate_debt_names(tmp_path):
    card = {"name": "Credit card", "balance": 1_000, "monthly_payment": 50, "apr": 0.2}
    path = write_renters(tmp_path, debts=[card, {**card, "balance": 2_000}])
    with pytest.raises(ValueError, match=r"Renter 'maya': duplicate debt names \['Credit card'\]"):
        load_renters(path)


def test_real_renters_file_passes_validation():
    assert len(load_renters()) == 4


# ---------- The four fictional renters ----------

@pytest.fixture(scope="module")
def renters():
    return load_renters()


def test_four_renters_with_the_required_variety(renters):
    assert len(renters) == 4
    assert {r.income_type for r in renters} == {"salaried", "variable"}
    assert {r.goal for r in renters} == {"buy_sooner", "better_rate"}
    aprs = [d.apr for r in renters for d in r.debts]
    assert min(aprs) < 0.06 and max(aprs) > 0.20  # low-rate loans and high-interest cards


# The live FRED rate moves weekly, so the demo must work across a realistic range.
DEMO_RATES = [0.06, 0.065, 0.07, 0.075, 0.08]


@pytest.mark.parametrize("rate", DEMO_RATES)
def test_every_renter_can_buy_on_both_paths(renters, rate):
    for r in renters:
        for p in analyze(r, Assumptions(interest_rate=rate))["paths"].values():
            assert p.months_to_buy is not None, f"{r.name} can't buy on {p.strategy} at {rate:.2%}"


@pytest.mark.parametrize("rate", DEMO_RATES)
def test_each_renter_keeps_its_story(renters, rate):
    x = {r.id: analyze(r, Assumptions(interest_rate=rate)) for r in renters}
    paths = {k: (v["paths"]["debt_first"], v["paths"]["deposit_first"]) for k, v in x.items()}

    # Maya: the card pushes her over the DTI limit today, and debt first wins on time and interest.
    assert x["maya"]["back_dti_today"] > x["maya"]["limits"].back
    d, s = paths["maya"]
    assert d.months_to_buy < s.months_to_buy and d.total_debt_interest < s.total_debt_interest

    # Jordan: cheap debt, DTI fine, deposit first is far faster.
    assert x["jordan"]["back_dti_today"] <= x["jordan"]["limits"].back
    d, s = paths["jordan"]
    assert s.months_to_buy + 12 <= d.months_to_buy

    # Priya: the close call. Neither path wins on both speed and interest by a wide margin.
    d, s = paths["priya"]
    assert abs(d.months_to_buy - s.months_to_buy) <= 12
    assert abs(d.total_debt_interest - s.total_debt_interest) <= 2_000
