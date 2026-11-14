"""Execution backends. Everything that runs a backtest goes through `run_backtest`."""

from __future__ import annotations

import pandas as pd

from backtester.data.cache import Cache
from backtester.engine.native import NativeBackend
from backtester.engine.result import RunConfig, RunResult
from backtester.engine.strategy import Strategy

_BACKENDS = {"native": NativeBackend}


def get_backend(name: str = "native"):
    if name == "lean":
        raise NotImplementedError(
            "The LEAN backend is not built yet; see docs/research/lean-integration.md")
    if name not in _BACKENDS:
        raise ValueError(f"unknown backend {name!r}")
    return _BACKENDS[name]()


def load_data(strategy: Strategy, cache: Cache, config: RunConfig) -> tuple[dict, dict]:
    """Load the strategy's universe from the cache, including history before the start
    date for warm-up. Returns (bars by symbol, metadata by symbol)."""
    data, meta = {}, {}
    for symbol in strategy.universe:
        data[symbol] = cache.load(symbol, strategy.interval, end=config.end)
        meta[symbol] = cache.meta(symbol, strategy.interval)
    return data, meta


def run_backtest(strategy: Strategy, config: RunConfig, *, cache: Cache | None = None,
                 data: dict[str, pd.DataFrame] | None = None,
                 backend: str = "native") -> RunResult:
    data_meta = None
    if data is None:
        data, data_meta = load_data(strategy, cache or Cache(), config)
    return get_backend(backend).run(strategy, data, config, data_meta)
