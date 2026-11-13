# Out-of-sample testing, walk-forward optimisation, parameter sensitivity

## What each one answers

- **In-sample / out-of-sample (IS/OOS) split**: does the strategy still work on data it
  was not tuned on? One split, one answer, easily contaminated by repeated peeking.
- **Walk-forward optimisation (WFO)**: if I had re-tuned the parameters on a schedule
  using only past data, what would I actually have earned? Formalised by Robert Pardo
  (*Design, Testing and Optimization of Trading Systems*, 1992; 2nd ed. *The Evaluation
  and Optimization of Trading Strategies*, 2008).
- **Parameter sensitivity**: is the chosen parameter set on a broad plateau or a lucky spike?

## Walk-forward procedure

1. Choose in-sample length `L_is`, out-of-sample length `L_oos`, step = `L_oos`
   (non-overlapping OOS segments), objective (default: Sharpe; alternatives CAGR/MaxDD,
   profit factor), and the parameter grid. **Fix all of these before running.**
2. For window `k`: optimise over the grid on the IS slice; take the best parameters;
   run them on the following OOS slice.
   - **Rolling**: IS slice has fixed length and slides forward (adapts to regime change).
   - **Anchored**: IS slice always starts at the beginning and grows (more data, slower to adapt).
3. Stitch the OOS segments into one equity curve. That curve is the walk-forward result.
4. Report per window: chosen parameters, IS metric, OOS metric.

**Walk-forward efficiency** `WFE = annualised OOS return / annualised IS return`
(per window and overall). Also computed on the objective itself (OOS Sharpe / IS Sharpe).

## Pitfalls found

- **Thresholds are folklore.** Sources disagree (">0.5", ">0.7", "<0.3 is a red flag").
  WFE is undefined or misleading when IS return is near zero or negative. Do not use it
  as a pass/fail gate.
- **The WFO setup is itself tunable.** Trying several window lengths and rolling vs
  anchored, then reporting the best, is overfitting one level up.
- **Short OOS windows are noisy.** A window with 3 trades says nothing.
- **Unstable chosen parameters** across windows mean the optimiser is fitting noise.
- **Warm-up leakage**: indicators need history; the OOS run must be warmed up with prior
  data but must not *trade* on it, and positions must carry correctly across segment joins.
- **Purging**: if a strategy's trades or labels span the IS/OOS boundary, drop (purge) the
  overlap so IS optimisation does not see outcomes that fall in OOS (López de Prado,
  *Advances in Financial Machine Learning*, 2018, ch. 7).
- Every parameter set evaluated counts as a trial for the deflated Sharpe ratio
  (see overfitting-statistics.md).

## Decision

- Implement IS/OOS split (default 70/30 by time), rolling and anchored WFO.
- Defaults: rolling, IS = 4 × OOS, at least 5 windows; refuse or warn when a window
  has fewer than 10 trades (configurable).
- Carry positions across segments: run the engine once per window with warm-up history,
  record only OOS-period equity changes; at each boundary the new parameters take over
  the existing positions.
- Report: stitched OOS curve and metrics, per-window table, WFE (return-based and
  Sharpe-based, shown as "n/a" when IS ≤ 0), share of windows profitable OOS, parameter
  stability (dispersion of chosen parameters, normalised by grid range).
- Flags (wording for the explanation layer, not gates): OOS Sharpe < 50% of IS;
  fewer than half the windows profitable; chosen parameters jump across the grid.
- Record the number of parameter sets tried; pass it to the deflated Sharpe calculation.
- Parameter sensitivity: full grid for 1–2 parameters (heatmap), one-at-a-time sweeps
  for more. Report the objective at the optimum versus the median of its grid neighbours
  ("plateau ratio"); flag when neighbours fall below half the optimum.

## Known-answer tests

- A strategy with no parameters gives a stitched OOS curve identical to a single plain
  backtest over the same OOS dates (tests joins, warm-up and position carry).
- Synthetic data where the profitable parameter switches halfway: rolling WFO picks up
  the switch; anchored lags.
- Pure-noise prices with a 50-point grid: IS Sharpe clearly positive, OOS Sharpe ≈ 0
  over many seeds (demonstrates and tests the overfitting flag).
- Window boundaries: no OOS bar is ever inside its own IS slice; OOS segments tile the
  period with no gaps or overlaps.

## Sources

- Pardo, R. (2008). *The Evaluation and Optimization of Trading Strategies*, 2nd ed., Wiley.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*, Wiley (purging, embargo).
- Practitioner summaries consulted: [LuxAlgo](https://www.luxalgo.com/library/concept/walk-forward-analysis/),
  [quant-trading-tools](https://quant-trading-tools.pages.dev/walk-forward-analysis/),
  [TradeScript](https://tradescript.substack.com/p/walk-forward-optimization-why-your),
  [NexusFi](https://nexusfi.com/a/automation/walk-forward-analysis).
