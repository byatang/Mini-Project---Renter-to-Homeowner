# Handoff: Renter-to-Homeowner Roadmap

*As of September 29, 2026, commit `a1d984f` on `main` (pushed to GitHub).*

## What's built

| File | What it does |
|---|---|
| `finance.py` | All the math. Monthly housing cost (principal and interest, property tax, insurance, mortgage insurance, HOA), front- and back-end DTI, which debts to pay off to qualify, cash to close, months to save, monthly saving needed, and the maximum price by income and by cash. |
| `home_values.py` | Downloads Zillow's public ZHVI file, keeps DFW, saves `data/dfw_zip_home_values.csv`. Lookups: list counties and cities, ZIPs in an area, flag ZIPs within budget. |
| `data/dfw_zip_home_values.csv` | 254 DFW ZIPs in 14 counties, as of 2026-08-31. Typical value, value 1 year ago, 1-year change. |
| `demo.py` | Terminal walkthrough of one hardcoded sample renter ($72K income, $1,850 rent, three debts, $8K saved, FHA 3.5% down). |
| `test_finance.py`, `test_home_values.py` | 19 tests. |
| `CLAUDE.md` | Project rules for AI assistants. |

## What works
- All 19 tests pass (`python -m pytest`).
- `python demo.py` runs end to end and shows the monthly cost vs. rent, DTI at both limit
  levels, a debt payoff plan, months to save, affordable price at 12, 24, and 36 months, and
  affordable ZIPs in Tarrant County.
- `python home_values.py` refreshes the Zillow data.
- Mortgage payment math is checked against a known value ($200K, 6.5%, 30 years =
  $1,264.14/month).

## What's incomplete
Measured against the project spec (educational explainer, four fictional renters, the model
decides debt first vs. deposit first):

- **No fictional renters file.** The only renter is hardcoded in `demo.py`. The spec needs
  four renters in a separate data file.
- **Debts have no interest rate.** `Debt` stores only `monthly_payment` and `balance`. The spec's
  core comparison ("at 22% the card costs more than the deposit gains you") needs each debt's
  APR and the code to calculate interest cost.
- **No month-by-month savings projection.** `months_to_save()` returns one number (the gap
  divided by monthly savings). The spec needs a month-by-month table. Savings earn no interest.
- **No debt-first vs. deposit-first comparison in code.** Nothing yet calculates both paths
  side by side (time to buy, interest paid, DTI and price reached), which is what the model
  will judge.
- **`affordable_price()` ignores paying off debt.** It asks "what can I afford after saving
  N months" with the debts unchanged.
- **Income stability isn't modeled.** There's no salaried vs. variable income field. Lenders
  typically average variable income over two years.
- **No model (AI) layer, no number check, no app.** Streamlit isn't installed, there's no
  on-screen disclaimer, and there's no rate display.
- **No live rate.** The rate is a 6.5% placeholder the user hasn't confirmed yet. FRED
  `MORTGAGE30US` isn't wired in.
- **No `README.md`.** It's part of the course grade.

## Known limits (simplifications, not bugs)
- Mortgage insurance uses flat yearly rates (conventional 0.6%, FHA 0.55%). FHA's 1.75% upfront
  premium isn't included.
- The debt payoff plan pays off whole debts only, highest monthly relief per dollar first. It
  ignores the lender rule that drops installment debts with fewer than 10 payments left.
- ZHVI is the *typical* (mid-market) home in each ZIP, not the cheapest.
- Nothing is currently broken.

## Key decisions
- **Stack:** Python 3.14 (`.venv`), pandas, pytest. Streamlit is planned for the app, because the
  course recommends it.
- **Two DTI levels, always shown together:** *comfortable* (Conventional 28/36, FHA 31/43) and
  *maximum* (Conventional 50/50, FHA 46.9/56.9).
- **Default assumptions** (`finance.Assumptions`): 6.5% rate (placeholder), 30 years, 2.2%
  property tax, 1.0% insurance, 3% closing costs, $0 HOA.
- **Home values:** Zillow ZHVI public CSV (mid-tier, all homes), saved in the repo so the app
  never needs to download 118 MB. Credit Zillow as the source on screen.
- **Git:** commit and push at the end of each step. No Co-Authored-By trailer on commits.

## Next steps
1. **Open decisions for the user:**
   - Which model API? The course suggests the Google AI Studio (Gemini) free tier. Claude is
     the other option.
   - Get a free FRED API key (fred.stlouisfed.org) if we want the live-rate layer.
   - Keep the "type in your own numbers" mode alongside the four fictional renters, or only
     show the four?
2. Add an APR to `Debt` and income stability to the renter data. Write `data/renters.json`
   with four fictional renters: varied debt type and APR, salaried vs. variable income, buy
   sooner vs. buy at a better rate, at least one close call.
3. In `finance.py`, add a month-by-month savings projection and a debt-first vs.
   deposit-first comparison. Move the thresholds to clearly named constants.
4. Model layer: send only the calculated numbers and get back a decision plus an explanation.
   Then run a number check that flags any cited number that doesn't match a calculated value.
5. Mortgage rate: hardcoded default, optional FRED live rate with silent fallback, and show the
   rate plus its date.
6. Streamlit app with the always-visible disclaimer, the renter walkthroughs, and the ZIP table.
7. `README.md`.
