"""Turn a validation result into a plain-language explanation (markdown).

Works from the dictionary `bt validate` saves (validation.json, after JSON round-trip),
so it can run on a saved run without re-running anything. Every number quoted comes from
that dictionary; the wording is rule-based and deterministic. A fuller narrative written
by Claude Code goes in narrative.md beside it.
"""

from __future__ import annotations


def pct(x, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:,.{digits}f}%"


def num(x, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}"


def _year(ts: str | None) -> str:
    return (ts or "")[:10]


def _by_severity(flags: list[dict], level: str) -> list[dict]:
    return [f for f in flags if f["severity"] == level]


RISK_TESTS = {"monte-carlo"}      # about how much could be lost, not whether there is an edge


def trust_level(flags: list[dict]) -> tuple[str, str]:
    """How well the evidence supports the strategy. Risk-of-loss flags are reported
    separately: a strategy can have a real edge and still be too risky for someone."""
    evidence = [f for f in flags if f["test"] not in RISK_TESTS]
    high, medium = len(_by_severity(evidence, "high")), len(_by_severity(evidence, "medium"))
    if high:
        return ("Unproven", f"{high} serious concern{'s' if high != 1 else ''} below mean this result should not be relied on yet.")
    if medium >= 2:
        return ("Tentative", f"{medium} moderate concerns below; the result is suggestive, not established.")
    if medium == 1:
        return ("Reasonable, with one caveat", "One moderate concern below; otherwise the tests found no serious problem.")
    return ("No serious concerns raised", "These tests found no serious problem, but they cannot prove a strategy will work.")


def risk_note(flags: list[dict]) -> str | None:
    risk = [f for f in flags if f["test"] in RISK_TESTS and f["severity"] in ("high", "medium")]
    if not risk:
        return None
    return "**Risk to plan for** (separate from the evidence question): " + " ".join(f["message"] for f in risk)


def summary(v: dict, meta: dict | None) -> list[str]:
    m = v["metrics"]
    meta = meta or {}
    universe = ", ".join(meta.get("universe", [])) or "the strategy's universe"
    lines = [f"Over {_year(m['start'])} to {_year(m['end'])} ({m['trading_days']:,} trading days) on {universe}, "
             f"the strategy returned **{pct(m['total_return'])}** in total ({pct(m['cagr'])} a year), "
             f"with a worst peak-to-trough fall of **{pct(m['max_drawdown'])}** and a Sharpe ratio of {num(m['sharpe'])}."]
    if m.get("benchmark_total_return") is not None:
        b = m["benchmark_total_return"]
        rel = "ahead of" if m["total_return"] > b else "behind"
        lines.append(f"Simply holding the benchmark returned {pct(b)} with a worst fall of "
                     f"{pct(m.get('benchmark_max_drawdown'))}, so the strategy finished {rel} it "
                     f"in total return" + (f" but with a shallower worst fall." if (m["max_drawdown"] or -1) > (m.get("benchmark_max_drawdown") or -1) else "."))
    return lines


def what_drove(v: dict, meta: dict | None) -> list[str]:
    m, out = v["metrics"], []
    if m.get("time_in_market") is not None:
        out.append(f"It was invested {pct(m['time_in_market'], 0)} of the time, with {m['trades']:,} closed trades.")
    if m.get("beta") is not None:
        out.append(f"Its returns moved {num(m['beta'])}x as much as the benchmark's (beta) and left "
                   f"{pct(m['alpha_annual'])} a year unexplained by that exposure (alpha).")
    rg = v.get("regimes")
    if rg:
        trend = {r["regime"]: r for r in rg["trend"] if r["regime"] != "unknown"}
        if "bull" in trend and "bear" in trend:
            out.append(f"In rising markets (the benchmark above its 200-day average, {pct(trend['bull']['share_of_time'], 0)} of the time) "
                       f"it returned {pct(trend['bull']['total_return'])}; in falling markets "
                       f"({pct(trend['bear']['share_of_time'], 0)} of the time), {pct(trend['bear']['total_return'])}.")
        for msg in rg.get("missing", []):
            out.append(f"The history contains {msg[3:]}, so the strategy has not been tested in that condition.")
    interest = (meta or {}).get("interest")
    if interest and (interest["earned"] or interest["paid"]):
        out.append(f"Interest on idle cash added ${interest['earned']:,.0f} and margin interest cost ${interest['paid']:,.0f}.")
    if (meta or {}).get("dividends_received"):
        out.append(f"Dividends received in cash: ${meta['dividends_received']:,.0f}.")
    c = v.get("costs")
    if c:
        levels = {r["cost_multiplier"]: r for r in c["levels"]}
        if 0.0 in levels and 1.0 in levels:
            gap = (levels[0.0]["total_return"] - levels[1.0]["total_return"]) * 100
            out.append(f"Trading costs reduced total return by {gap:,.1f} percentage points "
                       f"(${m['total_commission'] + m['total_slippage']:,.0f} in commission and slippage).")
    return out


