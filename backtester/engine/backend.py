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


RATE_SYMBOL = "^IRX"   # 13-week Treasury bill yield, in percent


def load_rates(cache: Cache) -> pd.Series | None:
    """Annual benchmark interest rate (decimal) by date, if cached."""
    if not cache.has(RATE_SYMBOL, "1d"):
        return None
    close = cache.load(RATE_SYMBOL, "1d")["close"] / 100
    close.index = close.index.tz_convert("America/New_York").normalize().tz_localize(None)
    return close[~close.index.duplicated(keep="last")]


class Runner:
    """Holds a strategy class with its data loaded, so tests can re-run it cheaply with
    different parameters, settings or price data."""

    def __init__(self, strategy_cls: type[Strategy], config: RunConfig, *,
                 cache: Cache | None = None, data: dict[str, pd.DataFrame] | None = None,
                 rates: pd.Series | None = None, backend: str = "native"):
        self.strategy_cls, self.config, self.backend = strategy_cls, config, backend
        self.data_meta = None
        if data is None:
            cache = cache or Cache()
            data, self.data_meta = load_data(strategy_cls(), cache, config)
            rates = load_rates(cache) if rates is None else rates
        self.data, self.rates = data, rates
        self.runs = 0

    def run(self, params: dict | None = None, *, schedule: list | None = None,
            data: dict[str, pd.DataFrame] | None = None, **overrides) -> RunResult:
        """`schedule` is [(timestamp, params), ...]: parameters switch at those times
        while positions carry over (used by walk-forward)."""
        import dataclasses
        cls = self.strategy_cls
        if schedule:
            times = [t for t, _ in schedule]

            class Scheduled(cls):
                def on_bar(self, ctx):
                    i = sum(1 for t in times if t <= ctx.now) - 1
                    if i >= 0:
                        self.params = {**cls.params, **schedule[i][1]}
                    super().on_bar(ctx)

            Scheduled.__name__ = cls.__name__
            strategy = Scheduled(**(params or schedule[0][1]))
            strategy.name = cls().name
        else:
            strategy = cls(**(params or {}))
        config = dataclasses.replace(self.config, **overrides) if overrides else self.config
        self.runs += 1
        return get_backend(self.backend).run(strategy, data or self.data, config,
                                             self.data_meta, self.rates)


def run_backtest(strategy: Strategy, config: RunConfig, *, cache: Cache | None = None,
                 data: dict[str, pd.DataFrame] | None = None,
                 backend: str = "native") -> RunResult:
    data_meta, rates = None, None
    if data is None:
        cache = cache or Cache()
        data, data_meta = load_data(strategy, cache, config)
        rates = load_rates(cache)
    return get_backend(backend).run(strategy, data, config, data_meta, rates)
