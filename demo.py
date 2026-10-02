"""Walk through the four fictional renters in the terminal: python demo.py

Every number here is calculated by code. The debt-first vs. deposit-first decision
itself is left to the model (added in a later step).
"""

from renters import DISCLAIMER

print(DISCLAIMER + "\n")

import home_values as hv  # noqa: E402  (imported after the disclaimer is on screen)
from finance import DEFAULT_LEVEL, Assumptions  # noqa: E402
from rates import get_mortgage_rate  # noqa: E402
from renters import analyze, load_renters  # noqa: E402

rate = get_mortgage_rate()
a = Assumptions(interest_rate=rate.rate)
homes = hv.load()
print(f"Mortgage rate {rate.rate:.2%} as of {rate.as_of} ({rate.source}) | "
      f"planning against {DEFAULT_LEVEL} DTI limits\n")

for r in load_renters():
    x = analyze(r, a)
    lim = x["limits"]
    print(f"=== {r.name}: {r.story}")
    print(f"    {r.income_type} income ${r.annual_income:,.0f}/yr "
          f"(lender counts ${x['qualifying_monthly_income']:,.0f}/mo) | rent ${r.rent:,.0f} | "
          f"saved ${r.savings:,.0f} | extra ${r.extra_per_month:,.0f}/mo | goal: {r.goal}")
    for d in r.debts:
        print(f"    {d.name}: ${d.balance:,.0f} at {d.apr:.2%}, ${d.monthly_payment:,.0f}/mo")
    print(f"    Target: ${r.target_price:,.0f} in {r.county} ({r.program}, {r.down_pct:.1%} down) "
          f"-> ${x['housing_cost']['total']:,.0f}/mo, ${x['cash_to_close']:,.0f} to close")
    print(f"    DTI today: {x['front_dti_today']:.1%} housing / {x['back_dti_today']:.1%} total "
          f"(limits {lim.front:.0%} / {lim.back:.0%})")
    for name, p in x["paths"].items():
        when = f"buys in {p.months_to_buy} months" if p.months_to_buy is not None else "can't buy in 10 yrs"
        print(f"    {name:<14} {when:<18} debt interest ${p.total_debt_interest:>6,.0f} | "
              f"DTI at purchase {p.back_dti_at_purchase:.1%} | debt left ${p.debt_left_at_purchase:,.0f}")
    area = hv.with_affordability(hv.zips_in(homes, county=r.county), r.target_price)
    print(f"    {area['within_budget'].sum()} of {len(area)} {r.county} ZIPs have a typical home "
          f"at or under ${r.target_price:,.0f}\n")

print(hv.SOURCE_NOTE)
