# RegimeOptimal: what the backtest says

## In short

Over 1968-12-31 to 2025-12-31 (14,372 trading days) on FFMKT, the strategy returned **2,909.4%** in total (6.2% a year), with a worst peak-to-trough fall of **-34.0%** and a Sharpe ratio of 0.53.

Simply holding the benchmark returned 2,520.0% with a worst fall of -59.2%, so the strategy finished ahead of it in total return but with a shallower worst fall.

**How much to trust it: Tentative.** 3 moderate concerns below; the result is suggestive, not established. This is a ranking of statistical support, not a forecast.

**Risk to plan for** (separate from the evidence question): 17% of resampled histories fall 50% from a peak.

## What drove the result

- It was invested 100% of the time, with 25 closed trades.
- Its returns moved 0.61x as much as the benchmark's (beta) and left 2.4% a year unexplained by that exposure (alpha).
- In rising markets (the benchmark above its 200-day average, 67% of the time) it returned 1,336.5%; in falling markets (33% of the time), 109.5%.
- Trading costs reduced total return by 2.2 percentage points ($2,160 in commission and slippage).

## Does it hold up?

**Look-ahead check:** passed. Cutting the data off at three dates left every earlier order unchanged, so the strategy did not use information from the future that the engine supplies.

**Walk-forward (re-tuning on the past, trading the future):** across 53 windows the out-of-sample result was 5.7% a year (Sharpe 0.51) against 6.5% (Sharpe 0.63) in-sample, and 68% of windows were profitable. A large drop out-of-sample points to overfitting.

**One-split check:** choosing parameters on the first 70% of the history and testing on the rest changed the Sharpe ratio from 0.52 to 0.70.

**Parameter sensitivity:** neighbouring parameter values scored 91% of the best, and 100% of all tried combinations were profitable. A broad plateau is reassuring.

**Monte Carlo (resampling the daily returns in blocks, 2,000 histories):** total return ran from 500% (5th percentile) to 13,802% (95th), median 2,912%. Plan for a worst fall near **-58%** (the 1-in-20 case), not the -34% the single backtest happened to show. 17.2% of histories fell 50% from a peak.

**Sizing (Kelly):** the growth-optimal size is 3.77x the size backtested, but with estimation error the plausible range is 2.18x to 5.85x. Suggested: 1.00x. Betting more than the optimum lowers growth and raises risk; backtests are optimistic, so treat these as upper limits.

**Is it luck?** The probability that the true Sharpe ratio is above zero is 100.0%; after allowing for 2 parameter sets tried (about 1.0 independent) it is 100.0%. The best-of-grid test gives p = 0.00. Shuffling the market's returns while keeping the strategy's exposures gives p = 0.07 for the timing. These measures rank how well the evidence supports the strategy; they do not predict future profit, and they cannot detect look-ahead, which is why the separate look-ahead check exists.

**Costs:** total return was 2,909% at the assumed costs, 2,879% at double and 2,853% at triple; delaying every fill by one bar gave 2,708%. Profit would vanish at about 1,347.6x the assumed costs.

## Concerns, most serious first

- **high:** 17% of resampled histories fall 50% from a peak.
- **medium:** Only 25 closed trades: statistics are unreliable.
- **medium:** FFMKT: longest gap between bars is 12 days.
- **medium:** The chosen value of states jumps around between windows.
- **info:** FFMKT: 5 bar(s) moved more than 10 standard deviations (check these are real market moves).
- **info:** 53 of 53 windows had fewer than 10 trades.
- **info:** A 1-in-20 resampled history has a drawdown of -58%, against -34% in the backtest.
- **info:** Not run: needs at least 10 configurations (have 2).

## What to do next

- Size positions for the 1-in-20 drawdown shown above, not the one in the backtest.
- Test over a longer history or a broader universe to get more trades before drawing conclusions.
- Inspect the flagged bars; a data error can create or destroy a result.
- Reduce the number of free parameters or fix them from theory, then re-run; large in-sample/out-of-sample gaps usually mean too much tuning.

## Settings used

Parameters: `{'mode': 'opt', 'states': 2, 'train_end': '1968-12-31'}`.

## What this does not tell you

- This is a simulation on past prices; it says nothing certain about the future, and it is not investment advice.
- Trades fill at the next bar's open plus a fixed slippage; real fills, spreads and market impact can differ, especially for intraday or large orders.
- Short borrow fees are not modelled. Dividends and interest follow the settings recorded in the run.
- Universes built from today's constituents suffer survivorship bias: companies that failed are missing.
- The statistical tests rank evidence; none of them proves a strategy works, and a strategy tuned many times will look better than it is.
- Run notes: Short borrow fees are not modelled.
