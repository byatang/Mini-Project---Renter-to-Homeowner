# Code review and verification record

**Project:** Renter-to-Homeowner Roadmap  
**Judge:** ChatGPT, used as a code-review judge  
**Review date:** October 2, 2026  
**Review scope:** Source code and tests in this repository, judged against the project requirements in `AGENTS.md`.

## What this review is

ChatGPT reviewed the project code against the stated requirements for correct calculations, a model-led agent loop, grounded explanations, failure handling, edge cases, API-key handling, and the educational disclaimer. The first review identified issues and gaps. A follow-up review compared the updated code with those findings.

The code findings below were checked against the updated source. The project owner subsequently reported that the full test suite passed (90 tests) after the seven fixes, and that Gemini and FRED were exercised in a live run. Those execution results are owner-reported; ChatGPT did not independently rerun the suite or live APIs while preparing this document.

## Findings and current status

| Finding from ChatGPT's review | Judge's assessment | Current code status | Verification |
|---|---|---|---|
| The model call was initially one-shot, without a tool-and-observation loop or a step cap. | Agree. A single response did not meet the project's agent requirement. | **Fixed.** `advisor.py` now runs a bounded tool loop (`MAX_STEPS`) and the model can request tools, receive their results, and continue before submitting its judgment. | Confirmed in source; the owner reports the tests passed. |
| A decision could initially be submitted after seeing only a summary, without comparing both strategies. | Agree. The decision should be based on both calculated paths. | **Fixed.** The code rejects `submit_decision` until results from both `project_debt_first` and `project_deposit_first` have been received. | Confirmed in source; the owner reports tests for early submission and projection order passed. |
| The model initially received raw annual income as well as calculated values. | Agree. Raw annual income could let the model redo income arithmetic. | **Fixed as intended.** Annual income was removed from the renter summary. The model receives lender-counted monthly income and a words-only income trend for variable earners. Debt balances, APRs, and payments are intentionally retained as citable facts so the explanation can identify a specific debt (for example, “the 26.99% card”), as required by the project's example. The project owner confirmed this design choice. | Confirmed in `agent_tools.py`; the owner reports the tests passed. |
| The number checker initially allowed a number without a unit to match a fact that had a unit. | Agree. For example, bare `21` should not validate against `21 months`. | **Fixed.** The checker now requires units to match. | Confirmed in source; the owner reports the tests passed. |
| An empty debt list initially caused the summary tool to fail at `max()`. | Agree. A no-debt renter should still be handled. | **Fixed.** The summary reports no debts and skips the APR comparison when the list is empty. | Confirmed in source; the owner reports the tests passed. |
| Zero or negative income initially caused division by zero or meaningless DTI. | Agree. Invalid income needs a clear rejection. | **Fixed.** `dti()` raises a clear `ValueError`, and renter data is validated when loaded, including variable income that qualifies at zero or below. | Confirmed in source; the owner reports the tests passed. |
| Duplicate debt names initially caused balances in the projection to overwrite one another. | Agree. That could produce incorrect projections. | **Fixed through input validation.** `load_renters()` rejects repeated debt names for a renter with a descriptive error. | Confirmed in source; the owner reports the tests passed. |
| The required disclaimer was missing from the runnable outputs. | Agree. The project requires the exact note to be visible. | **Fixed for the terminal scripts.** The exact disclaimer is printed first by `demo.py` and `advisor.py`. There is still no Streamlit app in the reviewed files, so an app's on-screen disclaimer cannot be verified. | Exact-text and script-output tests are present; the owner reports the test suite passed. App remains unbuilt. |
| The model failure and rate-fallback behavior needed review. | No issue found in the reviewed code for the requested API cases. | **No change required by the review.** The advisor handles key errors and transient failures with fallbacks; the FRED rate helper falls back to the default rate. | Source inspected. The owner reports a live Gemini/FRED run. |
| API-key handling needed review. | No issue found in the reviewed source. | **No change required by the review.** Keys are read from environment variables, and `.env` is ignored by Git. No hardcoded key was found in the searched source. | Source and `.gitignore` inspected; no key values were read or printed. |

## Calculation review

The DTI formula remains:

```text
housing-only DTI = monthly housing cost / gross monthly income
total DTI        = (monthly housing cost + monthly debt payments) / gross monthly income
```

For positive income, the implementation matches these definitions. The projection checks whether the renter can buy at month zero, then advances by month while applying monthly debt interest, minimum payments, savings interest, and available extra cash. The lender thresholds and market assumptions are named values in `finance.py` rather than buried in the calculation logic.

The reviewed terminal programs show the selected mortgage rate and its date. The live-rate helper uses the default rate when the FRED call fails. The model's debt-versus-deposit choice is not hardcoded as an APR threshold; the model submits the decision after receiving tool results.

## Verification results and limits

- **Automated tests:** The project owner reports **90 tests passed** after the seven fixes.
- **Live integration:** The project owner reports a live run with Gemini and FRED.
- **Independent rerun:** ChatGPT could not independently execute tests in its review environment: the system `python` command was unavailable, and launching `.venv\\Scripts\\python.exe` returned “Access is denied.”
- **Streamlit app:** No app source was present, so its interface, persistent disclaimer, and rate display remain unverified.
- **Debt details shared with the model:** The project owner has decided to keep debt balances, APRs, and payments in the tool results because the explanation needs to identify and discuss specific debts, such as the 26.99% card. This is an intentional product decision, not an unresolved review question.

## Project owner's review

**Agreement with ChatGPT's findings:** The project owner agrees the identified issues warranted fixes and confirms the choice to retain debt balances, APRs, and payments in the model-facing facts for specific, grounded explanations.

**Publishing status:** Updated with the project owner's verification results and design decision.
