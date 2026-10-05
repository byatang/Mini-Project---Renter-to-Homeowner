"""Renter-to-Homeowner Roadmap: the Streamlit dashboard.

Run:  streamlit run app.py

This file only displays. Every number comes from finance.py (via renters.analyze and the
agent tools); the only judgment comes from Gemini's tool loop (advisor.decide).
"""

import time
from dataclasses import replace

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

import home_values as hv
from advisor import decide, find_numbers
from agent_tools import STRATEGY_NAMES, RenterTools, money, months, pct
from finance import DEFAULT_LEVEL, LEVELS, PROGRAMS, STRATEGIES, Assumptions
from rates import get_mortgage_rate
from renters import DISCLAIMER, analyze, load_renters
from saved_answers import get_advice

# Ink and terracotta: very different lightness, so the two plans stay distinct for everyone.
INK, CLAY, MUTED = "#161616", "#B4653F", "#9A9A92"
PLAN_COLORS = {"debt first": INK, "deposit first": CLAY}
IN_BUDGET, OVER_BUDGET, PICKED = [180, 101, 63, 230], [150, 150, 142, 130], [22, 22, 22, 255]
INCOME_LABELS = {"salaried": "Salaried", "variable": "Variable income"}
GOAL_LABELS = {"buy_sooner": "Buy sooner", "better_rate": "Stronger terms"}
CHART_MEASURES = {"Savings": "savings", "Debt owed": "debt_balance", "Total DTI": "back_dti"}
PLAY_SECONDS_PER_MONTH = 0.12

st.set_page_config(page_title="Renter-to-Homeowner Roadmap", page_icon="🏠", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Inter+Tight:wght@300;400;500;600&family=Instrument+Serif:ital@0;1&display=swap');
:root { --ink:#161616; --cream:#F4F1EC; --paper:#FBFAF7; --sage:#DDE3DC; --stone:#A9B3AA;
        --clay:#B4653F; --muted:#8E8E86; --line:#E2DDD5; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1400px; padding-top: 1rem; padding-bottom: 5rem; }
h1, h2, h3, h4 { font-family: 'Inter Tight', sans-serif !important; letter-spacing: -0.03em; }
.serif { font-family: 'Instrument Serif', serif; font-style: italic; font-weight: 400;
         color: var(--clay); letter-spacing: -0.01em; }
.muted { color: var(--muted); font-size: 0.85rem; }

/* Disclaimer: pinned to the bottom of the window, always visible */
.disclaimer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 999990;
  padding: 0.6rem 1rem; text-align: center; font-size: 0.85rem; font-weight: 500;
  background: var(--ink); color: var(--cream); }

/* Header */
.head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.5rem;
        margin-bottom: 0.4rem; }
.head h1 { font-size: clamp(2.2rem, 4vw, 3.4rem); font-weight: 400; letter-spacing: -0.05em;
           line-height: 0.95; margin: 0.4rem 0 0 0; }
