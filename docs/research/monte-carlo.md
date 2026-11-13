# Monte Carlo methods

A single backtest is one path. Monte Carlo methods ask how different the outcome could
have been. Each variant tests a **different** risk, and they must not be mixed up.

| Variant | What is randomised | What it tells you | What it cannot tell you |
|---|---|---|---|
| Trade reshuffle (permute, no replacement) | Order of the realised trades | Sequence risk: drawdown range for the same set of trades | Final return (unchanged with fixed sizing); assumes trades are independent |
| Trade bootstrap (with replacement) | Which trades occur, and order | Sampling uncertainty of return and drawdown | Destroys clustering of wins/losses |
| Block bootstrap of period returns | Blocks of consecutive daily (or bar) returns | Same, but preserves autocorrelation and volatility clustering | Still assumes the future resembles the sample |
| Random trade skipping | Drop each trade with probability p (e.g. 5–10%) | Dependence on a few big winners; missed fills | — |
| Price-noise / synthetic paths | The price series itself; strategy is **re-run** | Whether the rules depend on exact historical prices | Expensive; noise model is an assumption |
| Parameter jitter | Parameters perturbed around chosen values; re-run | Local robustness (complements the sensitivity grid) | — |

## Method details

- **Stationary bootstrap** (Politis & Romano, 1994, *JASA* 89): blocks start at random
  positions, block lengths are geometric with mean `1/p`, wrapping around the end. The
  resampled series is stationary, unlike fixed-block bootstrap.
- **Block length**: automatic selection of Politis & White (2004), with the correction
  in Patton, Politis & White (2009). The Python `arch` package implements both
  (`optimal_block_length`, `StationaryBootstrap`). **[verify]** exact API names.
- **Compounding**: resample returns, then compound; for trades, resample per-trade
  returns as a fraction of equity (so sizing scales), not dollar P&L, unless the
  strategy used fixed dollar sizing.
- **Outputs per variant**: distribution (5/25/50/75/95th percentiles) of final return,
  CAGR, max drawdown, longest drawdown, Sharpe; fan chart of equity paths; probability
  of loss; **risk of ruin** = share of paths whose drawdown from peak exceeds a
  user-set threshold (default 50%) at any time; probability of hitting a drawdown worse
  than the backtest's.
- **Price-noise variant**: build synthetic price paths by stationary-bootstrapping the
  asset's own returns (keeps fat tails and clustering) and re-running the strategy.
  Multi-asset: resample the same time blocks across all assets to keep correlations.
  Adding white noise to OHLC is a weaker alternative (must keep low ≤ open, close ≤ high).

## Pitfalls found

- Plain reshuffling **understates** drawdown risk when wins and losses cluster; one
  practitioner example shows median max drawdown 25% under shuffle vs 31% under block
  bootstrap. Always show the block-bootstrap result beside the shuffle.
- Reshuffling does not test whether the edge is real: every path has the same trades.
  Significance belongs to the permutation tests (overfitting-statistics.md).
- Resampling trades ignores overlapping positions and time in market; period-return
  bootstrap handles those.
- Few trades (< ~30) give a falsely tight distribution. Warn.
- Monte Carlo on an overfitted backtest produces confident nonsense: the inputs are
  already biased upward. The explanation must say this when overfitting flags are raised.
- Options strategies have strongly skewed returns (many small wins, rare large losses);
  if the sample contains no large loss, no resampling can invent one. Flag short-premium
  strategies whose sample lacks a stress period.

## Decision

- Implement our own small stationary bootstrap (NumPy), validated against `arch` in tests.
- Default run: 5,000 paths each for (a) trade reshuffle, (b) stationary bootstrap of
  bar returns with automatic block length, (c) 10% trade skipping. Price-noise re-runs
  are opt-in (default 200 paths) because they re-run the engine.
- Fixed seed recorded in the run for reproducibility.
- Explanation layer reports the 5th-percentile outcome and 95th-percentile drawdown as
  the "plan for this" numbers, not the backtest's single path.

## Known-answer tests

- Reshuffle with fixed fractional sizing: every path ends at the same final equity;
  drawdowns differ.
- Bootstrap of i.i.d. normal returns: mean of path means ≈ sample mean; dispersion of
  path means ≈ σ/√n.
- Stationary bootstrap: mean block length ≈ 1/p; an AR(1) series keeps its lag-1
  autocorrelation (approximately) under block bootstrap and loses it under i.i.d. bootstrap.
- Risk of ruin for a symmetric ±1% coin-flip process matches the analytic barrier-hit
  probability within Monte Carlo error.
- Same seed → identical output.

## Sources

- Politis, D. & Romano, J. (1994). The stationary bootstrap. *JASA* 89(428).
- Politis, D. & White, H. (2004). Automatic block-length selection for the dependent
  bootstrap. *Econometric Reviews* 23(1); Patton, Politis & White (2009) correction.
- Practitioner material consulted: [AmiBroker Monte Carlo guide](https://amibroker.com/guide/h_montecarlo.html),
  [MQL5: stress testing trade sequences](https://www.mql5.com/en/articles/22291),
  [NexusFi](https://nexusfi.com/a/risk-management/monte-carlo-simulation).
