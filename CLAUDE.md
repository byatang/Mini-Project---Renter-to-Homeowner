# Renter-to-Homeowner Roadmap

Class mini-project for BUAN 6V99 (Agentic AI & Process Automation, Fall 2026). It will be
demoed publicly. Course materials are in the parent folder (`../BUAN6V99_*.md`). Current
status and next steps are in `HANDOFF.md`.

## What this project is
An **educational explainer, not a financial adviser.** It walks through four fictional
renters in Dallas-Fort Worth. For each one it explains whether they should **pay down debt
first or save for a deposit (down payment) first**, using that renter's specific numbers.

This note must always be visible on screen, word for word:
> Educational tool, not personalized financial advice. Rates shown are not guaranteed.

## The core rule
**The code handles all the arithmetic. The model makes one judgment: debt first or deposit first.**
- Python calculates every number: DTI, month-by-month savings projections, payments,
  affordability, and interest costs.
- The model receives only numbers the code has already calculated. It never does its own math.
- The model's explanation must cite the specific numbers in front of it (e.g. "at 22% the card
  costs more than the deposit gains you"), not generic advice.
- A check compares every number the model cites against the values the code calculated, and
  flags any mismatch on screen. Matches must be exact (31% = 31.0%, but 27% != 26.99%).
- The model sees only `advisor.fact_sheet()`. Fact labels contain no digits, and the code
  pre-calculates the differences between the paths so the model never subtracts.
- Models are tried in order (`GEMINI_MODELS`); free-tier models are often overloaded (503).
  If all fail, the app shows "AI explanation unavailable" instead of breaking.
- Never pull credit reports (all debts come from the fictional renters file). Never scrape
  listing sites.

## Assumptions and rates
- Lender thresholds and market assumptions are named constants in `finance.py` (`PROGRAMS`,
  `Assumptions`), so they're easy to change. DTI is shown two ways: **comfortable** (classic
  guidelines) and **maximum** (typical automated-underwriting limits).
- Mortgage rate: hardcoded default of **6.5%** (the user's placeholder). An optional live rate
  may come from FRED series `MORTGAGE30US` (free API key). If the live call fails, fall back to
  the hardcoded rate silently. Always show which rate is in use and its date.
- The live rate moves weekly, so the four renters are tuned to work at any rate from 6% to 8%.
  If you change `data/renters.json`, the tests check this.

## How to run
From the project folder, in the VS Code terminal (with `(.venv)` showing):
```
pip install -r requirements.txt   # first time only
python -m pytest                  # run all tests
python demo.py                    # the four renters, printed in the terminal
python home_values.py             # refresh DFW home values from Zillow (monthly)
```

## File structure
```
finance.py                    all the math; named constants at the top
renters.py                    loads the renters, analyze() runs both paths per renter
data/renters.json             the four fictional renters (edit here, not in code)
advisor.py                    fact sheet -> Gemini decision -> number check (python advisor.py)
rates.py                      live FRED mortgage rate, silent fallback to the default
check_keys.py                 confirms the API keys work without printing them
home_values.py                Zillow ZHVI download + DFW ZIP lookups
data/dfw_zip_home_values.csv  254 DFW ZIPs, typical home value + 1-year change
demo.py                       terminal walkthrough of the four renters
test_*.py                     tests (renters are checked at every rate from 6% to 8%)
.claude/settings.json + hooks/  project hooks: stay in project, block the key file, run tests after edits
requirements.txt              Python packages
HANDOFF.md                    what's built, what's not, next steps
```

## Stack and decisions
Python 3.14 in `.venv`, pandas, pytest. Streamlit for the app. Google AI Studio (Gemini, free
tier) for the model. Live mortgage rate from FRED `MORTGAGE30US`. API keys go in `.env`
(git-ignored) and are never pasted in chat. The app shows only the four fictional renters,
with no typed-in user numbers.

## Working with this user
- Business analytics grad student with a real estate background, new to coding, on Windows.
- Build **one step at a time** and explain each step in plain language.
- At the end of each step, commit and push to GitHub (`byatang/Mini-Project---Renter-to-Homeowner`).
- **Do not add a "Co-Authored-By: Claude" line to commit messages.**
- The project path contains spaces and `&`. Always quote it, and use `-LiteralPath` in
  PowerShell. For multi-line Python snippets, write a script file; inline `python -c` breaks
  on quotes in Windows PowerShell 5.1.
