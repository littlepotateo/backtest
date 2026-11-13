# Regime breakdown, cost stress, and bias checks

## 1. Regime breakdown

**Question:** does the strategy make its money everywhere, or only in one kind of market?

Regime labels must be computed **only from past data** and from the benchmark, not from
the strategy's own results:

| Dimension | Default rule | Labels |
|---|---|---|
| Trend | Benchmark close vs its 200-day average (lagged one bar) | bull / bear |
| Volatility | 21-day realised volatility of the benchmark vs its trailing 1-year terciles (or VIX terciles when VIX is cached) | low / mid / high |
| Drawdown | Benchmark more than 10% below its trailing peak | in drawdown / not |
| Calendar | Year, and named stress windows (2008-09 to 2009-03, 2020-02 to 2020-04, 2022) where data covers them | — |

Per regime: share of time, return, Sharpe, max drawdown, trade count, win rate.

Pitfalls: with IBKR's 5-year limit the sample may contain no bear market at all — say
so explicitly instead of showing an empty row; regimes with few bars or trades get a
"too little data" marker; statistical regime models (hidden Markov) are fitted on the
full sample and therefore look ahead unless refitted on a rolling basis — not used by default.

**Decision:** rule-based labels above; HMM regimes deferred. Flag when more than ~80%
of profit comes from one regime, and when a regime the strategy has never seen (e.g. no
bear market in sample) exists.

## 2. Cost stress

**Question:** how much of the edge is eaten by trading frictions, and at what cost level
does it vanish?

Cost model components:
- **Commission**: IBKR-style per-share for US stocks (with per-order minimum and
  percent-of-trade cap) and per-contract for options. The exact current schedule is
  configuration, loaded from `config/costs.yaml`, and **must be taken from IBKR's
  published schedule at build time [verify]** — not hard-coded from memory.
- **Spread**: half-spread paid on every fill. Default by instrument class (large-cap
  ETF ≈ 1 bp; small caps far wider); options use the modelled bid/ask (options-pricing.md).
- **Slippage / impact**: fixed basis points by default; optional square-root impact
  `k · σ_daily · √(order size / average daily volume)` for larger orders.
- **Short borrow and margin interest**: annual rates applied daily on short and
  borrowed balances.
- **Fill assumption**: next-bar open by default; optional participation cap (max % of
  bar volume).

Stress procedure: re-run at 0×, 1×, 2×, 3× costs; additionally delay every fill by one
extra bar (execution-delay stress — the most revealing test for intraday strategies).
Report metrics at each level and the **break-even cost per trade** (the per-trade cost
in basis points at which net profit reaches zero, ≈ gross profit / total traded notional).

Pitfalls: intraday strategies are dominated by spread and slippage, not commission;
minute bars hide the bid/ask bounce (a mean-reversion strategy can "profit" from it);
filling at the same bar's close that generated the signal is unrealistic; limit orders
are not filled just because price touched them.

**Decision:** costs applied in the engine at fill time, multiplier exposed as a run
setting; cost stress = four re-runs + one delayed-fill re-run. Flags: Sharpe halves at
2× costs; break-even cost below 2× the assumed cost; average profit per trade below
3× the assumed round-trip cost.

## 3. Look-ahead and other bias checks (`bt check`)

| Bias | How it is prevented or detected |
|---|---|
| **Look-ahead** | By construction: `ctx` exposes only bars up to the current one, and orders fill on the next bar. Detected by the **truncation test**: run on the full data and on data cut at several random dates `t`; all orders issued up to `t` must be identical. Any difference means the strategy used future data. |
| Same-bar fills | Engine refuses to fill at the signal bar's own close unless explicitly enabled; flagged in the run. |
| Adjusted-price leakage | Back-adjusted prices embed future dividends/splits. Signals may use adjusted prices; order sizing and P&L use prices as they were. Whether IBKR bars are adjusted is recorded per cache file. |
| **Survivorship** | Universe lists are static today. Any multi-stock strategy whose universe is "current index members" is flagged: results are biased upward. Point-in-time membership is out of scope for v1. |
| Data snooping | Trial ledger and deflated Sharpe (overfitting-statistics.md). |
| Too few trades | Fewer than 30 trades: metrics shown with a warning; fewer than 10: validation tests refuse to draw conclusions. |
| Data quality | Gaps, zero/negative prices, duplicate timestamps, bars outside session hours, single-bar spikes > 10 daily standard deviations. |
| Time zones and sessions | All timestamps stored in UTC with the exchange time zone recorded; daily bars are stamped at the session close; a strategy cannot see a daily bar before that close. |
| Outlier dependence | Share of total profit from the top 5% of trades; result with the single best trade removed. |

The truncation test is the standard approach used by other frameworks' look-ahead
detectors (e.g. freqtrade's lookahead analysis compares signals computed on full versus
truncated data) **[verify]**.

## Known-answer tests

- A deliberately cheating strategy (uses tomorrow's close via raw data access) is caught
  by the truncation test; an honest moving-average strategy passes.
- Regime labels at date `t` do not change when data after `t` is removed.
- Regime time shares sum to 100%; per-regime P&L sums to total P&L.
- Zero-cost run P&L minus 1× run P&L equals the sum of recorded costs exactly.
- Break-even cost: re-running at that cost gives ≈ zero net profit.
- Commission function matches hand-computed examples at the minimum, the normal range
  and the cap.

## Sources

- López de Prado (2018), *Advances in Financial Machine Learning* (backtest biases).
- Almgren & Chriss (2000), Optimal execution of portfolio transactions (impact models);
  square-root impact law (Grinold & Kahn; Tóth et al. 2011).
- [Nasdaq: 7 options backtesting pitfalls](https://www.nasdaq.com/articles/avoid-these-7-options-backtesting-pitfalls-2019-07-01).
