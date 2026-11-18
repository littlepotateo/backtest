"""Half-hour data processing for the intraday momentum study (Gao, Han, Li and Zhou, 2017): bars to p0..p13 and r1..r13."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FOLDER = Path(__file__).resolve().parent.parent / "strategies" / "intraday_momentum"


def load(name):
    sys.path.insert(0, str(FOLDER))
    spec = importlib.util.spec_from_file_location(f"intraday_{name}", FOLDER / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hh = load("halfhours")
NY = "America/New_York"


def day_bars(day: str, closes, minutes: int = 30, volume: float = 100.0, start="09:30", skip=()):
    """Bars for one session. `closes` has one price per half-hour (the price at its end); bar labels are start times (New York)."""
    t0 = pd.Timestamp(f"{day} {start}", tz=NY)
    rows, prev = [], closes[0]
    per = 30 // minutes
    for j, p in enumerate(closes):
        for k in range(per):
            ts = t0 + pd.Timedelta(minutes=30 * j + minutes * k)
            if (j + 1, k) in skip:
                continue
            c = p if k == per - 1 else prev + (p - prev) * (k + 1) / per
            rows.append((ts.tz_convert("UTC"), prev, max(prev, c), min(prev, c), c, volume))
            prev = c
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).set_index("time")


def ladder(first, step=0.1, n=13):
    return [first + step * i for i in range(n)]


def test_returns_match_a_hand_calculation():
    d1, d2 = ladder(100.0), [101.0, 102.0, 101.5, 103.0, 103.0, 104.0, 102.0, 101.0, 105.0, 106.0, 105.0, 107.0, 108.0]
    bars = pd.concat([day_bars("2026-03-02", d1), day_bars("2026-03-03", d2)])
    p = hh.to_halfhours(bars)
    assert list(p.index) == [pd.Timestamp("2026-03-02").date(), pd.Timestamp("2026-03-03").date()]
    r = hh.returns(p)
    assert np.isnan(r.loc[pd.Timestamp("2026-03-02").date(), "r1"])                  # no previous session
    d = pd.Timestamp("2026-03-03").date()
    assert r.loc[d, "r1"] == pytest.approx(d2[0] / d1[-1] - 1)                       # previous close to 10:00
    assert r.loc[d, "r13"] == pytest.approx(d2[12] / d2[11] - 1)
    assert r.loc[d, "r12"] == pytest.approx(d2[11] / d2[10] - 1)
    assert p.loc[d, "p0"] == pytest.approx(d1[-1])


def test_one_minute_bars_give_the_same_prices_as_half_hour_bars():
    closes = ladder(50.0, 0.37)
    a = hh.to_halfhours(day_bars("2026-03-02", closes, minutes=30))
    b = hh.to_halfhours(day_bars("2026-03-02", closes, minutes=1))
    pd.testing.assert_frame_equal(a[[f"p{j}" for j in range(1, 14)]], b[[f"p{j}" for j in range(1, 14)]])


def test_bars_outside_the_regular_session_are_ignored():
    closes = ladder(100.0)
    pre = day_bars("2026-03-02", [99.0, 99.5], start="08:00")                         # 08:00-09:00 pre-market
    post = day_bars("2026-03-02", [200.0], start="16:00")                              # after the close
    p = hh.to_halfhours(pd.concat([pre, day_bars("2026-03-02", closes), post]))
    assert p.iloc[0]["p13"] == pytest.approx(closes[-1]) and p.iloc[0]["p1"] == pytest.approx(closes[0])


@pytest.mark.parametrize("day", ["2026-03-06", "2026-03-09", "2026-11-02", "2026-11-03"])   # around the spring and autumn clock changes
def test_clock_changes_do_not_move_the_session_grid(day):
    p = hh.to_halfhours(day_bars(day, ladder(100.0)))
    assert len(p) == 1 and p.iloc[0]["p13"] == pytest.approx(101.2)


def test_half_days_and_missing_bars_are_dropped_and_counted():
    full = day_bars("2026-11-25", ladder(100.0))
    half = day_bars("2026-11-27", ladder(100.0, n=7))                                  # closes at 13:00
    gap = day_bars("2026-11-30", ladder(100.0), skip={(5, 0)})                          # one half-hour has no bar
    p = hh.to_halfhours(pd.concat([full, half, gap]))
    assert [d.isoformat() for d in p.index] == ["2026-11-25"]
    assert p.attrs["dropped"] == {"2026-11-27": "incomplete session (7 of 13 half-hours)", "2026-11-30": "incomplete session (12 of 13 half-hours)"}


def test_a_dropped_previous_session_makes_the_next_r1_missing():
    a, b, c = (day_bars(d, ladder(100.0 + i)) for i, d in enumerate(["2026-03-02", "2026-03-03", "2026-03-04"]))
    b = b.iloc[:-2]                                                                    # the middle day is incomplete
    p = hh.to_halfhours(pd.concat([a, b, c]))
    r = hh.returns(p)
    assert [d.isoformat() for d in p.index] == ["2026-03-02", "2026-03-04"]
    assert np.isnan(r.loc[pd.Timestamp("2026-03-04").date(), "r1"])                   # an overnight that spans two days is not the paper's r1


def test_bars_labelled_by_their_end_are_shifted():
    closes = ladder(100.0)
    start_labelled = day_bars("2026-03-02", closes)
    end_labelled = start_labelled.copy()
    end_labelled.index = end_labelled.index + pd.Timedelta(minutes=30)
    a = hh.to_halfhours(start_labelled)
    b = hh.to_halfhours(end_labelled, label="end")
    pd.testing.assert_frame_equal(a, b)


def test_volume_is_summed_per_half_hour():
    bars = day_bars("2026-03-02", ladder(100.0), minutes=1, volume=10.0)
    p = hh.to_halfhours(bars)
    assert p.iloc[0]["v1"] == pytest.approx(300.0) and p.iloc[0]["v13"] == pytest.approx(300.0)


def test_input_must_be_a_dataframe_with_close():
    with pytest.raises(ValueError):
        hh.to_halfhours(pd.DataFrame({"open": [1.0]}, index=pd.to_datetime(["2026-03-02"], utc=True)))
