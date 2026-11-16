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


def build_option_models(symbols: list[str], data: dict[str, pd.DataFrame], rates: pd.Series | None,
                        cache: Cache | None = None, levels: dict[str, pd.Series] | None = None,
                        scale: tuple[float, float] = (1.0, 1.0),
                        surface_config: str = "config/vol_surface.toml",
                        params: dict | None = None) -> dict:
    """An OptionModel per underlying. The volatility level comes from `levels` if given,
    else the cached volatility index for that symbol, else the underlying's own realised
    volatility. `scale` multiplies the level and the skew (pricing-sensitivity test)."""
    import numpy as np

    from backtester.options.chain import OptionModel
    from backtester.options.surface import VOL_INDEX, SurfaceParams, VolSurface, realised_vol
    models = {}
    for s in symbols:
        df = data[s]
        base = params[s] if params and s in params else SurfaceParams.load(s, surface_config)
        p = base.scaled(*scale)
        index = VOL_INDEX.get(s.upper())
        if levels and s in levels:
            level, source = levels[s], "supplied"
        elif index and cache is not None and cache.has(index, "1d"):
            level, source = cache.load(index, "1d")["close"] / 100, f"{index} (volatility index)"
        else:
            # realised volatility runs below implied on average; 1.2 is an assumption
            level, source = realised_vol(df["close"]) * 1.2, "21-day realised volatility x 1.2 (assumption)"
        if "adj_factor" in df:
            # trailing one-year dividend yield, known at each date (no future data)
            q = np.log(df["adj_factor"] / df["adj_factor"].shift(252)).clip(lower=0).fillna(0.0)
            q.index = q.index.tz_convert("America/New_York").normalize().tz_localize(None)
            q = q[~q.index.duplicated(keep="last")]
        else:
            q = 0.0
        models[s] = OptionModel(s, VolSurface(p, level, source), rates, q)
    return models


class Runner:
    """Holds a strategy class with its data loaded, so tests can re-run it cheaply with
    different parameters, settings or price data."""

    def __init__(self, strategy_cls: type[Strategy], config: RunConfig, *,
                 cache: Cache | None = None, data: dict[str, pd.DataFrame] | None = None,
                 rates: pd.Series | None = None, backend: str = "native",
                 option_levels: dict[str, pd.Series] | None = None,
                 option_params: dict | None = None):
        self.strategy_cls, self.config, self.backend = strategy_cls, config, backend
        self.data_meta = None
        if data is None:
            cache = cache or Cache()
            data, self.data_meta = load_data(strategy_cls(), cache, config)
            rates = load_rates(cache) if rates is None else rates
        self.data, self.rates, self.cache = data, rates, cache
        self.option_levels, self.option_params = option_levels, option_params
        if strategy_cls.options_on and config.use_adjusted:
            # option strikes and prices live on real (unadjusted) prices
            import dataclasses
            self.config = dataclasses.replace(config, use_adjusted=False)
        self.runs = 0

    def run(self, params: dict | None = None, *, schedule: list | None = None,
            data: dict[str, pd.DataFrame] | None = None,
            option_scale: tuple[float, float] = (1.0, 1.0), **overrides) -> RunResult:
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
        use = data or self.data
        models = build_option_models(cls.options_on, use, self.rates, self.cache, self.option_levels,
                                     option_scale, params=self.option_params) if cls.options_on else None
        return get_backend(self.backend).run(strategy, use, config, self.data_meta, self.rates, models)


def run_backtest(strategy: Strategy, config: RunConfig, *, cache: Cache | None = None,
                 data: dict[str, pd.DataFrame] | None = None,
                 backend: str = "native") -> RunResult:
    import dataclasses
    data_meta, rates = None, None
    if data is None:
        cache = cache or Cache()
        data, data_meta = load_data(strategy, cache, config)
        rates = load_rates(cache)
    models = None
    if strategy.options_on:
        config = dataclasses.replace(config, use_adjusted=False)
        models = build_option_models(strategy.options_on, data, rates, cache)
    return get_backend(backend).run(strategy, data, config, data_meta, rates, models)
