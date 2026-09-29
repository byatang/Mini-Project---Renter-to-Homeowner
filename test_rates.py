import pytest

from finance import DEFAULT_MORTGAGE_RATE
from rates import FALLBACK, get_mortgage_rate


def fake_fred(*values):
    """Stand-in for FRED's JSON: newest first, like the real call."""
    dates = ["2026-09-24", "2026-09-17", "2026-09-10"]
    obs = [{"date": d, "value": v} for d, v in zip(dates, values)]
    return lambda api_key: {"observations": obs}


def test_live_rate_is_converted_from_percent():
    r = get_mortgage_rate("fake-key", fetch=fake_fred("6.35", "6.30"))
    assert r.rate == pytest.approx(0.0635)
    assert r.as_of == "2026-09-24"
    assert r.is_live
    assert "FRED" in r.source


def test_missing_weeks_are_skipped():
    r = get_mortgage_rate("fake-key", fetch=fake_fred(".", "6.30"))
    assert r.rate == pytest.approx(0.0630)
    assert r.as_of == "2026-09-17"


def test_no_key_falls_back_to_default():
    assert get_mortgage_rate("", fetch=fake_fred("6.35")) == FALLBACK
    assert FALLBACK.rate == DEFAULT_MORTGAGE_RATE
    assert not FALLBACK.is_live


def test_any_failure_falls_back_silently():
    def broken(api_key):
        raise OSError("network down")
    assert get_mortgage_rate("fake-key", fetch=broken) == FALLBACK
    assert get_mortgage_rate("fake-key", fetch=lambda k: {"error": "bad key"}) == FALLBACK
    assert get_mortgage_rate("fake-key", fetch=fake_fred(".", ".")) == FALLBACK


def test_absurd_values_are_ignored():
    assert get_mortgage_rate("fake-key", fetch=fake_fred("650")) == FALLBACK
