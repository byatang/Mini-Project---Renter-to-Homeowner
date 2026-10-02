# Handoff: Renter-to-Homeowner Roadmap

*As of October 2, 2026, on `main`. 90 tests pass (`python -m pytest`).*

## What's built

| File | What it does |
|---|---|
| `finance.py` | All the math: monthly housing cost, front- and back-end DTI, qualifying income (variable income averaged over two years, or the current year if falling), cash to close, month-by-month projection of debt first vs. deposit first (`project_path`), interest to pay off remaining debt. Named constants at the top. |
| `renters.py` | Loads and validates `data/renters.json`; `analyze()` runs both paths per renter. Holds the `DISCLAIMER` text. |
| `data/renters.json` | Four fictional renters (Maya, Jordan, Priya, Marcus), tuned to work at any rate from 6% to 8%. |
| `agent_tools.py` | Tools the model can call: `get_renter_summary`, `project_debt_first`, `project_deposit_first`, `check_dti`, `submit_decision`. They return pre-formatted, code-calculated numbers. |
| `advisor.py` | Bounded tool loop: the model asks for tools, the code runs them, repeat until `submit_decision` or `MAX_STEPS = 6`. Then the number check. `python advisor.py` runs all four renters live. |
| `rates.py` | Live FRED `MORTGAGE30US` rate; silent fallback to 6.5% on any failure. |
| `home_values.py` + `data/dfw_zip_home_values.csv` | Zillow ZHVI, 254 DFW ZIPs, as of 2026-08-31. |
| `demo.py` | Terminal walkthrough of the four renters (numbers only, no AI). |
| `check_keys.py` | Confirms the Gemini and FRED keys work without printing them. |
| `.claude/` | Hooks: block files outside the project, block `.env`, run tests after every edit. |

## What works
- `python demo.py` and `python advisor.py` both open with the disclaimer, then run end to end.
- Live runs: renters reach a decision in 2 to 3 steps, and every cited number has passed the
  number check.
- Without API keys, everything still runs: the rate falls back to 6.5%, and the AI step reports
  "AI explanation unavailable" instead of crashing.

## Review findings: what changed (October 2)

1. **Disclaimer.** `renters.DISCLAIMER` holds the exact text. `demo.py` and `advisor.py` print it
   as their first line. Tests run both scripts (with blank keys, so no API calls) and check
   line 1 word for word. (`test_disclaimer.py`)
2. **Decision grounding.** `submit_decision` is rejected until the model has received results
   from **both** `project_debt_first` and `project_deposit_first`. The rejection is sent back
   as a tool message naming the missing projection(s), and the loop continues. There's no
   fixed order, and `check_dti` isn't required. `MAX_STEPS` raised from 4 to 6. New tests: a
   model that decides after only `get_renter_summary` is sent back (twice) and then accepted;
   either projection order works.
3. **Empty debts.** `get_renter_summary` handles `"debts": []`: it reports `Debts: none` and
   omits the APR-gap fact, and never calls `max()` on an empty list. Test covers the summary
   and both projections.
4. **Income validation.** `finance.dti()` raises a clear `ValueError` when gross monthly
   income is zero or negative (a guard before the formula; the formula is unchanged).
   `renters.load_renters()` validates each renter on load, including variable income that
   averages to zero or less. Tests for 0 and negative income in both places.
5. **Unit matching.** In the number check, a cited number must carry the same unit as the
   fact it matches. A bare "21" no longer matches "21 months" (or "43" vs. "43.0%", or "6,364"
   vs. "$6,364"). A bare number still matches a unitless fact. New test.
6. **Model inputs.** Raw annual income (this year and last year) removed from
   `get_renter_summary`. The model now gets the monthly income the lender counts, plus, for
   variable earners, a words-only `Income trend` ("rising this year" or "falling this year")
   so the direction isn't lost. Debt balances, APRs, and payments stay as citable facts. The
   printed step line now shows the lender-counted income too. Tests confirm no annual income
   reaches the model.
7. **Duplicate debt names.** `load_renters()` rejects a renter with two debts of the same name,
   with an error naming the renter and the duplicate. (The projection tracks balances by debt
   name, so duplicates would silently merge.) Test added.

Not changed: the DTI formula and all projection math in `finance.py`.

## What's incomplete
- **Streamlit app.** Not started (paused at the user's request). It needs: the always-visible
  disclaimer on screen, the rate in use and its date, both paths with month-by-month charts,
  the model's decision with number-check flags, and the ZIP table with Zillow credit.
- **Saved AI answers.** Agreed but not built: reuse the last good answer when every model is
  down, only when the renter's numbers are identical, labeled with the model and the time.
- **`README.md`.** A draft was previewed in chat but not written. It needs updating for the
  tool loop and these fixes.
- **Open question: retry 503?** Only 429 and 500 are retried. 503 ("high demand") is the
  error Google actually returns most often. It moves straight to the next model, so when all
  models are busy at once, a renter can end "AI explanation unavailable". Adding 503 to
  `RETRY_CODES` is a one-line change, awaiting the user's decision.

## Known limits (simplifications, not bugs)
- Debt first uses only monthly extra cash, never a lump sum from existing savings, and
  targets only the single highest-APR debt before switching to saving.
- The comparison ignores rent paid while waiting and equity built after buying.
- Mortgage insurance uses flat yearly rates; FHA's 1.75% upfront premium isn't included.
- ZHVI is the *typical* home in each ZIP, not the cheapest.
- A backup model that takes over mid-run gets earlier steps retold as plain text (Gemini
  rejects another model's "thought signatures"), so it loses the first model's hidden
  reasoning, but not any numbers.

## Key decisions
- **Stack:** Python 3.14, pandas, pytest, Streamlit (for the app), Google Gemini (free tier),
  FRED for the rate. Keys live in `.env` (git-ignored, blocked by a hook).
- **Code does all arithmetic; the model makes one judgment.** Every cited number must exactly
  match a tool result: same value, same unit.
- **Tool loop:** one step = one model call; `MAX_STEPS = 6`; quarterly checkpoints in the
  projections, to keep the number check strict; no decision by the limit gives "No decision
  reached", never a guess.
- **Errors:** 429 and 500 are retried; other errors move to the next model
  (`gemini-3.8-flash` -> `gemini-3.5-flash` -> `gemini-3.1-flash-lite`); a rejected key (401,
  403, or 400 "API key") stops right away with "AI explanation unavailable".
- **DTI:** planned against the *comfortable* limits (Conventional 28/36, FHA 31/43); *maximum*
  limits available.
- **Git:** commit and push at the end of each step; no Co-Authored-By trailer.

## Next steps
1. Decide on retrying 503.
2. Build the Streamlit app with saved AI answers.
3. Write `README.md` from the actual code.