def tests(v: dict) -> list[str]:
    out = []
    ck = v.get("checks")
    if ck:
        lk = ck["lookahead"]
        out.append("**Look-ahead check:** " + (
            "passed. Cutting the data off at three dates left every earlier order unchanged, so the strategy did not use "
            "information from the future that the engine supplies." if lk["passed"] else
            "**failed.** Orders changed when later data was removed, so the strategy used information it could not have had. "
            "Nothing below can be trusted until this is fixed."))
    wf = v.get("walkforward")
    if wf:
        out.append(f"**Walk-forward (re-tuning on the past, trading the future):** across {len(wf['windows'])} windows the "
                   f"out-of-sample result was {pct(wf['oos_annual_return'])} a year (Sharpe {num(wf['oos_sharpe'])}) against "
                   f"{pct(wf['is_annual_return_mean'])} (Sharpe {num(wf['is_sharpe_mean'])}) in-sample, and "
                   f"{pct(wf['windows_profitable'], 0)} of windows were profitable. A large drop out-of-sample points to overfitting.")
    io = v.get("in_out_of_sample")
    if io:
        out.append(f"**One-split check:** choosing parameters on the first 70% of the history and testing on the rest "
                   f"changed the Sharpe ratio from {num(io['is_sharpe'])} to {num(io['oos_sharpe'])}.")
    se = v.get("sensitivity")
    if se and se.get("plateau_ratio") is not None:
        out.append(f"**Parameter sensitivity:** neighbouring parameter values scored {pct(se['plateau_ratio'], 0)} of the best, "
                   f"and {pct(se['share_of_grid_positive'], 0)} of all tried combinations were profitable. "
                   + ("A broad plateau is reassuring." if se["plateau_ratio"] >= 0.8 else "A narrow peak suggests the best value is partly luck."))
    mc = v.get("montecarlo")
    if mc:
        b = mc["bootstrap"]
        out.append(f"**Monte Carlo (resampling the daily returns in blocks, {b['paths']:,} histories):** total return ran from "
                   f"{pct(b['total_return']['p5'], 0)} (5th percentile) to {pct(b['total_return']['p95'], 0)} (95th), "
                   f"median {pct(b['total_return']['p50'], 0)}. Plan for a worst fall near **{pct(b['max_drawdown']['p95'], 0)}** "
                   f"(the 1-in-20 case), not the {pct(mc['backtest_max_drawdown'], 0)} the single backtest happened to show. "
                   f"{pct(b['risk_of_ruin'], 1)} of histories fell {abs(b['ruin_threshold']):.0%} from a peak.")
    k = v.get("kelly")
    if k:
        if k.get("edge"):
            out.append(f"**Sizing (Kelly):** the growth-optimal size is {num(k['point_estimate'])}x the size backtested, but with "
                       f"estimation error the plausible range is {num(k['bootstrap']['p5'])}x to {num(k['bootstrap']['p95'])}x. "
                       f"Suggested: {num(k['recommended'])}x. Betting more than the optimum lowers growth and raises risk; "
                       "backtests are optimistic, so treat these as upper limits.")
        else:
            out.append("**Sizing (Kelly):** no positive edge was found, so there is nothing to size.")
    o = v.get("overfitting")
    if o:
        s = f"**Is it luck?** The probability that the true Sharpe ratio is above zero is {pct(o['probabilistic_sharpe'], 1)}"
        d = o.get("deflated_sharpe_effective_trials")
        if d:
            s += (f"; after allowing for {o['trials_recorded']} parameter sets tried (about {d['n_trials']:.1f} independent) it is "
                  f"{pct(d['probability'], 1)}")
        s += "."
        if o.get("pbo"):
            s += f" The probability of backtest overfitting is {pct(o['pbo']['pbo'], 0)}."
        if o.get("spa"):
            s += f" The best-of-grid test gives p = {num(o['spa']['p_value'])}."
        p = o.get("permutation", {})
        if "p_value" in p:
            s += f" Shuffling the market's returns while keeping the strategy's exposures gives p = {num(p['p_value'])} for the timing."
        out.append(s + " These measures rank how well the evidence supports the strategy; they do not predict future profit, and they "
                   "cannot detect look-ahead, which is why the separate look-ahead check exists.")
    cs = v.get("costs")
    if cs:
        lv = {r["cost_multiplier"]: r for r in cs["levels"]}
        s = (f"**Costs:** total return was {pct(lv[1.0]['total_return'], 0)} at the assumed costs, {pct(lv[2.0]['total_return'], 0)} at double "
             f"and {pct(lv[3.0]['total_return'], 0)} at triple; delaying every fill by one bar gave {pct(cs['delayed_fill']['total_return'], 0)}.")
        steady = lv[1.0]["total_return"] >= lv[2.0]["total_return"] >= lv[3.0]["total_return"]
        if cs.get("break_even_multiplier") and steady:
            s += f" Profit would vanish at about {num(cs['break_even_multiplier'], 1)}x the assumed costs."
        elif not steady:
            s += (" Total return does not fall steadily as costs rise, because position sizes change in whole lots, so the "
                  "result is noisy and no break-even cost is quoted.")
        out.append(s)
    op = v.get("option_pricing")
    if op:
        out.append("**Option prices are modelled, not quoted.** Moving the assumed volatility level and skew changed the total return as follows: "
                   + "; ".join(f"{c['case']}: {pct(c['total_return'], 0)}" for c in op["cases"])
                   + ". The conclusion should be read as a range, not a point.")
    return out


