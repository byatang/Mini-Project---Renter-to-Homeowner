# Code review and verification record

**Project:** Renter-to-Homeowner Roadmap  
**Judge:** ChatGPT, used as a code-review judge  
**Review date:** October 2, 2026  
**Review scope:** Source code and tests in this repository, judged against the project requirements in `AGENTS.md`.

## What this review is

ChatGPT reviewed the project code against the stated requirements for correct calculations, a model-led agent loop, grounded explanations, failure handling, edge cases, API-key handling, and the educational disclaimer. The first review identified issues and gaps. A follow-up review compared the updated code with those findings.

This record distinguishes between fixes confirmed by inspecting the source and tests, and fixes whose tests were actually run. The current environment did not allow the project Python executable to start, so the test suite could not be executed during this verification pass.

## Findings and current status

| Finding from ChatGPT's review | Judge's assessment | Current code status | Verification |
|---|---|---|---|
| The model call was initially one-shot, without a tool-and-observation loop or a step cap. | Agree. A single response did not meet the project's agent requirement. | **Fixed.** `advisor.py` now runs a bounded tool loop (`MAX_STEPS`) and the model can request tools, receive their results, and continue before submitting its judgment. | Confirmed in source. Tests for tool-loop behavior are present; not executed in this environment. |
| A decision could initially be submitted after seeing only a summary, without comparing both strategies. | Agree. The decision should be based on both calculated paths. | **Fixed.** The code rejects `submit_decision` until results from both `project_debt_first` and `project_deposit_first` have been received. | Confirmed in source and covered by tests for early submission and projection order; not executed here. |
| The model initially received raw annual income as well as calculated values. | Agree. Raw income could let the model redo arithmetic. | **Partly fixed by design.** Annual income was removed from the renter summary. The model receives lender-counted monthly income and a words-only income trend for variable earners. Debt balances, APRs, and monthly payments remain available as citable facts, so the model still receives some raw debt inputs. | Confirmed in `agent_tools.py`; tests asserting annual income is not sent are present but were not executed. This remaining exposure should be considered against the project's strict “only calculated numbers” rule. |
| The number checker initially allowed a number without a unit to match a fact that had a unit. | Agree. For example, bare `21` should not validate against `21 months`. | **Fixed.** The checker now requires units to match. | Confirmed in source; tests cover unit matching and bare-number citations, but were not executed here. |
| An empty debt list initially caused the summary tool to fail at `max()`. | Agree. A no-debt renter should still be handled. | **Fixed.** The summary reports no debts and skips the APR comparison when the list is empty. | Confirmed in source; tests for empty-debt summary and projections are present but were not executed here. |
| Zero or negative income initially caused division by zero or meaningless DTI. | Agree. Invalid income needs a clear rejection. | **Fixed.** `dti()` raises a clear `ValueError`, and renter data is validated when loaded, including variable income that qualifies at zero or below. | Confirmed in source; tests are present but were not executed here. |
| Duplicate debt names initially caused balances in the projection to overwrite one another. | Agree. That could produce incorrect projections. | **Fixed through input validation.** `load_renters()` rejects repeated debt names for a renter with a descriptive error. | Confirmed in source; tests are present but were not executed here. |
| The required disclaimer was missing from the runnable outputs. | Agree. The project requires the exact note to be visible. | **Fixed for the terminal scripts.** The exact disclaimer is printed first by `demo.py` and `advisor.py`. There is still no Streamlit app in the reviewed files, so an app's on-screen disclaimer cannot be verified. | Exact-text and script-output tests are present; not executed here. App remains unbuilt. |
| The model failure and rate-fallback behavior needed review. | No issue found in the reviewed code for the requested API cases. | **No change required by the review.** The advisor handles key errors and transient failures with fallbacks; the FRED rate helper falls back to the default rate. | Source inspected. No live API calls were made. |
| API-key handling needed review. | No issue found in the reviewed source. | **No change required by the review.** Keys are read from environment variables, and `.env` is ignored by Git. No hardcoded key was found in the searched source. | Source and `.gitignore` inspected; no key values were read or printed. |

## Calculation review

The DTI formula remains:

```text
housing-only DTI = monthly housing cost / gross monthly income
total DTI        = (monthly housing cost + monthly debt payments) / gross monthly income
```

For positive income, the implementation matches these definitions. The projection checks whether the renter can buy at month zero, then advances by month while applying monthly debt interest, minimum payments, savings interest, and available extra cash. The lender thresholds and market assumptions are named values in `finance.py` rather than buried in the calculation logic.

The reviewed terminal programs show the selected mortgage rate and its date. The live-rate helper uses the default rate when the FRED call fails. The model's debt-versus-deposit choice is not hardcoded as an APR threshold; the model submits the decision after receiving tool results.

## Verification limits

- **Tests added or updated:** Source inspection found tests covering the identified fixes.
- **Tests executed for this record:** None. The system `python` command was unavailable, and launching `.venv\\Scripts\\python.exe` returned “Access is denied.” Therefore, test success is **not verified** in this record.
- **Live Gemini/FRED behavior:** Not exercised; no live API calls were made.
- **Streamlit app:** No app source was present, so its interface, persistent disclaimer, and rate display remain unverified.
- **Remaining design question:** The model still sees debt balances, rates, and payments. The project owner should decide whether this satisfies the intended boundary or whether those raw debt figures should also be removed from the model-facing tools.

## Project owner's review

**Agreement with ChatGPT's findings:** Pending the project owner's proofread. This document does not presume the owner's agreement.

**Publishing status:** Draft for proofread. Do not push this write-up until the project owner approves the wording.
