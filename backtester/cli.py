"""`bt` command line."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backtester.analysis.metrics import compute_metrics
from backtester.data.cache import Cache, from_csv
from backtester.data.ibkr import parse_ibkr_history
from backtester.engine.backend import load_data, run_backtest
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


def cmd_import_csv(args):
    saved = Cache(args.cache).save(args.symbol, args.interval, from_csv(args.file),
                                   source=args.source, adjusted=args.adjusted)
    print(f"{args.symbol.upper()} {args.interval}: {len(saved)} bars cached")


def cmd_run(args):
    cls = load_strategy_class(args.strategy)
    strategy = cls(**_parse_params(args.param))
    costs = CostModel.from_toml(args.costs).scaled(args.cost_multiplier)
    config = RunConfig(start=args.start, end=args.end, initial_cash=args.cash, costs=costs,
                       fill=args.fill, max_leverage=args.max_leverage,
                       allow_short=not args.no_short, use_adjusted=not args.raw_prices)
    cache = Cache(args.cache)
    result = run_backtest(strategy, config, cache=cache, backend=args.backend)
    bench_symbol = args.benchmark or strategy.universe[0]
    benchmark = None
    if cache.has(bench_symbol, strategy.interval):
        b = cache.load(bench_symbol, strategy.interval, end=args.end)
        benchmark = (b["close"] * b["adj_factor"]) if config.use_adjusted else b["close"]
        benchmark = benchmark[benchmark.index >= result.equity.index[0]]
    metrics = compute_metrics(result, args.risk_free, benchmark)
    result.meta["benchmark"] = bench_symbol if benchmark is not None else None
    result.meta["strategy_file"] = str(args.strategy)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = result.save(Path(args.out) / f"{stamp}-{strategy.name}")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(format_summary(result.meta, metrics))
    print(f"\n  Saved to {out}")


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

    s = sub.add_parser("import-csv", help="load bars from a CSV file")
    s.add_argument("symbol")
    s.add_argument("interval")
    s.add_argument("file")
    s.add_argument("--source", default="csv")
    s.add_argument("--adjusted", default="unknown")
    s.set_defaults(func=cmd_import_csv)

    s = sub.add_parser("run", help="run a backtest")
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
    s.add_argument("--raw-prices", action="store_true", help="ignore dividend adjustment")
    s.add_argument("--benchmark", help="symbol for buy-and-hold comparison (default: first in universe)")
    s.add_argument("--risk-free", type=float, default=0.0, help="annual risk-free rate, e.g. 0.04")
    s.add_argument("--backend", default="native")
    s.add_argument("--out", default="runs")
    s.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
