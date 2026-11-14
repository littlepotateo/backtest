"""`bt` command line."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtester.analysis.metrics import compute_metrics
from backtester.data.cache import Cache, from_csv, to_utc
from backtester.data.ibkr import parse_ibkr_history
from backtester.engine.backend import Runner
from backtester.engine.costs import CostModel
from backtester.engine.result import RunConfig
from backtester.engine.strategy import Strategy


def load_strategy_class(path: str | Path) -> type[Strategy]:
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"strategy_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = [v for v in vars(module).values()
             if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
             and v.__module__ == module.__name__]
    if len(found) != 1:
        raise SystemExit(f"{path} must define exactly one Strategy subclass (found {len(found)})")
    return found[0]


def _parse_params(items: list[str]) -> dict:
    out = {}
    for item in items or []:
        key, _, raw = item.partition("=")
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def _pct(x):
    return "n/a" if x is None else f"{x * 100:,.2f}%"


def _num(x, digits=2):
    return "n/a" if x is None else f"{x:,.{digits}f}"


def format_summary(meta: dict, m: dict) -> str:
    lines = [
        f"{meta['strategy']}  {meta['params']}",
        f"{', '.join(meta['universe'])} · {meta['interval']} bars · "
        f"{m['start'][:10]} to {m['end'][:10]} ({m['trading_days']} trading days)",
        "",
        f"  Total return        {_pct(m['total_return'])}",
        f"  Annual return       {_pct(m['cagr'])}",
        f"  Volatility          {_pct(m['volatility'])}",
        f"  Sharpe              {_num(m['sharpe'])}",
        f"  Sortino             {_num(m['sortino'])}",
        f"  Max drawdown        {_pct(m['max_drawdown'])}  (longest {m['longest_drawdown_days']} days)",
        f"  Trades              {m['trades']}  (win rate {_pct(m['win_rate'])}, "
        f"profit factor {_num(m['profit_factor'])})",
        f"  Time in market      {_pct(m['time_in_market'])}",
        f"  Costs               ${_num(m['total_commission'])} commission, "
        f"${_num(m['total_slippage'])} slippage",
    ]
    if "benchmark_total_return" in m:
        lines += [f"  Benchmark           {_pct(m['benchmark_total_return'])} total, "
                  f"{_pct(m['benchmark_max_drawdown'])} max drawdown",
                  f"  Beta / alpha        {_num(m['beta'])} / {_pct(m['alpha_annual'])} per year"]
    sources = {s: d.get("source", "?") for s, d in meta.get("data", {}).items()}
    if sources:
        lines += ["", "  Data: " + ", ".join(f"{s} ({src})" for s, src in sources.items())]
    for w, n in meta.get("warnings", {}).items():
        lines.append(f"  Warning: {w.replace('_', ' ')} × {n}")
    for note in meta.get("notes", []):
        lines.append(f"  Note: {note}")
    return "\n".join(lines)


def cmd_data(args):
    rows = Cache(args.cache).list()
    if not rows:
        print("cache is empty")
    for r in rows:
        print(f"{r['symbol']:<8}{r['interval']:<5}{r['bars']:>8} bars  "
              f"{r['start'][:10]} to {r['end'][:10]}  source={r['source']}  adjusted={r['adjusted']}")


def cmd_ingest_ibkr(args):
    cache = Cache(args.cache)
    for f in args.files:
        bars, interval = parse_ibkr_history(Path(f))
        saved = cache.save(args.symbol, interval, bars, source="ibkr", adjusted=args.adjusted)
        print(f"{args.symbol.upper()} {interval}: +{len(bars)} bars from {f}, {len(saved)} cached")


def cmd_fetch_yahoo(args):
    from backtester.data.yahoo import fetch_yahoo
    bars = fetch_yahoo(args.symbol, args.interval, args.start, args.end)
    saved = Cache(args.cache).save(args.symbol, args.interval, bars, source="yahoo",
                                   adjusted="split-adjusted; adj_factor adds dividends")
    print(f"{args.symbol.upper()} {args.interval}: {len(saved)} bars cached "
          f"({saved.index[0].date()} to {saved.index[-1].date()})")


def cmd_fetch_rates(args):
    from backtester.data.yahoo import fetch_yahoo
    from backtester.engine.backend import RATE_SYMBOL
    bars = fetch_yahoo(RATE_SYMBOL, "1d", args.start, None, allow_nonpositive=True)
    saved = Cache(args.cache).save(RATE_SYMBOL, "1d", bars, source="yahoo", adjusted="not a price",
                                   allow_nonpositive=True)
    print(f"13-week Treasury bill yield: {len(saved)} days cached "
          f"({saved.index[0].date()} to {saved.index[-1].date()}), latest {saved['close'].iloc[-1]:.2f}%")


def cmd_calibrate_options(args):
    import numpy as np

    from backtester.engine.backend import load_rates
    from backtester.options.calibrate import calibrate, save_params
    from backtester.options.surface import VOL_INDEX, realised_vol
    snap = json.loads(Path(args.file).read_text())
    cache, sym = Cache(args.cache), snap["symbol"].upper()
    day = to_utc(snap["date"]) + pd.Timedelta(days=1)
    index = VOL_INDEX.get(sym)
    if index and cache.has(index, "1d"):
        series, src = cache.load(index, "1d")["close"] / 100, index
    else:
        series, src = realised_vol(cache.load(sym, "1d")["close"]) * 1.2, "21-day realised volatility x 1.2"
    level = float(series[series.index < day].dropna().iloc[-1])
    rates = load_rates(cache)
    rate = float(rates[rates.index <= snap["date"]].iloc[-1]) if rates is not None else 0.0
    bars = cache.load(sym, "1d")
    years = (bars.index[-1] - bars.index[0]).days / 365.25
    q = max(float(np.log(bars["adj_factor"].iloc[-1] / bars["adj_factor"].iloc[0]) / years), 0.0)
    rep = calibrate(snap, level, rate, q)
    rep["level_source"] = src
    print(f"{sym} on {rep['date']}: spot {rep['spot']}, level {level:.4f} from {src}, "
          f"rate {rate:.2%}, dividend yield {q:.2%}")
    print(f"  quotes: {rep['quote_source']}")
    for row in rep["table"]:
        print(f"  {row['expiry']} {row['right']} {row['strike']:>6g}  market {row['market_mid']:>7.2f}  "
              f"model {row['model_price']:>7.2f}  ({row['price_error_pct']:+.1f}%)  "
              f"vol {row['market_iv']:.3f} vs {row['model_iv']:.3f}")
    p = rep["params"]
    print(f"  fitted: ratio {p['ratio']:.3f}, skew {p['skew']:.3f}, curvature {p['curvature']:.3f}, "
          f"term {p['term']:.3f}, half-spread {p['half_spread']:.2%}")
    print(f"  price error: mean {rep['mean_abs_price_error_pct']:.1f}%, worst {rep['max_abs_price_error_pct']:.1f}%")
    if not args.dry_run:
        save_params(sym, rep, args.config)
        out = Path(args.file).with_suffix(".report.json")
        out.write_text(json.dumps(rep, indent=2))
        print(f"  saved to {args.config} and {out}")


def cmd_import_csv(args):
    saved = Cache(args.cache).save(args.symbol, args.interval, from_csv(args.file),
                                   source=args.source, adjusted=args.adjusted)
    print(f"{args.symbol.upper()} {args.interval}: {len(saved)} bars cached")


def _setup(args):
    """Strategy class, parameters, runner (data loaded) and benchmark series from run options."""
    cls = load_strategy_class(args.strategy)
    params = _parse_params(args.param)
    cls(**params)                                   # validates parameter names early
    costs = CostModel.from_toml(args.costs).scaled(args.cost_multiplier)
    config = RunConfig(start=args.start, end=args.end, initial_cash=args.cash, costs=costs,
                       fill=args.fill, max_leverage=args.max_leverage,
                       allow_short=not args.no_short, use_adjusted=not args.raw_prices,
                       cash_interest=not args.no_cash_interest)
    cache = Cache(args.cache)
    runner = Runner(cls, config, cache=cache, backend=args.backend)
    bench_symbol = args.benchmark or cls.universe[0]
    benchmark = None
    if cache.has(bench_symbol, cls.interval):
        b = cache.load(bench_symbol, cls.interval, end=args.end)
        benchmark = (b["close"] * b["adj_factor"]) if config.use_adjusted else b["close"]
    return cls, params, runner, benchmark, bench_symbol


def _from(benchmark, start):
    return None if benchmark is None else benchmark[benchmark.index >= start]


def _save_run(args, result, metrics, bench_symbol, benchmark):
    result.meta["benchmark"] = bench_symbol if benchmark is not None else None
    result.meta["strategy_file"] = str(args.strategy)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = result.save(Path(args.out) / f"{stamp}-{result.meta['strategy']}")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return out


def cmd_run(args):
    cls, params, runner, benchmark, bench_symbol = _setup(args)
    result = runner.run(params)
    metrics = compute_metrics(result, args.risk_free, _from(benchmark, result.equity.index[0]))
    out = _save_run(args, result, metrics, bench_symbol, benchmark)
    print(format_summary(result.meta, metrics))
    print(f"\n  Saved to {out}")


def cmd_optimize(args):
    from backtester.analysis.optimize import grid_search
    cls, _, runner, _, _ = _setup(args)
    res = grid_search(runner, ledger=Path(args.strategy).with_suffix(".trials.jsonl"))
    table = res["table"].sort_values("sharpe", ascending=False)
    print(f"{cls.__name__}: {len(table)} configurations\n")
    print(table.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nThe best row is the best in hindsight. Use `bt validate` to see whether it holds up.")


def cmd_check(args):
    from backtester.analysis import checks
    cls, params, runner, _, _ = _setup(args)
    look = checks.lookahead_test(runner, {**cls.params, **params})
    print("Look-ahead test: " + ("passed" if look["passed"] else "FAILED"))
    for c in look["cuts"]:
        print(f"  data cut at {c['cutoff'][:10]}: {c['orders_checked']} orders, "
              f"{'identical' if c['identical'] else 'DIFFERENT'}")
    if look["problem"]:
        print(f"  first difference: {look['problem']}")
    for s, d in checks.data_quality(runner.data, cls.interval).items():
        print(f"Data {s}: {d['bars']} bars, {d['start'][:10]} to {d['end'][:10]}, "
              f"longest gap {d['longest_gap_days']} days" + "".join(f"\n  issue: {i}" for i in d["issues"]))
    if not look["passed"]:
        raise SystemExit(1)


def format_validation(v: dict) -> str:
    lines = []
    wf = v.get("walkforward")
    if wf:
        lines += [f"  Walk-forward ({wf['mode']}, {len(wf['windows'])} windows of {wf['oos_days']} days, "
                  f"{wf['is_days']} in-sample)",
                  f"    out-of-sample: {_pct(wf['oos_annual_return'])} a year, Sharpe {_num(wf['oos_sharpe'])}; "
                  f"in-sample average: {_pct(wf['is_annual_return_mean'])}, Sharpe {_num(wf['is_sharpe_mean'])}",
                  f"    efficiency {_num(wf['wfe_return'])} (return), {_num(wf['wfe_sharpe'])} (Sharpe); "
                  f"{_pct(wf['windows_profitable'])} of windows profitable"]
    io = v.get("in_out_of_sample")
    if io:
        lines.append(f"  In/out-of-sample split at {io['split_date']}: Sharpe {_num(io['is_sharpe'])} "
                     f"-> {_num(io['oos_sharpe'])} with {io['params']}")
    s = v.get("sensitivity")
    if s:
        lines.append(f"  Sensitivity: best {s['best_params']} (Sharpe {_num(s['best'])}), neighbours at "
                     f"{_pct(s['plateau_ratio'])} of best, {_pct(s['share_of_grid_positive'])} of grid positive")
    mc = v.get("montecarlo")
    if mc:
        b = mc["bootstrap"]
        lines += [f"  Monte Carlo ({b['paths']} resampled histories, blocks of ~{b['mean_block_days']:.0f} days)",
                  f"    total return 5th/50th/95th percentile: {_pct(b['total_return']['p5'])} / "
                  f"{_pct(b['total_return']['p50'])} / {_pct(b['total_return']['p95'])}",
                  f"    max drawdown median {_pct(b['max_drawdown']['p50'])}, 1-in-20 {_pct(b['max_drawdown']['p95'])} "
                  f"(backtest {_pct(mc['backtest_max_drawdown'])}); chance of loss {_pct(b['probability_of_loss'])}"]
        if "reshuffle" in mc:
            lines.append(f"    reshuffled trade order: 1-in-20 drawdown {_pct(mc['reshuffle']['max_drawdown']['p95'])}; "
                         f"skipping 10% of trades: 5th percentile return {_pct(mc['skip']['total_return']['p5'])}")
    sy = v.get("synthetic")
    if sy:
        lines.append(f"  Synthetic price histories ({sy['paths']} re-runs): total return 5th/50th/95th "
                     f"{_pct(sy['total_return']['p5'])} / {_pct(sy['total_return']['p50'])} / "
                     f"{_pct(sy['total_return']['p95'])}; chance of loss {_pct(sy['probability_of_loss'])}")
    k = v.get("kelly")
    if k and k.get("edge"):
        lines.append(f"  Kelly: growth-optimal size {_num(k['point_estimate'])}x the backtested size "
                     f"(resampled range {_num(k['bootstrap']['p5'])}x to {_num(k['bootstrap']['p95'])}x); "
                     f"suggested {_num(k['recommended'])}x"
                     + (" (limited by the leverage cap)" if k.get("leverage_cap_multiple") is not None
                        and k["recommended"] >= k["leverage_cap_multiple"] - 1e-9 else ""))
    o = v.get("overfitting")
    if o:
        lines.append(f"  Probability true Sharpe > 0: {_pct(o['probabilistic_sharpe'])}")
        if "deflated_sharpe_effective_trials" in o:
            d, raw = o["deflated_sharpe_effective_trials"], o["deflated_sharpe_raw_trials"]
            lines.append(f"    after {raw['n_trials']:.0f} variants tried (~{d['n_trials']:.1f} independent): "
                         f"{_pct(d['probability'])} (raw count: {_pct(raw['probability'])})")
        if "pbo" in o:
            lines.append(f"    probability of backtest overfitting: {_pct(o['pbo']['pbo'])}")
        if "spa" in o:
            lines.append(f"    best of grid versus holding cash, allowing for selection: p = {_num(o['spa']['p_value'])}")
        if "p_value" in o["permutation"]:
            lines.append(f"    timing permutation p = {_num(o['permutation']['p_value'])}"
                         + (f"; random-entry p = {_num(o['random_entry']['p_value'])}" if "p_value" in o["random_entry"] else ""))
    rg = v.get("regimes")
    if rg:
        parts = [f"{r['regime']} {_pct(r['total_return'])} total ({_pct(r['share_of_time'])} of time)"
                 for r in rg["trend"] if r["regime"] != "unknown"]
        lines.append("  Regimes (benchmark trend): " + "; ".join(parts))
    cs = v.get("costs")
    if cs:
        lv = "; ".join(f"{row['cost_multiplier']:g}x {_pct(row['total_return'])}" for row in cs["levels"])
        lines.append(f"  Cost stress, total return: {lv}; fills delayed one bar {_pct(cs['delayed_fill']['total_return'])}")
        if cs.get("break_even_multiplier"):
            lines.append(f"    break-even at about {_num(cs['break_even_multiplier'], 1)}x assumed costs "
                         f"({_num(cs['break_even_cost_bps_per_fill'], 1)} basis points per fill)")
    op = v.get("option_pricing")
    if op:
        lines.append("  Option-pricing sensitivity, total return: "
                     + "; ".join(f"{c['case']} {_pct(c['total_return'])}" for c in op["cases"]))
    lines.append("")
    if v["flags"]:
        lines.append("  Flags")
        lines += [f"    [{f['severity']}] {f['message']}" for f in v["flags"]]
    else:
        lines.append("  No flags raised.")
    return "\n".join(lines)


def cmd_validate(args):
    from backtester.analysis.findings import ALL_TESTS, CHEAP_TESTS, to_jsonable, validate
    cls, params, runner, benchmark, bench_symbol = _setup(args)
    tests = args.tests.split(",") if args.tests else list(CHEAP_TESTS)
    if args.synthetic and "synthetic" not in tests:
        tests.append("synthetic")
    result = runner.run({**cls.params, **params})
    cache = Cache(args.cache)
    regime_close = None
    if cache.has(bench_symbol, "1d"):
        d = cache.load(bench_symbol, "1d", end=args.end)
        regime_close = d["close"] * d["adj_factor"]
    elif benchmark is not None:
        regime_close = benchmark
    v = validate(runner, params, tests, benchmark_close=_from(benchmark, result.equity.index[0]),
                 regime_close=regime_close,
                 ledger=Path(args.strategy).with_suffix(".trials.jsonl"), n_paths=args.paths,
                 synthetic_paths=args.synthetic or 200, seed=args.seed, risk_free_rate=args.risk_free,
                 wf_mode=args.walk_forward)
    out = _save_run(args, result, v["metrics"], bench_symbol, benchmark)
    (out / "validation.json").write_text(json.dumps(to_jsonable(v), indent=2, default=str))
    print(format_summary(result.meta, v["metrics"]))
    print()
    print(format_validation(v))
    print(f"\n  Saved to {out}")


def cmd_compare_ibkr(args):
    import numpy as np
    cache = Cache(args.cache)
    ib, interval = parse_ibkr_history(Path(args.file))
    ref = cache.load(args.symbol, interval).reindex(ib.index)
    matched = ref["close"].notna()
    if not matched.any():
        raise SystemExit("no overlapping bars between the IBKR sample and the cache")
    diff = (ib.loc[matched, ["open", "high", "low", "close"]] / ref.loc[matched, ["open", "high", "low", "close"]] - 1).abs()
    report = {"bars_compared": int(matched.sum()), "bars_in_sample": int(len(ib)),
              "start": ib.index[0].isoformat(), "end": ib.index[-1].isoformat(),
              "max_relative_difference": {k: float(v) for k, v in diff.max().items()},
              "volume_ratio_ibkr_to_cache": float(np.nanmedian(ib.loc[matched, "volume"] / ref.loc[matched, "volume"]))}
    meta_path = cache._path(args.symbol, interval).with_suffix(".json")
    meta = cache.meta(args.symbol, interval)
    meta["ibkr_check"] = report
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"{args.symbol.upper()} {interval}: {report['bars_compared']} of {report['bars_in_sample']} bars compared "
          f"against {meta.get('source', '?')}")
    for k, val in report["max_relative_difference"].items():
        print(f"  largest {k} difference: {val * 100:.4f}%")
    print(f"  IBKR volume is {report['volume_ratio_ibkr_to_cache']:.0%} of the cached volume (median)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="bt", description="Strategy backtester")
    p.add_argument("--cache", default="data/cache", help="bar cache folder")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("data", help="list cached bars").set_defaults(func=cmd_data)

    s = sub.add_parser("ingest-ibkr", help="load Interactive Brokers price-history JSON files")
    s.add_argument("symbol")
    s.add_argument("files", nargs="+")
    s.add_argument("--adjusted", default="unknown")
    s.set_defaults(func=cmd_ingest_ibkr)

    s = sub.add_parser("fetch-yahoo", help="download bars from Yahoo Finance")
    s.add_argument("symbol")
    s.add_argument("--interval", default="1d")
    s.add_argument("--start")
    s.add_argument("--end")
    s.set_defaults(func=cmd_fetch_yahoo)

    s = sub.add_parser("fetch-rates", help="download the Treasury bill yield used for cash and margin interest")
    s.add_argument("--start", default="1990-01-01")
    s.set_defaults(func=cmd_fetch_rates)

    s = sub.add_parser("calibrate-options", help="fit the volatility surface to a snapshot of option quotes")
    s.add_argument("file")
    s.add_argument("--config", default="config/vol_surface.toml")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_calibrate_options)

    s = sub.add_parser("import-csv", help="load bars from a CSV file")
    s.add_argument("symbol")
    s.add_argument("interval")
    s.add_argument("file")
    s.add_argument("--source", default="csv")
    s.add_argument("--adjusted", default="unknown")
    s.set_defaults(func=cmd_import_csv)

    def run_options(s):
        s.add_argument("strategy", help="path to a strategy .py file")
        s.add_argument("--start")
        s.add_argument("--end")
        s.add_argument("--cash", type=float, default=100_000)
        s.add_argument("--param", action="append", metavar="NAME=VALUE")
        s.add_argument("--costs", default="config/costs.toml")
        s.add_argument("--cost-multiplier", type=float, default=1.0)
        s.add_argument("--fill", choices=["next_open", "close"], default="next_open")
        s.add_argument("--max-leverage", type=float, default=1.0)
        s.add_argument("--no-short", action="store_true")
        s.add_argument("--no-cash-interest", action="store_true")
        s.add_argument("--raw-prices", action="store_true", help="ignore dividend adjustment")
        s.add_argument("--benchmark", help="symbol for buy-and-hold comparison (default: first in universe)")
        s.add_argument("--risk-free", type=float, default=0.0, help="annual risk-free rate, e.g. 0.04")
        s.add_argument("--backend", default="native")
        s.add_argument("--out", default="runs")

    s = sub.add_parser("run", help="run a backtest")
    run_options(s)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("check", help="look-ahead and data checks")
    run_options(s)
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("optimize", help="try every combination in the strategy's parameter grid")
    run_options(s)
    s.set_defaults(func=cmd_optimize)

    s = sub.add_parser("validate", help="run a backtest plus the robustness tests")
    run_options(s)
    s.add_argument("--tests", help="comma-separated: checks,optimize,walkforward,sensitivity,"
                                   "montecarlo,kelly,overfitting,regimes,costs,synthetic")
    s.add_argument("--paths", type=int, default=5000, help="Monte Carlo paths")
    s.add_argument("--synthetic", type=int, default=0, metavar="N",
                   help="also re-run on N synthetic price histories (slow)")
    s.add_argument("--walk-forward", choices=["rolling", "anchored"], default="rolling")
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("compare-ibkr", help="compare an IBKR price-history sample with cached bars")
    s.add_argument("symbol")
    s.add_argument("file")
    s.set_defaults(func=cmd_compare_ibkr)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
