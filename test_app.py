"""Click through the Streamlit dashboard headless. Keys are blanked, so no FRED or Gemini calls
are made: the rate falls back to the default and the AI step shows "AI explanation unavailable"."""

import pytest
from streamlit.testing.v1 import AppTest

from renters import DISCLAIMER


@pytest.fixture
def story(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("FRED_API_KEY", "")
    at = AppTest.from_file("app.py", default_timeout=120).run()
    assert not at.exception
    return at


@pytest.fixture
def app(story):
    """The dashboard, reached the way a visitor would: from the story page."""
    story.button(key="start-top").click().run()
    assert not story.exception
    return story


def text_of(at):
    return "\n".join(m.value for m in at.markdown)


# ---------- Story (landing page) ----------

def test_app_opens_on_the_story_with_disclaimer_and_rate(story):
    md = text_of(story)
    assert "thinking you'll <span class=\"serif\">never</span> own?" in md
    assert DISCLAIMER in md
    assert "Mortgage rate in use: 6.50%, as of 2026-09-25" in md
    assert not story.sidebar.radio                              # no dashboard controls yet


def test_story_has_four_chapters_with_code_calculated_numbers(story):
    md = text_of(story)
    for chapter in ("Chapter 01", "Chapter 02", "Chapter 03", "Chapter 04"):
        assert chapter in md
    # The story features the renter whose two plans are furthest apart, computed by code.
    from finance import Assumptions
    from renters import analyze, load_renters
    paths = {r.name: analyze(r, Assumptions(interest_rate=0.065))["paths"] for r in load_renters()}
    gaps = {name: abs(p["debt_first"].months_to_buy - p["deposit_first"].months_to_buy)
            for name, p in paths.items()}
    star = max(gaps, key=gaps.get)
    assert f"Meet <b>{star}</b>" in md
    assert f"{paths[star]['debt_first'].months_to_buy} months" in md
    assert f"{paths[star]['deposit_first'].months_to_buy} months" in md
    assert f"{gaps[star]} months" in md


def test_renter_card_opens_that_renters_dashboard(story):
    story.button(key="story-open-priya").click().run()
    assert not story.exception and "<h1>Priya</h1>" in text_of(story)


def test_back_to_the_story(app):
    app.button(key="back-to-story").click().run()
    assert "Chapter 01" in text_of(app)


# ---------- Dashboard ----------


def test_dashboard_opens_on_the_first_renter_with_disclaimer(app):
    md = text_of(app)
    assert "<h1>Maya</h1>" in md
    assert DISCLAIMER in md and "position: fixed" in md        # pinned, always visible


def test_rate_in_use_and_its_date_are_shown(app):
    md = text_of(app)
    assert "Mortgage rate in use: 6.50%, as of 2026-09-25" in md
    assert "Default rate (project placeholder)" in md           # it's the default, not live


def test_kpis_month_panel_ai_and_map_are_on_screen(app):
    md = text_of(app)
    assert "Debt first · can buy in" in md and "21 months" in md
    assert "Deposit first · can buy in" in md and "41 months" in md
    assert "Month 0" in md                                      # month panel starts at today
    assert any("AI explanation unavailable" in w.value for w in app.warning)
    assert app.get("deck_gl_json_chart")                        # the ZIP map


def test_switching_renters(app):
    app.radio(key="renter").set_value("Jordan").run()
    assert not app.exception and "<h1>Jordan</h1>" in text_of(app)


def test_month_scrubber_shows_when_each_plan_can_buy(app):
    app.slider(key="month-maya").set_value(21).run()
    md = text_of(app)
    assert "Month 21" in md and "Can buy ✓" in md               # debt first buys in month 21
    assert "can buy in 41 months" in md                         # deposit first still saving


def test_what_if_slider_updates_numbers_and_labels_the_rate(app):
    app.slider(key="rate-maya").set_value(8.0).run()
    assert not app.exception
    assert "Mortgage rate in use: 8.00% (what-if" in text_of(app)
    assert any("what-if scenario" in w.value for w in app.warning)


def test_more_controls_recalculate(app):
    app.slider(key="savings-maya").set_value(30_000).run()
    app.slider(key="down-maya").set_value(10.0).run()
    assert not app.exception
    assert "FHA, 10.0% down" in text_of(app)


def test_switching_program_keeps_the_down_payment(app):
    """Regression: switching FHA -> Conventional used to reset 3.5% down to 3.0%."""
    app.button_group(key="program-maya").set_value("Conventional").run()
    assert not app.exception
    assert "Conventional, 3.5% down" in text_of(app)


def test_down_payment_below_the_program_minimum_uses_the_minimum(app):
    app.slider(key="down-maya").set_value(3.0).run()            # FHA needs 3.5%
    assert "FHA, 3.5% down" in text_of(app)
    assert any("FHA needs at least 3.5% down" in c.value for c in app.caption)


def test_what_if_does_not_call_gemini_until_asked(app):
    app.slider(key="extra-maya").set_value(900).run()
    assert not any("AI explanation unavailable" in w.value for w in app.warning)
    next(b for b in app.button if b.label == "Ask Gemini about this scenario").click().run()
    assert any("AI explanation unavailable" in w.value for w in app.warning)   # now it ran


def test_reset_returns_to_the_original_numbers(app):
    app.slider(key="price-maya").set_value(250_000).run()
    next(b for b in app.button if "Reset" in b.label).click().run()
    assert app.slider(key="price-maya").value == 190_000
    assert not any("what-if scenario" in w.value for w in app.warning)