NEXT_STEPS = {
    "trades": "Test over a longer history or a broader universe to get more trades before drawing conclusions.",
    "look-ahead": "Find where the strategy reads future data (or fills on the signal bar) and fix it before anything else.",
    "walk-forward": "Reduce the number of free parameters or fix them from theory, then re-run; large in-sample/out-of-sample gaps usually mean too much tuning.",
    "sensitivity": "Prefer parameter values in the middle of a plateau, not the single best value.",
    "monte-carlo": "Size positions for the 1-in-20 drawdown shown above, not the one in the backtest.",
    "kelly": "Do not size above the suggested multiple; if there is no edge, stop here.",
    "significance": "Treat the result as unproven until more data or an independent sample supports it.",
    "overfitting": "Cut the number of variants tried, and keep a final hold-out period untouched.",
    "regimes": "Check how it behaves in the conditions it has not seen (e.g. a bear market) before relying on it.",
    "costs": "Lower turnover or use limit orders; re-test with realistic spreads for the instruments traded.",
    "option pricing": "Obtain real historical option quotes (or a vendor surface) before trusting the profit level of an options strategy.",
    "data": "Inspect the flagged bars; a data error can create or destroy a result.",
    "performance": "Reconsider the idea; it did not make money over this history.",
}

LIMITS = [
    "This is a simulation on past prices; it says nothing certain about the future, and it is not investment advice.",
    "Trades fill at the next bar's open plus a fixed slippage; real fills, spreads and market impact can differ, especially for intraday or large orders.",
    "Short borrow fees are not modelled. Dividends and interest follow the settings recorded in the run.",
    "Universes built from today's constituents suffer survivorship bias: companies that failed are missing.",
    "The statistical tests rank evidence; none of them proves a strategy works, and a strategy tuned many times will look better than it is.",
]


def explain(v: dict, meta: dict | None = None, title: str | None = None) -> str:
    flags = v.get("flags", [])
    level, why = trust_level(flags)
    name = title or (meta or {}).get("strategy") or "Strategy"
    parts = [f"# {name}: what the backtest says", ""]
    parts += ["## In short", ""] + [ln + "\n" for ln in summary(v, meta)]
    parts += [f"**How much to trust it: {level}.** {why} This is a ranking of statistical support, not a forecast.", ""]
    risk = risk_note(flags)
    if risk:
        parts += [risk, ""]
    drove = what_drove(v, meta)
    if drove:
        parts += ["## What drove the result", ""] + [f"- {x}" for x in drove] + [""]
    t = tests(v)
    if t:
        parts += ["## Does it hold up?", ""] + [f"{x}\n" for x in t]
    if flags:
        parts += ["## Concerns, most serious first", ""]
        parts += [f"- **{f['severity']}:** {f['message']}" for f in flags]
        parts += [""]
    seen, steps = set(), []
    for f in flags:
        key = f["test"]
        if key in NEXT_STEPS and key not in seen and f["severity"] in ("high", "medium"):
            seen.add(key)
            steps.append(NEXT_STEPS[key])
    if steps:
        parts += ["## What to do next", ""] + [f"- {s}" for s in steps] + [""]
    params = v.get("params")
    if params:
        parts += ["## Settings used", "", f"Parameters: `{params}`.", ""]
    parts += ["## What this does not tell you", ""] + [f"- {x}" for x in LIMITS]
    if (meta or {}).get("notes"):
        parts += [f"- Run notes: {' '.join(meta['notes'])}"]
    return "\n".join(parts).rstrip() + "\n"
