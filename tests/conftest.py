import numpy as np
import pandas as pd
import pytest

from backtester.data.cache import normalise_bars


def make_bars(closes, opens=None, start="2024-01-02 14:30", freq="B"):
    """Daily bars from closes; open defaults to the previous close."""
    closes = np.asarray(closes, dtype=float)
    if opens is None:
        opens = np.concatenate([[closes[0]], closes[:-1]])
    opens = np.asarray(opens, dtype=float)
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    return normalise_bars(pd.DataFrame({
        "open": opens, "high": np.maximum(opens, closes), "low": np.minimum(opens, closes),
        "close": closes, "volume": 1e6}, index=idx))


@pytest.fixture
def bars():
    return make_bars
