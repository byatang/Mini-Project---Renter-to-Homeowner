"""Run the roadmap math for one sample renter. Change the numbers and run: python demo.py"""

from finance import (
    PROGRAMS, Assumptions, Debt, affordable_price, cash_to_close, debt_payoff_to_qualify,
    monthly_housing_cost, monthly_saving_needed, months_to_save,
)

# ----- The renter (typed in by the user) -----
annual_income = 72_000
rent = 1_850
savings = 8_000
debts = [
    Debt("Car loan", monthly_payment=450, balance=15_000),
    Debt("Credit card", monthly_payment=150, balance=5_000),
    Debt("Student loan", monthly_payment=250, balance=25_000),
]
monthly_saving = 500

# ----- The home they want -----
target_price = 250_000
down_pct = 0.035
program = PROGRAMS["FHA"]
a = Assumptions()

income = annual_income / 12

print(f"Monthly gross income: ${income:,.0f}   Rent: ${rent:,.0f}\n")

cost = monthly_housing_cost(target_price, down_pct, program, a)
print(f"A ${target_price:,.0f} home ({program.name}, {down_pct:.1%} down) costs about "
      f"${cost['total']:,.0f}/month:")
for item, amount in cost.items():
    if item != "total":
        print(f"   {item.replace('_', ' '):<20} ${amount:>8,.0f}")
print(f"   {'vs. rent':<20} ${rent:>8,.0f}\n")

plan = debt_payoff_to_qualify(income, debts, target_price, down_pct, program, a)
print(f"DTI: front {plan.front_dti:.1%} (limit {program.max_front_dti:.0%}), "
      f"back {plan.back_dti_before:.1%} (limit {program.max_back_dti:.0%})")
if plan.qualifies_now:
    print("   -> Qualifies on income and debts today.\n")
elif not plan.fixable_by_paying_debt:
    print("   -> The house payment alone is over the limit. Paying off debt won't fix it;"
          " look at a lower price or a bigger down payment.\n")
else:
    names = ", ".join(d.name for d in plan.debts_to_pay_off)
    print(f"   -> Pay off {names} (${plan.cash_needed:,.0f}) to bring back-end DTI to "
          f"{plan.back_dti_after:.1%}.\n")

need = cash_to_close(target_price, down_pct, a) + plan.cash_needed
months = months_to_save(need, savings, monthly_saving)
print(f"Cash needed: ${need:,.0f} (down payment + closing costs"
      f"{' + debt payoff' if plan.cash_needed else ''})")
print(f"   Saving ${monthly_saving:,.0f}/month from ${savings:,.0f}: {months} months")
print(f"   To get there in 24 months: save ${monthly_saving_needed(need, savings, 24):,.0f}/month\n")

print("What can I afford if I keep saving?")
for m in (12, 24, 36):
    r = affordable_price(income, debts, savings, monthly_saving, m, down_pct, program, a)
    print(f"   In {m} months: ${r['price']:,.0f}  (limited by {r['limited_by']})")