.head .story { color: #5E5E58; max-width: 34rem; font-size: 0.95rem; margin: 0.5rem 0 0 0; }
.wordmark { font-family: 'Inter Tight', sans-serif; font-weight: 500; letter-spacing: 0.35em;
            font-size: 0.8rem; margin-bottom: 0.6rem; }
.pill { display: inline-block; padding: 0.2rem 0.75rem; margin: 0 0.3rem 0.3rem 0;
        border: 1px solid var(--ink); border-radius: 999px; font-size: 0.66rem;
        text-transform: uppercase; letter-spacing: 0.07em; font-weight: 500; }
.pill.sage { background: var(--sage); border-color: var(--sage); }
.pill.clay { background: var(--clay); border-color: var(--clay); color: var(--cream); }
.pill.light { border-color: rgba(244,241,236,0.6); color: var(--cream); }
.rateline { font-size: 0.82rem; color: #5E5E58; margin: 0.3rem 0 0.9rem 0; }
.rateline .dot { display: inline-block; width: 0.5rem; height: 0.5rem; border-radius: 50%;
                 background: var(--clay); margin-right: 0.45rem; }
.facts { font-size: 0.82rem; color: #5E5E58; margin-bottom: 0.9rem; }
.facts b { color: var(--ink); font-weight: 600; }

/* Tiles: real Streamlit containers, styled by key */
div[class*="st-key-tile-"] { border-radius: 22px; padding: 1.1rem 1.25rem; }
div[class*="st-key-tile-paper"] { background: var(--paper);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 10px 30px rgba(0,0,0,0.05); }
div[class*="st-key-tile-sage"] { background: var(--sage); }
div[class*="st-key-tile-stone"] { background: var(--stone); }
div[class*="st-key-tile-dark"] { background: var(--ink); }
div[class*="st-key-tile-clay"] { background: var(--clay); }
div[class*="st-key-tile-dark"] *, div[class*="st-key-tile-clay"] *,
div[class*="st-key-tile-stone"] * { color: var(--cream) !important; }
div[class*="st-key-tile-"][class*="-kpi-"] { min-height: 150px; }
.kpi-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.8; }
.kpi-big { font-family: 'Inter Tight', sans-serif; font-size: 2.2rem; font-weight: 400;
           letter-spacing: -0.05em; line-height: 1.05; margin-top: 0.5rem; }
.kpi-mid { font-family: 'Inter Tight', sans-serif; font-size: 1.25rem; font-weight: 400;
           letter-spacing: -0.03em; line-height: 1.2; margin-top: 0.5rem; }
.kpi-note { font-size: 0.78rem; opacity: 0.8; margin-top: 0.7rem; }
.card-title { font-family: 'Inter Tight', sans-serif; font-size: 1.35rem; font-weight: 400;
              letter-spacing: -0.03em; margin: 0 0 0.3rem 0; }

/* Month panel */
.month-big { font-family: 'Inter Tight', sans-serif; font-size: 2.6rem; font-weight: 300;
             letter-spacing: -0.05em; line-height: 1; }
.plan-block { border-top: 1px solid var(--line); padding: 0.75rem 0 0.4rem 0; }
.plan-head { display: flex; justify-content: space-between; align-items: center;
             font-weight: 600; font-size: 0.92rem; }
.status { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
          padding: 0.15rem 0.6rem; border-radius: 999px; background: var(--sage); }
.status.yes { background: var(--ink); color: var(--cream); }
.bar { height: 8px; border-radius: 999px; background: #ECE8E1; margin: 0.45rem 0 0.3rem 0;
       overflow: hidden; }
.bar > div { height: 100%; border-radius: 999px; }
.row { display: flex; justify-content: space-between; font-size: 0.82rem; color: #4A4A45;
       padding: 0.12rem 0; }
.swatch { display: inline-block; width: 0.7em; height: 0.7em; border-radius: 50%;
          margin-right: 0.45em; vertical-align: baseline; }

/* Gemini */
.decision { display: inline-block; padding: 0.4rem 1.1rem; border-radius: 999px; color: #fff;
            font-weight: 500; font-size: 1rem; }
.quote { font-size: 1rem; line-height: 1.6; border-left: 3px solid var(--clay);
         padding: 0.1rem 0 0.1rem 1rem; margin: 0.8rem 0 1rem 0; }
.step { display: flex; gap: 0.8rem; padding: 0.5rem 0; border-bottom: 1px solid var(--line);
        font-size: 0.86rem; }
.step-no { flex: 0 0 auto; min-width: 4rem; font-size: 0.66rem; text-transform: uppercase;
           letter-spacing: 0.07em; color: var(--muted); padding-top: 0.15rem; }
.step.final .step-no { color: var(--clay); font-weight: 600; }
.zip-card { border-top: 1px solid var(--line); margin-top: 0.6rem; padding-top: 0.6rem;
            font-size: 0.88rem; }
.zip-card b.big { font-family: 'Inter Tight', sans-serif; font-size: 1.3rem; font-weight: 500; }

/* Story page */
.dim { color: #A6A69E; }
.topbar { display: flex; justify-content: space-between; align-items: center; padding: 0.3rem 0 1rem 0; }
.hero { background: var(--paper); border-radius: 28px; padding: 2.2rem 2.6rem 2rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 12px 40px rgba(0,0,0,0.05); }
.hero-top { display: flex; justify-content: space-between; align-items: center; }
.hero h1 { font-size: clamp(2.1rem, 4.6vw, 3.8rem); line-height: 1.03; font-weight: 400;
           letter-spacing: -0.045em; margin: 1.3rem 0 0.4rem 0; max-width: 62rem; }
.arrow { display: inline-flex; width: 2.2rem; height: 2.2rem; border-radius: 50%;
         border: 1px solid var(--ink); align-items: center; justify-content: center; }
.band { background: var(--ink); color: var(--cream); border-radius: 28px; padding: 1.7rem 2.4rem;
        display: flex; justify-content: space-between; align-items: flex-end; gap: 2rem;
        margin: 2.6rem 0 1.2rem 0; }
.band h2 { color: var(--cream) !important; font-size: clamp(2rem, 4.6vw, 3.6rem); font-weight: 400;
           line-height: 0.98; margin: 0.9rem 0 0 0; letter-spacing: -0.045em; }
.band-num { font-family: 'Inter Tight', sans-serif; font-weight: 300; color: var(--sage);
            font-size: clamp(4rem, 10vw, 8rem); line-height: 0.8; letter-spacing: -0.06em; }
.lede { font-size: 1.15rem; line-height: 1.6; max-width: 46rem; color: #3C3C38; margin: 0 0 1.2rem 0; }
.lede b { color: var(--ink); }
div[class*="st-key-tile-"][class*="-story-"] { min-height: 170px; }
div[class*="st-key-tile-"][class*="-how-"] { min-height: 190px; }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; }
.card-num { font-family: 'Inter Tight', sans-serif; font-weight: 300; font-size: 2.4rem;
            color: var(--stone); letter-spacing: -0.05em; line-height: 0.9; }
.card-name { font-size: 2.2rem !important; font-weight: 400 !important; margin: 0.3rem 0 0 0 !important;
             letter-spacing: -0.045em; }
.plan-line { display: flex; justify-content: space-between; border-top: 1px solid var(--line);
             padding: 0.5rem 0; font-size: 0.93rem; }
.tile-label { font-family: 'Inter Tight', sans-serif; font-size: 1.5rem; font-weight: 400;
              letter-spacing: -0.03em; margin: 0.3rem 0 0.5rem 0; }

/* Widgets */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {
  border-radius: 999px !important; font-weight: 500; }
[data-testid="stBaseButton-primary"] { background: var(--ink) !important; border-color: var(--ink) !important;
                                       color: var(--cream) !important; }
[data-testid="stBaseButton-secondary"] { background: transparent !important;
                                         border: 1px solid var(--ink) !important; }
[data-testid="stAlert"] { border-radius: 16px; }
[data-testid="stSidebar"] { background: var(--paper); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .stRadio label p { font-size: 0.95rem; }
</style>
"""
st.markdown(CSS + f'<div class="disclaimer" role="note">{DISCLAIMER}</div>',
            unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_rate():
    return get_mortgage_rate()


@st.cache_data(show_spinner=False)
def cached_homes():
    return hv.load()


@st.cache_data(show_spinner=False)
def cached_renters():
    return load_renters()


rate = cached_rate()
renters = cached_renters()
homes = cached_homes()
by_name = {r.name: r for r in renters}


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def swatch(plan):
    return f'<span class="swatch" style="background:{PLAN_COLORS[plan]}"></span>'


def pills(*labels, cls=""):
    return "".join(f'<span class="pill {cls}">{label}</span>' for label in labels)


def go_to(page, renter_name=None):
    """Button callback: switch between the story and the dashboard."""
    st.session_state["page"] = page
    if renter_name:
        st.session_state["renter"] = renter_name


st.session_state.setdefault("page", "story")


# ---------- Story (landing page) ----------

def band(label, title, numeral):
    html(f'<div class="band"><div>{pills(label, cls="sage")}<h2>{title}</h2></div>'
         f'<div class="band-num">{numeral}</div></div>')


def tile(col, variant, key, label, big, note, size="big"):
    with col.container(key=f"tile-{variant}-story-{key}"):
        html(f'<div class="kpi-label">{label}</div><div class="kpi-{size}">{big}</div>'
             f'<div class="kpi-note">{note}</div>')


def story():
    a = Assumptions(interest_rate=rate.rate)
    xs = {r.id: analyze(r, a) for r in renters}

    def gap(r):
        p = xs[r.id]["paths"]
        d, s = p["debt_first"].months_to_buy, p["deposit_first"].months_to_buy
        return abs(d - s) if d is not None and s is not None else -1

    star = max(renters, key=gap)             # the renter where the order matters most
    sx, sp = xs[star.id], xs[star.id]["paths"]
    d_m, s_m = sp["debt_first"].months_to_buy, sp["deposit_first"].months_to_buy
    faster = "debt first" if d_m < s_m else "deposit first"

    top = st.columns([3, 1])
    top[0].markdown(f'<div class="topbar"><div class="wordmark">ROADMAP</div></div>',
                    unsafe_allow_html=True)
    top[1].button("Open the dashboard →", key="start-top", on_click=go_to, args=("dashboard",),
                  type="primary", width="stretch")

    html('<div class="hero"><div class="hero-top">' + pills("A short story")
         + '<span class="arrow">↘</span></div>'
         '<h1>Paying rent and thinking you\'ll <span class="serif">never</span> own? '
         '<span class="dim">Many renters assume buying is out of reach. Often the better question '
         'isn\'t whether, but what to do first.</span></h1></div>')
    html(f'<div class="rateline"><span class="dot"></span>Mortgage rate in use: {rate.rate:.2%}, '
         f'as of {rate.as_of} ({rate.source}).</div>')

    band("Chapter 01", "The<br/>assumption", "01")
    html(f'<p class="lede">Meet <b>{star.name}</b>. {star.story} Rent is <b>{money(star.rent)}</b> '
         f'a month. Here is what owning a <b>{money(star.target_price)}</b> home in {star.county} '
         f'would cost, worked out by the code with taxes and insurance included.</p>')
    c = st.columns(3, gap="medium")
    tile(c[0], "paper", "rent", "Rent today", money(star.rent), "per month")
    tile(c[1], "dark", "own", "Monthly cost to own", money(sx["housing_cost"]["total"]),
         f"loan, property tax, insurance, mortgage insurance · {rate.rate:.2%} rate")
    tile(c[2], "sage", "close", "Cash needed to close", money(sx["cash_to_close"]),
         f"{pct(star.down_pct, 1)} down payment plus closing costs")

    band("Chapter 02", "The fork in<br/>the road", "02")
    html(f'<p class="lede">Each month {star.name} has <b>{money(star.extra_per_month)}</b> to spare. '
         f'Two ways to use it: <b>pay down debt first</b>, then save, or <b>save for the deposit '
         f'first</b> while paying only the minimums. Same income, same savings. The only difference '
         f'is the order.</p>')
    c = st.columns([1, 1, 1.2], gap="medium")
    tile(c[0], "dark", "debt", "Debt first · can buy in", months(d_m),
         f"{money(sp['debt_first'].total_debt_interest)} interest on today's debts")
    tile(c[1], "clay", "deposit", "Deposit first · can buy in", months(s_m),
         f"{money(sp['deposit_first'].total_debt_interest)} interest on today's debts")
    tile(c[2], "sage", "gap", "The order matters", f"{months(gap(star))}",
         f"sooner with {faster}, for {star.name}. Other renters land differently.", size="big")

    band("Chapter 03", "Four<br/>renters", "03")
    html('<p class="lede">Four fictional Dallas–Fort Worth renters, each with a different mix of '
         'debt, income and goals. One of them is a genuine close call.</p>')
    for row in (renters[:2], renters[2:]):
        cols = st.columns(2, gap="medium")
        for col, r in zip(cols, row):
            lines = "".join(
                f'<div class="plan-line"><span>{swatch(STRATEGY_NAMES[s])}{STRATEGY_NAMES[s].capitalize()}'
                f'</span><b>{months(xs[r.id]["paths"][s].months_to_buy)}</b></div>' for s in STRATEGIES)
            with col.container(key=f"tile-paper-card-{r.id}"):
                html(f'<div class="card-head"><div>{pills(INCOME_LABELS[r.income_type], GOAL_LABELS[r.goal])}'
                     f'</div><div class="card-num">0{renters.index(r) + 1}</div></div>'
                     f'<h3 class="card-name">{r.name}</h3><p class="muted">{r.story}</p>{lines}')
                st.button(f"See {r.name}'s dashboard →", key=f"story-open-{r.id}", on_click=go_to,
                          args=("dashboard", r.name))

    band("Chapter 04", "How the answer<br/>is made", "04")
    cols = st.columns(3, gap="medium")
    for col, variant, title, points in zip(cols, ("sage", "dark", "paper"), (
            "The math", "The agent", "The check"), (
            ["Code calculates DTI, payments and interest", "Both plans, month by month",
             "Rates and limits are named settings"],
            ["Gemini starts with only a renter's name", "It asks tools for the numbers it needs",
             "It must decide within a few steps, or say so"],
            ["Every number in its explanation is matched", "Same value and same unit, exactly",
             "Mismatches are flagged on screen"])):
        with col:
            html(f'<div class="tile-label">{title}</div>')
            with st.container(key=f"tile-{variant}-how-{title.split()[-1].lower()}"):
                html("<ul>" + "".join(f"<li>{p}</li>" for p in points) + "</ul>")

    html('<div style="height:2rem"></div>')
    with st.container(key="tile-dark-story-end"):
        html('<div class="kpi-label">Your turn</div><div class="kpi-big">Move the sliders, press '
             'play, ask Gemini.</div><div class="kpi-note">Change any renter\'s numbers and watch '
             'both plans recalculate month by month.</div>')
        st.button("Open the dashboard →", key="start-bottom", on_click=go_to, args=("dashboard",))


# ---------- Left panel: renter picker and scenario controls ----------

def control_keys(r):
    return {k: f"{k}-{r.id}" for k in ("program", "level", "rate", "extra", "savings", "price", "down")}


def defaults(r):
    return {"program": r.program, "level": DEFAULT_LEVEL, "rate": round(rate.rate * 100, 2),
            "extra": int(r.extra_per_month), "savings": int(r.savings),
            "price": int(r.target_price), "down": round(r.down_pct * 100, 1)}


def reset_controls(r):
    for name, key in control_keys(r).items():
        st.session_state[key] = defaults(r)[name]


def controls():
    """Left panel. Returns (original renter, scenario renter, rate, DTI level, changed?)."""
    with st.sidebar:
        html('<div class="wordmark">ROADMAP</div>')
        st.button("← Back to the story", key="back-to-story", on_click=go_to, args=("story",))
        name = st.radio("Renter", list(by_name), key="renter",
                        captions=[f"{INCOME_LABELS[r.income_type]} · {GOAL_LABELS[r.goal]}"
                                  for r in renters])
        r = by_name[name]
        keys, base = control_keys(r), defaults(r)
        for k, key in keys.items():
            st.session_state.setdefault(key, base[k])

        html(pills("What if", cls="sage") + f'<div class="card-title">Change {r.name}\'s '
             f'<span class="serif">numbers</span></div>')
        st.caption("Everything recalculates instantly. The renter file never changes.")
        program = st.segmented_control("Loan program", list(PROGRAMS), key=keys["program"]) or base["program"]
        level = st.segmented_control("DTI limits", list(LEVELS), key=keys["level"],
                                     format_func=str.capitalize) or base["level"]
        min_down = PROGRAMS[program].min_down_pct * 100
        if st.session_state[keys["down"]] < min_down:          # switched to a program needing more
            st.session_state[keys["down"]] = round(min_down, 1)
        # Fixed range (lowest minimum of any program to 20%): changing a slider's range makes
        # Streamlit reset it, which would silently change the down payment.
        lowest_down = min(p.min_down_pct for p in PROGRAMS.values()) * 100
        rate_pct = st.slider("Mortgage rate (%)", 5.0, 9.0, step=0.01, key=keys["rate"], format="%.2f%%")
        extra = st.slider("Extra cash per month ($)", 0, 2_000, step=25, key=keys["extra"])
        savings = st.slider("Savings today ($)", 0, 60_000, step=500, key=keys["savings"])
        price = st.slider("Target home price ($)", 100_000, 400_000, step=5_000, key=keys["price"])
        down = st.slider("Down payment (%)", round(lowest_down, 1), 20.0, step=0.5, key=keys["down"],
                         format="%.1f%%")
        if down < min_down:
            st.caption(f"{program} needs at least {min_down:.1f}% down, so {min_down:.1f}% is used.")
            down = min_down
        st.button("↺ Reset to original numbers", on_click=reset_controls, args=(r,), width="stretch")
        st.caption(f"Original: {base['program']}, {base['down']:.1f}% down, {base['rate']:.2f}% rate, "
                   f"{money(base['extra'])}/mo extra, {money(base['savings'])} saved, "
                   f"{money(base['price'])} home, {DEFAULT_LEVEL} limits.")

    rate_changed = abs(rate_pct - base["rate"]) > 1e-6
    changed = (rate_changed or program != base["program"] or level != base["level"]
               or extra != base["extra"] or savings != base["savings"] or price != base["price"]
               or abs(down - base["down"]) > 1e-6)
    scenario = replace(r, program=program, extra_per_month=extra, savings=savings,
                       target_price=price, down_pct=round(down / 100, 4))
    scenario_rate = (replace(rate, rate=rate_pct / 100, source="What-if rate set in the app",
                             is_live=False) if rate_changed else rate)
    return r, (scenario if changed else r), scenario_rate, level, changed


# ---------- Charts ----------

def styled(chart):
    return (chart.configure_view(stroke=None)
            .configure_axis(grid=True, gridColor="#ECE8E1", domain=False, tickColor="#ECE8E1",
                            labelColor="#6E6E68", labelFont="Inter", titleFont="Inter",
                            titleColor="#6E6E68", titleFontWeight=400)
            .configure_legend(labelFont="Inter", labelColor="#3C3C38", symbolType="circle"))


def plan_frame(paths):
    rows = []
    for s in STRATEGIES:
        for m in paths[s].monthly:
            rows.append({"Plan": STRATEGY_NAMES[s], "Month": m["month"], "savings": m["savings"],
                         "debt_balance": m["debt_balance"], "back_dti": m["back_dti"]})
    return pd.DataFrame(rows)


def plan_chart(df, field, current_month, target=None, target_label=""):
    """Two plans, thin lines. Hover for values; click a month to inspect it."""
    is_pct = field == "back_dti"
    fmt = ".1%" if is_pct else "$,.0f"
    color = alt.Color("Plan:N", scale=alt.Scale(domain=list(PLAN_COLORS), range=list(PLAN_COLORS.values())),
                      legend=alt.Legend(orient="top", title=None))
    base = alt.Chart(df).encode(
        x=alt.X("Month:Q", title="Months from now", axis=alt.Axis(tickMinStep=1)),
        y=alt.Y(f"{field}:Q", title=None, axis=alt.Axis(format=".0%" if is_pct else "$,.0f")),
        color=color)
    pick = alt.selection_point(name="pick", fields=["Month"], nearest=True, on="click")
    layers = [
        base.mark_line(strokeWidth=2),
        base.mark_point(size=220, opacity=0).encode(          # big, invisible hit targets
            tooltip=["Plan:N", "Month:Q", alt.Tooltip(f"{field}:Q", format=fmt)]).add_params(pick),
        base.transform_window(rank="rank(Month)", sort=[{"field": "Month", "order": "descending"}],
                              groupby=["Plan"]).transform_filter("datum.rank == 1")
            .mark_point(size=90, filled=True, shape="diamond"),
        alt.Chart(pd.DataFrame({"Month": [current_month]})).mark_rule(color=CLAY, strokeWidth=2)
            .encode(x="Month:Q"),
    ]
    if target is not None:
        t = pd.DataFrame({"y": [target], "label": [target_label]})
        layers += [alt.Chart(t).mark_rule(strokeDash=[4, 4], color=MUTED).encode(y="y:Q"),
                   alt.Chart(t).mark_text(align="left", dx=4, dy=-6, color="#6E6E68", font="Inter")
                       .encode(y="y:Q", x=alt.value(0), text="label:N")]
    return styled(alt.layer(*layers).properties(height=300))


# ---------- Month detail panel ----------

def month_detail(paths, x, m):
    need, lim = x["cash_to_close"], x["limits"]
    blocks = [f'<div class="muted">Both plans at</div><div class="month-big">Month {m}</div>']
    for s in STRATEGIES:
        p, plan = paths[s], STRATEGY_NAMES[s]
        bought = p.months_to_buy is not None and m >= p.months_to_buy
        row = p.monthly[min(m, len(p.monthly) - 1)]
        progress = max(0.0, min(1.0, row["savings"] / need)) if need else 1.0
        status = ('<span class="status yes">Can buy ✓</span>' if bought else
                  '<span class="status">Saving</span>')
        when = (f"bought in month {p.months_to_buy}" if bought and m > p.months_to_buy else
                f"can buy in {months(p.months_to_buy)}" if p.months_to_buy is not None else
                "can't buy within 10 years")
        blocks.append(
            f'<div class="plan-block"><div class="plan-head"><span>{swatch(plan)}{plan.capitalize()}'
            f'</span>{status}</div>'
            f'<div class="bar"><div style="width:{progress * 100:.1f}%;background:{PLAN_COLORS[plan]}">'
            f'</div></div>'
            f'<div class="row"><span>Saved toward closing</span><b>{money(row["savings"])} of {money(need)}</b></div>'
            f'<div class="row"><span>Debt still owed</span><b>{money(row["debt_balance"])}</b></div>'
            f'<div class="row"><span>Total DTI</span><b>{pct(row["back_dti"], 1)} vs {pct(lim.back, 1)} limit</b></div>'
            f'<div class="row"><span></span><span class="muted">{when}</span></div></div>')
    return "".join(blocks)


# ---------- Gemini ----------

def show_steps(steps):
    rows = []
    for line in steps:
        text = line.split("-> ", 1)[-1]
        final = "submit_decision" in line or "No decision" in line or "unavailable" in line
        step_no = line.split(" ->")[0].strip() if line.startswith("Step") else ""
        rows.append(f'<div class="step{" final" if final else ""}"><span class="step-no">'
                    f'{step_no}</span><span>{text}</span></div>')
    html("".join(rows))


def show_ai(r, scenario, scenario_rate, level, x, is_what_if):
    html('<div class="card-title">Gemini\'s <span class="serif">judgment</span></div>')
    if not is_what_if:
        key = f"advice-{r.id}-{rate.rate}-{rate.as_of}"
        refresh = st.button("Ask Gemini again", key=f"refresh-{r.id}",
                            help="Run the tool loop live now instead of showing the saved answer.")
        if refresh or key not in st.session_state:
            with st.spinner(f"Gemini is working through the tools for {r.name}..."):
                st.session_state[key] = get_advice(r, rate, refresh=refresh)
        advice, source, saved_at = st.session_state[key]
        origin = (f"{'Live answer' if source == 'live' else 'Saved answer (same numbers as now)'}"
                  f" from {advice.model}" + (f", generated {saved_at}." if saved_at else "."))
        if source == "saved" and advice.reason:
            origin += f" Gemini couldn't be reached just now ({advice.reason})."
    else:
        html('<p class="muted">What-if scenario: the saved answer is for the original numbers. '
             'Ask Gemini about these numbers (uses a few API calls; not saved).</p>')
        key = f"whatif-{r.id}-{level}-{RenterTools(scenario, scenario_rate, x).fingerprint()}"
        if st.button("Ask Gemini about this scenario", key=f"ask-{key}", type="primary"):
            with st.spinner("Gemini is working through the tools for this scenario..."):
                st.session_state[key] = decide(scenario, scenario_rate, analysis=x,
                                               log=lambda line: None)
        advice = st.session_state.get(key)
        if advice is None:
            return
        origin = f"Live answer for this what-if scenario from {advice.model} (not saved)."

    if advice.status == "decided":
        plan = STRATEGY_NAMES[advice.decision]
        html(f'<span class="decision" style="background:{PLAN_COLORS[plan]}">{plan.capitalize()}</span>'
             f'<div class="quote">{advice.explanation}</div>')
        cited = find_numbers(advice.explanation)
        if advice.mismatches:
            st.error("**Number check: mismatch.** These numbers in the explanation don't match any "
                     f"value the code calculated: {', '.join(advice.mismatches)}", icon="🚩")
        else:
            st.success(f"**Number check passed:** all {len(cited)} numbers cited match values the "
                       "code calculated.", icon="✅")
        st.caption(origin)
    else:
        st.warning(f"**{advice.message}.** The calculated numbers are unaffected."
                   + (f"  \nDetail: {advice.reason}" if advice.reason else ""), icon="⚠️")
    if advice.steps:
        with st.popover("How Gemini got there: tool-loop steps"):
            show_steps(advice.steps)


# ---------- Map ----------

def zip_map(scenario):
    area = hv.with_affordability(hv.zips_in(homes, county=scenario.county), scenario.target_price)
    within = area[area["within_budget"]]
    html(f'<div class="card-title">Where {scenario.name} could <span class="serif">buy</span></div>'
         f'<div class="muted"><b>{len(within)} of {len(area)}</b> {scenario.county} ZIPs at or under '
         f'{money(scenario.target_price)} &nbsp; <span class="swatch" style="background:rgb(180,101,63)">'
         f'</span>in budget &nbsp;<span class="swatch" style="background:rgb(150,150,142)"></span>over</div>')
    df = area.dropna(subset=["lat", "lon"]).copy()
    picked = st.session_state.get(f"picked-zip-{scenario.id}")
    df["color"] = [PICKED if z == picked else IN_BUDGET if ok else OVER_BUDGET
                   for z, ok in zip(df["zip"], df["within_budget"])]
    df["value_text"] = df["typical_value"].map(money)
    df["change_text"] = df["change_1yr"].map(lambda v: f"{v:+.1%}")
    df["status"] = ["In budget" if ok else f"Over budget by {money(g)}"
                    for ok, g in zip(df["within_budget"], df["gap"])]
    layer = pdk.Layer("ScatterplotLayer", id="zips", data=df, get_position="[lon, lat]",
                      get_fill_color="color", get_radius=1300, radius_min_pixels=5,
                      radius_max_pixels=22, pickable=True, stroked=True,
                      get_line_color=[255, 255, 255], line_width_min_pixels=1)
    view = pdk.ViewState(latitude=df["lat"].mean(), longitude=df["lon"].mean(), zoom=8.6)
    event = st.pydeck_chart(
        pdk.Deck(layers=[layer], initial_view_state=view, map_style=None,
                 tooltip={"html": "<b>{zip}</b> · {city}<br/>{value_text} · {status}"}),
        height=330, on_select="rerun", selection_mode="single-object", key=f"map-{scenario.id}")
    objects = (event.selection.get("objects", {}) or {}).get("zips", []) if event else []
    if objects and objects[0].get("zip") != picked:
        st.session_state[f"picked-zip-{scenario.id}"] = objects[0]["zip"]
        st.rerun()
    row = df[df["zip"] == picked]
    if len(row):
        z = row.iloc[0]
        html(f'<div class="zip-card"><b class="big">{z["zip"]}</b> · {z["city"]}<br/>'
             f'Typical home <b>{z["value_text"]}</b> · 1-year change {z["change_text"]} · '
             f'<b>{z["status"]}</b></div>')
    else:
        html('<div class="zip-card muted">Click a circle to see that ZIP\'s details.</div>')
    st.caption(f"Typical = Zillow's mid-market home, not the cheapest. Values as of "
               f"{homes['as_of'].iloc[0]}. {hv.LOCATIONS_NOTE}.")


# ---------- Dashboard ----------

def dashboard():
    r, scenario, scenario_rate, level, is_what_if = controls()
    x = analyze(scenario, Assumptions(interest_rate=scenario_rate.rate), level)
    lim, paths = x["limits"], x["paths"]
    tools = RenterTools(scenario, scenario_rate, x)

    # Header
    html(f'<div class="head"><div>{pills(INCOME_LABELS[r.income_type], GOAL_LABELS[r.goal], r.county)}'
         + (pills("What-if", cls="clay") if is_what_if else "")
         + f'<h1>{r.name}</h1><p class="story">{r.story}</p></div></div>')
    current = f"{rate.rate:.2%}, as of {rate.as_of} ({rate.source})"
    rate_text = (f"Mortgage rate in use: {current}." if scenario_rate is rate else
                 f"Mortgage rate in use: {scenario_rate.rate:.2%} (what-if, set by you with the "
                 f"slider). Current rate: {current}.")
    html(f'<div class="rateline"><span class="dot"></span>{rate_text} Plans are checked against '
         f'the {level} DTI limits.</div>')
    if is_what_if:
        st.warning("You're looking at a **what-if scenario**. Reset it from the left panel.", icon="🎛️")
    debts = "; ".join(f"{d.name} <b>{money(d.balance)}</b> at {pct(d.apr)} ({money(d.monthly_payment)}/mo)"
                      for d in scenario.debts) or "none"
    html(f'<div class="facts">Monthly cost to own <b>{money(x["housing_cost"]["total"])}</b> · rent today '
         f'{money(r.rent)} · cash to close <b>{money(x["cash_to_close"])}</b> · '
         f'{scenario.program}, {pct(scenario.down_pct, 1)} down · lender counts '
         f'<b>{money(x["qualifying_monthly_income"])}/mo</b> · debts: {debts}</div>')

    # KPI tiles
    debt, deposit = (tools.run(f"project_{s}", {"renter_id": r.id})[0] for s in STRATEGIES)
    ok = x["back_dti_today"] <= lim.back and x["front_dti_today"] <= lim.front
    k = st.columns([1, 1, 1.25, 1.25, 1])
    tiles = [
        ("dark", "debt", "Debt first · can buy in", months(paths["debt_first"].months_to_buy),
         f'{debt["Total interest on today\'s debts"]} interest', "big"),
        ("clay", "deposit", "Deposit first · can buy in", months(paths["deposit_first"].months_to_buy),
         f'{deposit["Total interest on today\'s debts"]} interest', "big"),
        ("sage", "timing", "Timing", debt.get("Timing compared with deposit first", "—").capitalize(),
         "comparing the two plans", "mid"),
        ("stone", "interest", "Interest", debt["Interest compared with deposit first"].capitalize(),
         "on today's debts, until paid off", "mid"),
        ("paper", "dti", "Total DTI today", pct(x["back_dti_today"], 1),
         f"limit {pct(lim.back, 1)} · {'within ✓' if ok else 'over the limit'}", "big"),
    ]
    for col, (variant, key, label, value, note, size) in zip(k, tiles):
        with col.container(key=f"tile-{variant}-kpi-{key}"):
            html(f'<div class="kpi-label">{label}</div><div class="kpi-{size}">{value}</div>'
                 f'<div class="kpi-note">{note}</div>')

    # Chart (click a month) + month panel (scrubber, play)
    df = plan_frame(paths)
    last_month = int(df["Month"].max())
    month_key, pending_key = f"month-{r.id}", f"pending-month-{r.id}"
    if pending_key in st.session_state:
        st.session_state[month_key] = st.session_state.pop(pending_key)
    st.session_state.setdefault(month_key, 0)
    if st.session_state[month_key] > last_month:
        st.session_state[month_key] = last_month

    left, right = st.columns([2.1, 1], gap="medium")
    with left.container(key=f"tile-paper-chart-{r.id}"):
        head = st.columns([1.2, 2])
        head[0].markdown('<div class="card-title">Month by <span class="serif">month</span></div>',
                         unsafe_allow_html=True)
        measure = head[1].segmented_control("Show", list(CHART_MEASURES), default="Savings",
                                            key=f"measure-{r.id}", label_visibility="collapsed") or "Savings"
        field = CHART_MEASURES[measure]
        target, label = ((x["cash_to_close"], f"Needed to close: {money(x['cash_to_close'])}")
                         if field == "savings" else
                         (lim.back, f"Limit: {pct(lim.back, 1)}") if field == "back_dti" else (None, ""))
        event = st.altair_chart(plan_chart(df, field, st.session_state[month_key], target, label),
                                width="stretch", on_select="rerun", key=f"chart-{r.id}-{field}")
        picks = (event.selection.get("pick") or []) if event else []
        if picks and "Month" in picks[0]:
            clicked = int(picks[0]["Month"])
            if clicked != st.session_state.get(f"last-click-{r.id}"):
                st.session_state[f"last-click-{r.id}"] = clicked
                st.session_state[pending_key] = clicked
                st.rerun()
        st.caption("Hover for values. Click any month to inspect it on the right. "
                   "◆ marks the month each plan can buy.")

    with right.container(key=f"tile-paper-month-{r.id}"):
        st.slider("Month", 0, last_month, key=month_key)
        play = st.button("▶ Play both plans", key=f"play-{r.id}", width="stretch")
        panel = st.empty()
        if play:
            for m in range(st.session_state[month_key] if st.session_state[month_key] < last_month else 0,
                           last_month + 1):
                panel.markdown(month_detail(paths, x, m), unsafe_allow_html=True)
                time.sleep(PLAY_SECONDS_PER_MONTH)
            st.session_state[pending_key] = last_month
            st.rerun()
        panel.markdown(month_detail(paths, x, st.session_state[month_key]), unsafe_allow_html=True)

    # Gemini + map
    left, right = st.columns([1, 1.15], gap="medium")
    with left.container(key=f"tile-paper-ai-{r.id}"):
        show_ai(r, scenario, scenario_rate, level, x, is_what_if)
    with right.container(key=f"tile-paper-map-{r.id}"):
        zip_map(scenario)


if st.session_state["page"] == "dashboard":
    dashboard()
else:
    story()
html('<div style="height:1.5rem"></div>')
st.caption(f"Sources: mortgage rate, {rate.source}. {hv.SOURCE_NOTE}. {hv.LOCATIONS_NOTE}. "
           "The renters are fictional. AI judgment by Google Gemini; all numbers calculated by code.")
