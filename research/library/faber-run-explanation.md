# FaberTiming: what the backtest says

## In short

Over 2007-06-01 to 2026-11-16 (4,897 trading days) on SPY, EFA, IEF, DBC, VNQ, the strategy returned **136.5%** in total (4.5% a year), with a worst peak-to-trough fall of **-14.9%** and a Sharpe ratio of 0.34.

Simply holding the benchmark returned 599.0% with a worst fall of -55.2%, so the strategy finished behind it in total return but with a shallower worst fall.

**How much to trust it: Tentative.** 5 moderate concerns below; the result is suggestive, not established. This is a ranking of statistical support, not a forecast.

## What drove the result

- It was invested 99% of the time, with 438 closed trades.
- Its returns moved 0.24x as much as the benchmark's (beta) and left 0.4% a year unexplained by that exposure (alpha).
- In rising markets (the benchmark above its 200-day average, 79% of the time) it returned 127.0%; in falling markets (21% of the time), 4.4%.
- Interest on idle cash added $10,612 and margin interest cost $3.
- Trading costs reduced total return by 1.0 percentage points ($573 in commission and slippage).

## Does it hold up?

**Look-ahead check:** passed. Cutting the data off at three dates left every earlier order unchanged, so the strategy did not use information from the future that the engine supplies.

**Walk-forward (re-tuning on the past, trading the future):** across 15 windows the out-of-sample result was 4.3% a year (Sharpe 0.62) against 5.0% (Sharpe 0.68) in-sample, and 73% of windows were profitable. A large drop out-of-sample points to overfitting.

**One-split check:** choosing parameters on the first 70% of the history and testing on the rest changed the Sharpe ratio from 0.48 to 0.98.

**Parameter sensitivity:** neighbouring parameter values scored 91% of the best, and 100% of all tried combinations were profitable. A broad plateau is reassuring.

**Monte Carlo (resampling the daily returns in blocks, 2,000 histories):** total return ran from 37% (5th percentile) to 309% (95th), median 140%. Plan for a worst fall near **-30%** (the 1-in-20 case), not the -15% the single backtest happened to show. 0.0% of histories fell 50% from a peak.

**Sizing (Kelly):** the growth-optimal size is 4.25x the size backtested, but with estimation error the plausible range is 0.00x to 8.38x. Suggested: 1.00x. Betting more than the optimum lowers growth and raises risk; backtests are optimistic, so treat these as upper limits.

**Is it luck?** The probability that the true Sharpe ratio is above zero is 93.4%; after allowing for 3 parameter sets tried (about 1.1 independent) it is 93.8%. The best-of-grid test gives p = 0.00. Shuffling the market's returns while keeping the strategy's exposures gives p = 0.66 for the timing. These measures rank how well the evidence supports the strategy; they do not predict future profit, and they cannot detect look-ahead, which is why the separate look-ahead check exists.

**Costs:** total return was 136% at the assumed costs, 136% at double and 135% at triple; delaying every fill by one bar gave 132%. Profit would vanish at about 134.8x the assumed costs.

## Concerns, most serious first

- **medium:** DBC: 1 bar(s) where high/low do not contain open/close.
- **medium:** The chosen value of months jumps around between windows.
- **medium:** 93% probability that the true Sharpe ratio is above zero (95% is the usual bar).
- **medium:** After allowing for about 1 independent variants tried, the probability of a real edge is 94%.
- **medium:** Timing is not distinguishable from chance (permutation p = 0.66); returns may come from market exposure alone.
- **info:** Total return 136.5% is below the benchmark's 599.0%.
- **info:** SPY: 1 bar(s) moved more than 10 standard deviations (check these are real market moves).
- **info:** EFA: 1 bar(s) moved more than 10 standard deviations (check these are real market moves).
- **info:** VNQ: 2 bar(s) moved more than 10 standard deviations (check these are real market moves).
- **info:** A 1-in-20 resampled history has a drawdown of -30%, against -15% in the backtest.
- **info:** 95% of profit came from bull markets (79% of the time).
- **info:** Not run: needs at least 10 configurations (have 3).

## What to do next

- Inspect the flagged bars; a data error can create or destroy a result.
- Reduce the number of free parameters or fix them from theory, then re-run; large in-sample/out-of-sample gaps usually mean too much tuning.
- Treat the result as unproven until more data or an independent sample supports it.

## Settings used

Parameters: `{'months': 10, 'timing': True}`.

## What this does not tell you

- This is a simulation on past prices; it says nothing certain about the future, and it is not investment advice.
- Trades fill at the next bar's open plus a fixed slippage; real fills, spreads and market impact can differ, especially for intraday or large orders.
- Short borrow fees are not modelled. Dividends and interest follow the settings recorded in the run.
- Universes built from today's constituents suffer survivorship bias: companies that failed are missing.
- The statistical tests rank evidence; none of them proves a strategy works, and a strategy tuned many times will look better than it is.
- Run notes: Short borrow fees are not modelled.
