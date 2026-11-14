"""How much of the edge survives trading frictions?
See docs/research/regimes-costs-lookahead.md."""

from __future__ import annotations

from backtester.analysis.optimize import daily_returns, sharpe
from backtester.engine.backend import Runner


def cost_stress(runner: Runner, params: dict | None = None,
                multipliers: tuple = (0.0, 1.0, 2.0, 3.0)) -> dict:
    """Re-run with costs scaled, and once with every fill delayed by one extra bar."""
    base_costs = runner.config.costs
    start_cash = runner.config.initial_cash
    rows, pnl, traded, paid = [], {}, 0.0, 0.0
    for m in multipliers:
        res = runner.run(params, costs=base_costs.scaled(base_costs.multiplier * m))
        profit = float(res.equity.iloc[-1] - start_cash)
        pnl[m] = profit
        costs = float(res.fills["commission"].sum() + res.fills["slippage_cost"].sum())
        if m == 1.0:
            traded = float((res.fills["qty"].abs() * res.fills["price"]).sum())
            paid = costs
        rows.append({"cost_multiplier": m, "profit": profit, "total_return": profit / start_cash,
                     "sharpe": sharpe(daily_returns(res)), "costs_paid": costs,
                     "trades": int(len(res.trades))})
    delayed = runner.run(params, fill_delay_bars=runner.config.fill_delay_bars + 1)
    d_profit = float(delayed.equity.iloc[-1] - start_cash)

    out = {"levels": rows,
           "delayed_fill": {"extra_bars": 1, "profit": d_profit, "total_return": d_profit / start_cash,
                            "sharpe": sharpe(daily_returns(delayed))},
           "assumed_cost_bps_per_fill": paid / traded * 1e4 if traded else None}
    if 0.0 in pnl and 1.0 in pnl and pnl[0.0] > pnl[1.0]:
        # linear estimate: each unit of the multiplier costs (profit at 0x - profit at 1x)
        be = pnl[0.0] / (pnl[0.0] - pnl[1.0])
        out["break_even_multiplier"] = be
        out["break_even_cost_bps_per_fill"] = be * out["assumed_cost_bps_per_fill"] if traded else None
    else:
        out["break_even_multiplier"] = None
    return out
