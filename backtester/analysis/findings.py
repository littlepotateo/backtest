"""Run the validation tests and turn their numbers into plain-language flags.

`validate` returns everything as one dictionary (saved as validation.json). `flags`
lists what a reader should worry about. Flags are observations with a severity, not
pass/fail gates.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from backtester.analysis import checks, coststress, kelly, montecarlo, overfitting, regimes
from backtester.analysis.metrics import TRADING_DAYS, compute_metrics
from backtester.analysis.optimize import daily_returns, grid_search, params_key, sharpe, trial_count
from backtester.analysis.walkforward import in_out_of_sample, sensitivity, walk_forward
from backtester.engine.backend import Runner

CHEAP_TESTS = ["checks", "optimize", "walkforward", "sensitivity", "montecarlo", "kelly",
               "overfitting", "regimes", "costs"]
ALL_TESTS = CHEAP_TESTS + ["synthetic"]


def to_jsonable(x):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    if isinstance(x, pd.DataFrame):
        return to_jsonable(x.reset_index().to_dict(orient="records")) if x.index.name or \
            not isinstance(x.index, pd.RangeIndex) else to_jsonable(x.to_dict(orient="records"))
    if isinstance(x, pd.Series):
        return {"index": [str(i) for i in x.index], "values": to_jsonable(x.to_list())}
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return to_jsonable(x.tolist())
    if isinstance(x, (pd.Timestamp,)):
        return x.isoformat()
    return x


def validate(runner: Runner, params: dict | None = None, tests: list[str] | None = None, *,
             benchmark_close: pd.Series | None = None, regime_close: pd.Series | None = None, ledger: str | Path | None = None,
             n_paths: int = 5000, synthetic_paths: int = 200, seed: int = 0,
             risk_free_rate: float = 0.0, wf_mode: str = "rolling") -> dict:
    tests = list(tests or CHEAP_TESTS)
    unknown = set(tests) - set(ALL_TESTS)
    if unknown:
        raise ValueError(f"unknown tests: {sorted(unknown)}")
    cls = runner.strategy_cls
    params = {**cls.params, **(params or {})}
    base = runner.run(params)
    r = daily_returns(base)
    out: dict = {"params": params, "tests_run": tests, "skipped": {},
                 "metrics": compute_metrics(base, risk_free_rate, benchmark_close)}
    grid = cls.grid()
    has_grid = len(grid) > 1

    if "checks" in tests:
        out["checks"] = {"lookahead": checks.lookahead_test(runner, params),
                         "data": checks.data_quality(runner.data, cls.interval),
                         "trades": checks.trade_checks(base)}

    grid_result = None
    if has_grid and {"optimize", "walkforward", "sensitivity", "overfitting"} & set(tests):
        if not any(params_key(g) == params_key(params) for g in grid):
            grid = grid + [params]
        grid_result = grid_search(runner, grid, ledger)
        out["optimize"] = {"configurations": len(grid), "table": grid_result["table"],
                           "best_params": grid_result["configs"][grid_result["best"]]}
    elif not has_grid:
        for t in ("optimize", "walkforward", "sensitivity"):
            if t in tests:
                out["skipped"][t] = "the strategy declares no parameter grid"

    if grid_result is not None and "walkforward" in tests:
        try:
            wf = walk_forward(runner, grid_result, mode=wf_mode)
            wf.pop("oos_equity")
            out["walkforward"] = wf
            out["in_out_of_sample"] = in_out_of_sample(runner, grid_result)
        except ValueError as e:
            out["skipped"]["walkforward"] = str(e)
    if grid_result is not None and "sensitivity" in tests:
        out["sensitivity"] = sensitivity(cls, grid_result)

    if "montecarlo" in tests:
        out["montecarlo"] = montecarlo.monte_carlo(base, n_paths, seed)
    if "synthetic" in tests:
        try:
            out["synthetic"] = montecarlo.synthetic_reruns(runner, params, synthetic_paths, seed)
        except ValueError as e:
            out["skipped"]["synthetic"] = str(e)
    if "kelly" in tests:
        out["kelly"] = kelly.kelly_analysis(base, risk_free_rate, seed=seed,
                                            max_leverage=runner.config.max_leverage)

    if "overfitting" in tests:
        x = r.to_numpy() - risk_free_rate / TRADING_DAYS
        o: dict = {"probabilistic_sharpe": overfitting.probabilistic_sharpe(x),
                   "min_track_record_days": overfitting.min_track_record_length(x),
                   "observations": int(len(r))}
        if grid_result is not None:
            m = grid_result["returns"]
            per_period = m.mean() / m.std(ddof=1)
            variance = float(per_period.replace([np.inf, -np.inf], np.nan).var(ddof=1))
            recorded = trial_count(ledger) if ledger else 0
            n_raw = max(recorded, m.shape[1])
            n_eff = overfitting.effective_trials(m) * (n_raw / m.shape[1])
            o["trials_recorded"] = n_raw
            o["deflated_sharpe_raw_trials"] = overfitting.deflated_sharpe(x, n_raw, variance)
            o["deflated_sharpe_effective_trials"] = overfitting.deflated_sharpe(x, n_eff, variance)
            if m.shape[1] >= 10:
                try:
                    o["pbo"] = overfitting.pbo_cscv(m)
                except ValueError as e:
                    out["skipped"]["pbo"] = str(e)
            else:
                out["skipped"]["pbo"] = f"needs at least 10 configurations (have {m.shape[1]})"
            o["spa"] = overfitting.spa_test(m, seed=seed)
        o["permutation"] = overfitting.permutation_test(base, runner.data, seed=seed)
        if (out["metrics"].get("time_in_market") or 0) > 0.95:
            o["random_entry"] = {"skipped": "the strategy is almost always invested, so entry timing is not what it relies on"}
        else:
            o["random_entry"] = overfitting.random_entry_test(base, runner.data, seed=seed)
        o["not_run"] = "Price-path permutation (Masters) is not implemented: its recipe is unverified."
        out["overfitting"] = o

    if "regimes" in tests:
        series = regime_close if regime_close is not None else benchmark_close
        if series is None:
            out["skipped"]["regimes"] = "no benchmark price series available"
        else:
            rb = regimes.regime_breakdown(base, series)
            if rb["labelled_share"] < 0.5:
                out["skipped"]["regimes"] = ("benchmark history is too short to label market regimes "
                                             "(needs about a year of daily prices before the test period)")
            else:
                out["regimes"] = rb
    if "costs" in tests:
        out["costs"] = coststress.cost_stress(runner, params)

    if cls.options_on:
        out["option_pricing"] = option_pricing_sensitivity(runner, params, base)
        for t in ("permutation", "random_entry"):
            if "overfitting" in out:
                out["overfitting"][t] = {"skipped": "not meaningful for option positions"}

    out["flags"] = flags(out)
    return out


def option_pricing_sensitivity(runner: Runner, params: dict, base) -> dict:
    """Option prices are modelled. Re-run with the volatility level and skew moved, to
    show how much the result owes to those assumptions."""
    start = runner.config.initial_cash
    rows = [{"case": "as configured", "total_return": float(base.equity.iloc[-1] / start - 1),
             "sharpe": sharpe(daily_returns(base))}]
    for name, scale in (("volatility level -15%", (0.85, 1.0)), ("volatility level +10%", (1.10, 1.0)),
                        ("skew 25% flatter", (1.0, 0.75)), ("skew 25% steeper", (1.0, 1.25))):
        res = runner.run(params, option_scale=scale)
        rows.append({"case": name, "total_return": float(res.equity.iloc[-1] / start - 1),
                     "sharpe": sharpe(daily_returns(res))})
    returns = [r["total_return"] for r in rows]
    return {"cases": rows, "lowest": min(returns), "highest": max(returns),
            "sign_changes": min(returns) < 0 < max(returns),
            "note": "Modelled prices, not quotes. For SPY, a level fitted to one day of IBKR quotes "
                    "and a level fitted to the Cboe PutWrite index differ by about 16%."}


def _flag(severity: str, test: str, message: str) -> dict:
    return {"severity": severity, "test": test, "message": message}


def flags(v: dict) -> list[dict]:
    """Things a reader should know before trusting the result, most serious first."""
    f = []
    m = v.get("metrics", {})
    n_trades = m.get("trades", 0)
    if n_trades < 10:
        f.append(_flag("high", "trades", f"Only {n_trades} closed trades: far too few to draw conclusions."))
    elif n_trades < 30:
        f.append(_flag("medium", "trades", f"Only {n_trades} closed trades: statistics are unreliable."))
    if (m.get("total_return") or 0) <= 0:
        f.append(_flag("high", "performance", "The strategy lost money over the test period."))
    if m.get("benchmark_total_return") is not None and m["total_return"] < m["benchmark_total_return"]:
        f.append(_flag("info", "performance",
                       f"Total return {m['total_return']:.1%} is below the benchmark's {m['benchmark_total_return']:.1%}."))

    c = v.get("checks")
    if c:
        if not c["lookahead"]["passed"]:
            f.append(_flag("high", "look-ahead", "Orders changed when future data was removed: "
                                                 "the strategy uses information it could not have had."))
        if c["lookahead"]["same_bar_fills"]:
            f.append(_flag("medium", "look-ahead", "Orders fill on the same bar that produced the signal."))
        for s, d in c["data"].items():
            for issue in d["issues"]:
                f.append(_flag("info" if "standard deviations" in issue else "medium", "data", f"{s}: {issue}."))
        t = c["trades"]
        share = t.get("top_5pct_share_of_gross_profit")
        if share is not None and share > 0.5 and t["trades"] >= 10:
            f.append(_flag("medium", "trades", f"The top {t['top_5pct_trades']} trade(s) produced {share:.0%} of gross profit."))
        if t.get("net_profit_from_trades", 0) > 0 and t.get("profit_without_best_trade", 0) <= 0:
            f.append(_flag("high", "trades", "Without its single best trade the strategy does not make money."))

    wf = v.get("walkforward")
    if wf:
        if wf["oos_sharpe"] is not None and np.isfinite(wf["oos_sharpe"]) and wf["is_sharpe_mean"] > 0:
            ratio = wf["oos_sharpe"] / wf["is_sharpe_mean"]
            if ratio < 0.5:
                f.append(_flag("high" if ratio < 0.25 else "medium", "walk-forward",
                               f"Out-of-sample Sharpe is {ratio:.0%} of in-sample "
                               f"({wf['oos_sharpe']:.2f} vs {wf['is_sharpe_mean']:.2f}): likely overfitted."))
        if wf["windows_profitable"] < 0.5:
            f.append(_flag("medium", "walk-forward",
                           f"Only {wf['windows_profitable']:.0%} of out-of-sample windows were profitable."))
        if wf["windows_with_too_few_trades"]:
            f.append(_flag("info", "walk-forward",
                           f"{wf['windows_with_too_few_trades']} of {len(wf['windows'])} windows had fewer than 10 trades."))
        unstable = [k for k, s in wf["param_instability"].items() if s > 0.3]
        if unstable:
            f.append(_flag("medium", "walk-forward",
                           f"The chosen value of {', '.join(unstable)} jumps around between windows."))
    s = v.get("sensitivity")
    if s and s.get("plateau_ratio") is not None and s["plateau_ratio"] < 0.5:
        f.append(_flag("medium", "sensitivity",
                       f"Neighbouring parameter values score {s['plateau_ratio']:.0%} of the best: a narrow peak."))

    mc = v.get("montecarlo")
    if mc:
        b = mc["bootstrap"]
        if b["probability_of_loss"] > 0.2:
            f.append(_flag("medium", "monte-carlo",
                           f"{b['probability_of_loss']:.0%} of resampled histories lose money."))
        if b["max_drawdown"]["p95"] < 1.5 * mc["backtest_max_drawdown"] - 1e-9:
            f.append(_flag("info", "monte-carlo",
                           f"A 1-in-20 resampled history has a drawdown of {b['max_drawdown']['p95']:.0%}, "
                           f"against {mc['backtest_max_drawdown']:.0%} in the backtest."))
        if b["risk_of_ruin"] > 0.05:
            f.append(_flag("high", "monte-carlo",
                           f"{b['risk_of_ruin']:.0%} of resampled histories fall {abs(b['ruin_threshold']):.0%} from a peak."))
    k = v.get("kelly")
    if k:
        if not k.get("edge"):
            f.append(_flag("high", "kelly", "No positive edge to size."))
        elif k["point_estimate"] < 1:
            f.append(_flag("medium", "kelly",
                           f"Growth-optimal size is {k['point_estimate']:.2f}x the backtested size: "
                           "the backtest was already over-betting."))
        if k.get("probability_no_edge", 0) > 0.1:
            f.append(_flag("medium", "kelly",
                           f"{k['probability_no_edge']:.0%} of resampled histories show no edge at all."))

    o = v.get("overfitting")
    if o:
        psr = o.get("probabilistic_sharpe")
        if psr is not None and np.isfinite(psr) and psr < 0.95:
            f.append(_flag("medium" if psr >= 0.8 else "high", "significance",
                           f"{psr:.0%} probability that the true Sharpe ratio is above zero (95% is the usual bar)."))
        d = o.get("deflated_sharpe_effective_trials")
        if d and np.isfinite(d["probability"]) and d["probability"] < 0.95:
            f.append(_flag("medium" if d["probability"] >= 0.5 else "high", "significance",
                           f"After allowing for about {d['n_trials']:.0f} independent variants tried, the probability "
                           f"of a real edge is {d['probability']:.0%}."))
        if o.get("pbo") and o["pbo"]["pbo"] > 0.4:
            f.append(_flag("high" if o["pbo"]["pbo"] > 0.6 else "medium", "overfitting",
                           f"Probability of backtest overfitting is {o['pbo']['pbo']:.0%}."))
        if o.get("spa") and o["spa"]["p_value"] > 0.10:
            f.append(_flag("medium", "significance",
                           f"The best parameter set is not clearly better than holding cash once "
                           f"selection is accounted for (p = {o['spa']['p_value']:.2f})."))
        p = o.get("permutation")
        if p and "p_value" in p and p["p_value"] > 0.10:
            f.append(_flag("medium", "significance",
                           f"Timing is not distinguishable from chance (permutation p = {p['p_value']:.2f}); "
                           "returns may come from market exposure alone."))
        re = o.get("random_entry")
        if re and "p_value" in re and re["p_value"] > 0.10:
            f.append(_flag("info", "significance",
                           f"Random entries with the same holding periods do about as well (p = {re['p_value']:.2f})."))

    rg = v.get("regimes")
    if rg:
        for msg in rg["missing"]:
            f.append(_flag("medium", "regimes", f"Untested conditions: {msg}."))
        for row in rg["trend"]:
            if row["share_of_profit"] is not None and row["share_of_profit"] > 0.8 and row["share_of_time"] < 0.8 \
                    and row["regime"] != "unknown":
                f.append(_flag("info", "regimes",
                               f"{row['share_of_profit']:.0%} of profit came from {row['regime']} markets "
                               f"({row['share_of_time']:.0%} of the time)."))
    cs = v.get("costs")
    if cs:
        levels = {row["cost_multiplier"]: row for row in cs["levels"]}
        if 1.0 in levels and 2.0 in levels and levels[1.0]["profit"] > 0:
            if levels[2.0]["profit"] <= 0:
                f.append(_flag("high", "costs", "Profit disappears when trading costs are doubled."))
            elif levels[2.0]["profit"] < 0.5 * levels[1.0]["profit"]:
                f.append(_flag("medium", "costs", "Doubling trading costs removes more than half the profit."))
        d = cs["delayed_fill"]
        if 1.0 in levels and levels[1.0]["profit"] > 0 and d["profit"] < 0.5 * levels[1.0]["profit"]:
            f.append(_flag("medium", "costs",
                           "Delaying every fill by one bar removes more than half the profit: "
                           "the result depends on fast execution."))
    op = v.get("option_pricing")
    if op:
        f.append(_flag("high" if op["sign_changes"] else "medium", "option pricing",
                       f"Option prices are modelled, not real quotes. Moving the volatility assumptions "
                       f"changes the total return from {op['lowest']:.0%} to {op['highest']:.0%}"
                       + ("; the result changes sign." if op["sign_changes"] else ".")))
    for name, why in v.get("skipped", {}).items():
        f.append(_flag("info", name, f"Not run: {why}."))
    order = {"high": 0, "medium": 1, "info": 2}
    return sorted(f, key=lambda x: order[x["severity"]])
