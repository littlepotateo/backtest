# IntradayMomentum: what the backtest says

## In short

Over 2026-07-31 to 2026-11-17 (77 trading days) on SPY, the strategy returned **-4.6%** in total (-14.2% a year), with a worst peak-to-trough fall of **-4.6%** and a Sharpe ratio of -6.85.

Simply holding the benchmark returned -1.9% with a worst fall of -6.0%, so the strategy finished behind it in total return but with a shallower worst fall.

**How much to trust it: Unproven.** 4 serious concerns below mean this result should not be relied on yet. This is a ranking of statistical support, not a forecast.

**Risk to plan for** (separate from the evidence question): 100% of resampled histories lose money.

## What drove the result

- It was invested 8% of the time, with 76 closed trades.
- Its returns moved -0.03x as much as the benchmark's (beta) and left -15.6% a year unexplained by that exposure (alpha).
- The history contains bear market in the sample, so the strategy has not been tested in that condition.
- Trading costs reduced total return by 1.6 percentage points ($1,649 in commission and slippage).

## Does it hold up?

**Look-ahead check:** passed. Cutting the data off at three dates left every earlier order unchanged, so the strategy did not use information from the future that the engine supplies.

**Walk-forward (re-tuning on the past, trading the future):** across 6 windows the out-of-sample result was -16.7% a year (Sharpe -7.72) against -6.1% (Sharpe -3.16) in-sample, and 0% of windows were profitable. A large drop out-of-sample points to overfitting.

**One-split check:** choosing parameters on the first 70% of the history and testing on the rest changed the Sharpe ratio from -5.19 to -10.14.

**Parameter sensitivity:** neighbouring parameter values scored -260% of the best, and 50% of all tried combinations were profitable. A narrow peak suggests the best value is partly luck.

**Monte Carlo (resampling the daily returns in blocks, 500 histories):** total return ran from -6% (5th percentile) to -2% (95th), median -5%. Plan for a worst fall near **-7%** (the 1-in-20 case), not the -5% the single backtest happened to show. 0.0% of histories fell 50% from a peak.

**Sizing (Kelly):** no positive edge was found, so there is nothing to size.

**Is it luck?** The probability that the true Sharpe ratio is above zero is 0.0%; after allowing for 4 parameter sets tried (about 4.0 independent) it is 0.0%. The best-of-grid test gives p = 0.19. Shuffling the market's returns while keeping the strategy's exposures gives p = 0.95 for the timing. These measures rank how well the evidence supports the strategy; they do not predict future profit, and they cannot detect look-ahead, which is why the separate look-ahead check exists.

**Costs:** total return was -5% at the assumed costs, -6% at double and -8% at triple; delaying every fill by one bar gave 4%. Profit would vanish at about -1.8x the assumed costs.

## Concerns, most serious first

- **high:** The strategy lost money over the test period.
- **high:** No positive edge to size.
- **high:** 0% probability that the true Sharpe ratio is above zero (95% is the usual bar).
- **high:** After allowing for about 4 independent variants tried, the probability of a real edge is 0%.
- **medium:** Orders fill on the same bar that produced the signal.
- **medium:** Only 0% of out-of-sample windows were profitable.
- **medium:** Neighbouring parameter values score -260% of the best: a narrow peak.
- **medium:** 100% of resampled histories lose money.
- **medium:** The best parameter set is not clearly better than holding cash once selection is accounted for (p = 0.19).
- **medium:** Timing is not distinguishable from chance (permutation p = 0.95); returns may come from market exposure alone.
- **medium:** Untested conditions: no bear market in the sample.
- **info:** Total return -4.6% is below the benchmark's -1.9%.
- **info:** 6 of 6 windows had fewer than 10 trades.
- **info:** Random entries with the same holding periods do about as well (p = 1.00).
- **info:** Not run: needs at least 10 configurations (have 4).

## What to do next

- Reconsider the idea; it did not make money over this history.
- Do not size above the suggested multiple; if there is no edge, stop here.
- Treat the result as unproven until more data or an independent sample supports it.
- Find where the strategy reads future data (or fills on the signal bar) and fix it before anything else.
- Reduce the number of free parameters or fix them from theory, then re-run; large in-sample/out-of-sample gaps usually mean too much tuning.
- Prefer parameter values in the middle of a plateau, not the single best value.
- Size positions for the 1-in-20 drawdown shown above, not the one in the backtest.
- Check how it behaves in the conditions it has not seen (e.g. a bear market) before relying on it.

## Settings used

Parameters: `{'signal': 'r1', 'mode': 'timing', 'gamma': 5.0, 'min_obs': 60}`.

## What this does not tell you

- This is a simulation on past prices; it says nothing certain about the future, and it is not investment advice.
- Trades fill at the next bar's open plus a fixed slippage; real fills, spreads and market impact can differ, especially for intraday or large orders.
- Short borrow fees are not modelled. Dividends and interest follow the settings recorded in the run.
- Universes built from today's constituents suffer survivorship bias: companies that failed are missing.
- The statistical tests rank evidence; none of them proves a strategy works, and a strategy tuned many times will look better than it is.
- Run notes: Orders fill at the close of the bar that generated them. This is optimistic; next-bar-open fills are the default. Short borrow fees are not modelled.
