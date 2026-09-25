import pytest

from finance import (
    LEVELS, PROGRAMS, Assumptions, Debt, affordable_price, cash_to_close, debt_payoff_to_qualify,
    dti, max_price_by_cash, max_price_by_income, monthly_housing_cost,
    monthly_principal_interest, monthly_saving_needed, months_to_save,
)

CONV = PROGRAMS["Conventional"]
FHA = PROGRAMS["FHA"]


def test_principal_interest_matches_known_value():
    # $200K, 6.5%, 30 years -> $1,264.14 (any mortgage calculator)
    assert monthly_principal_interest(200_000, 0.065, 30) == pytest.approx(1264.14, abs=0.01)


def test_principal_interest_at_zero_rate():
    assert monthly_principal_interest(360_000, 0, 30) == 1000


def test_mortgage_insurance_only_under_20_pct_for_conventional():
    assert monthly_housing_cost(300_000, 0.10, CONV)["mortgage_insurance"] > 0
    assert monthly_housing_cost(300_000, 0.20, CONV)["mortgage_insurance"] == 0
    assert monthly_housing_cost(300_000, 0.20, FHA)["mortgage_insurance"] > 0


def test_dti():
    front, back = dti(6000, 1500, [Debt("car", 200, 10_000), Debt("card", 100, 2_000)])
    assert front == pytest.approx(0.25)
    assert back == pytest.approx(0.30)


@pytest.mark.parametrize("program", [CONV, FHA])
@pytest.mark.parametrize("level", LEVELS)
def test_max_price_by_income_hits_the_limit_exactly(program, level):
    income, debts, a = 6000, [Debt("car", 400, 12_000)], Assumptions(hoa_monthly=50)
    limits = program.limits(level)
    price = max_price_by_income(income, debts, 0.05, program, a, level)
    front, back = dti(income, monthly_housing_cost(price, 0.05, program, a)["total"], debts)
    assert max(front / limits.front, back / limits.back) == pytest.approx(1.0)


def test_maximum_allows_more_house_than_comfortable():
    for program in (CONV, FHA):
        comfortable = max_price_by_income(6000, [], 0.05, program, level="comfortable")
        maximum = max_price_by_income(6000, [], 0.05, program, level="maximum")
        assert maximum > comfortable


def test_payoff_picks_most_relief_per_dollar_first():
    # $10K/month income, $250K house (~$2,286/month) leaves ~$1,314 for other debts.
    debts = [
        Debt("student loan", 1000, 100_000),  # frees 1% of balance per month
        Debt("card", 400, 8_000),             # frees 5% of balance per month -> pay this first
    ]
    plan = debt_payoff_to_qualify(10_000, debts, 250_000, 0.05, CONV)
    assert not plan.qualifies_now
    assert [d.name for d in plan.debts_to_pay_off] == ["card"]
    assert plan.cash_needed == 8_000
    assert plan.back_dti_after <= CONV.comfortable.back


def test_house_exactly_at_the_limit_qualifies():
    price = max_price_by_income(6000, [], 0.05, CONV)
    assert debt_payoff_to_qualify(6000, [], price, 0.05, CONV).qualifies_now


def test_payoff_cannot_fix_a_house_that_is_too_expensive():
    plan = debt_payoff_to_qualify(4000, [Debt("card", 100, 2000)], 600_000, 0.05, CONV)
    assert not plan.fixable_by_paying_debt
    assert plan.debts_to_pay_off == []


def test_cash_and_savings():
    assert cash_to_close(250_000, 0.05) == pytest.approx(20_000)  # 5% down + 3% closing
    assert months_to_save(20_000, 8_000, 500) == 24
    assert months_to_save(20_000, 25_000, 0) == 0
    assert months_to_save(20_000, 8_000, 0) is None
    assert monthly_saving_needed(20_000, 8_000, 24) == pytest.approx(500)
    assert max_price_by_cash(20_000, 0.05) == pytest.approx(250_000)


def test_affordable_price_reports_the_binding_limit():
    r = affordable_price(6000, [], 0, 100, 12, 0.05, CONV)
    assert r["limited_by"] == "savings"
    assert r["price"] == pytest.approx(r["price_by_cash"])


def test_down_payment_below_program_minimum_is_rejected():
    with pytest.raises(ValueError):
        affordable_price(6000, [], 0, 500, 24, 0.02, CONV)
