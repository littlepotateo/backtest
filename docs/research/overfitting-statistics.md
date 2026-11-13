# Overfitting and significance statistics

These answer: **is the result distinguishable from luck, given how many things were tried?**

## 1. Probabilistic Sharpe ratio (PSR) — Bailey & López de Prado (2012)

Probability that the true Sharpe exceeds a benchmark `SR*`, allowing for sample length,
skewness `γ3` and (Pearson, normal = 3) kurtosis `γ4`. All Sharpe ratios are **per
period, not annualised**; `T` = number of return observations.

```
PSR(SR*) = Φ( (SR − SR*) · √(T − 1) / √(1 − γ3·SR + ((γ4 − 1)/4)·SR²) )
```

Minimum track record length for confidence `1 − α`:
`MinTRL = 1 + (1 − γ3·SR + ((γ4 − 1)/4)·SR²) · (z_α / (SR − SR*))²`.

Negative skew and fat tails (typical of short-option strategies) lower PSR.

## 2. Deflated Sharpe ratio (DSR) — Bailey & López de Prado (2014)

PSR with the benchmark raised to the Sharpe you would expect from the best of `N`
skill-less trials:

```
SR0 = √V · [ (1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ]      γ ≈ 0.5772 (Euler–Mascheroni)
DSR = PSR(SR0)
```

`V` = variance of the Sharpe ratios across the trials (per-period units).

Pitfalls: `N` should be the number of **effectively independent** trials — correlated
parameter variants over-deflate if counted raw; the approximation is asymptotic and
under-corrects for small `N` (< ~10); `N` is only honest if every variant tried is
recorded, including ones tried in earlier sessions.

## 3. Probability of backtest overfitting (PBO) via CSCV — Bailey, Borwein, López de Prado & Zhu (2017)

Needs the returns of **all** candidate configurations (e.g. the whole parameter grid).

1. Build matrix `M` (T rows × N configurations) of per-period returns.
2. Split rows into `S` equal contiguous blocks (S even, typically 8–16).
3. For every way of choosing `S/2` blocks as in-sample (the rest, in order, are
   out-of-sample): find the configuration `n*` with the best IS Sharpe; find its OOS
   rank among the N; relative rank `ω = rank/(N + 1)`; logit `λ = ln(ω/(1 − ω))`.
4. `PBO = share of splits with λ ≤ 0` (best-in-sample is at or below the OOS median).

Also report: the distribution of λ, the regression of OOS on IS performance (a negative
slope is a strong overfitting signal), and probability of OOS loss for the IS-best.

Pitfalls: needs N ≥ ~10 configurations to mean much; block structure assumes blocks are
roughly exchangeable; with `S = 16` there are 12,870 splits — fine.

## 4. Permutation tests — Aronson (2006), Masters

- **Returns/positions permutation**: keep the strategy's position series, permute the
  market's bar returns (or equivalently shuffle the alignment), recompute the metric,
  repeat. p-value = `(1 + #{permuted ≥ actual}) / (1 + B)`. Tests whether timing has
  skill beyond the strategy's average exposure. Cheap (no re-run).
- **Price-path permutation (Masters)**: permute the log price *changes* (bar-to-bar and
  intrabar components separately, across all assets jointly) to build synthetic markets
  with the same return distribution but no exploitable structure; **re-run the whole
  strategy including any optimisation** on each. Tests the entire process, including
  selection bias. Expensive.
- **Random-entry baseline**: same number of trades and holding-period distribution,
  random entry times. Easy to explain.

Pitfalls: permuting returns removes trend *and* volatility clustering, so the null is
"i.i.d. market"; a trend follower can look significant simply because real markets
trend. Removing the long-run drift (detrending) is needed so a long-biased strategy is
not credited with the market's rise. **[verify]** Masters' exact OHLC permutation
recipe against his text before implementing the price-path variant.

## 5. Reality Check and SPA — White (2000), Hansen (2005)

Test whether the *best* of many rules beats a benchmark, using the stationary bootstrap
on the matrix of excess returns. Hansen's SPA studentises and discounts clearly poor
rules, so it does not lose power when junk rules are added (White's RC does). Romano &
Wolf's StepM identifies *which* rules survive. The `arch` package implements `SPA`,
`StepM` and `MCS` **[verify]**.

## Decision

| Method | When it runs | Default |
|---|---|---|
| PSR, MinTRL | Every run | Always |
| DSR | Whenever more than one configuration has been evaluated | `N` = configurations recorded for this strategy across all runs; effective N estimated from the average correlation of trial returns; shown with raw-N and effective-N values |
| PBO (CSCV) | After a grid optimisation or walk-forward with ≥ 10 configurations | S = 10 |
| Returns permutation + random-entry | Every `bt validate` | 2,000 permutations, detrended |
| Masters price-path permutation | Opt-in | 200 re-runs |
| SPA | After a grid optimisation | via stationary bootstrap, 2,000 resamples |

- A **trial ledger** per strategy (`strategies/<name>/trials.jsonl`) records every
  configuration ever backtested, so DSR's `N` is honest across sessions.
- Explanation wording: PSR/DSR are reported as probabilities ("72% chance the true
  Sharpe is above zero after accounting for 40 variants tried"), never as pass/fail.

## Known-answer tests

- PSR with `SR = SR*` → 0.5. Normal returns (γ3 = 0, γ4 = 3): denominator is
  `√(1 + SR²/2)`.
- DSR with `N = 1` equals PSR(0) by definition (handled as a special case, since
  `Φ⁻¹(0)` is undefined).
- `SR0` increases with `N` and with `V`; spot value for N = 100, V = 1: 2.5306 (computed)
  (also compare with the paper's own example when its full text is available).
- PBO on N pure-noise configurations ≈ 0.5; PBO when one configuration has a real,
  persistent edge ≈ 0.
- Permutation p-value for a random strategy is uniform on [0, 1] over many seeds;
  for a strategy with look-ahead it is ≈ 1/(B + 1).
- SPA p-value on all-noise rules is not small; with one genuinely superior rule it is.

## Sources

- Bailey, D. & López de Prado, M. (2012). The Sharpe ratio efficient frontier. *Journal of Risk* 15(2).
- Bailey, D. & López de Prado, M. (2014). [The deflated Sharpe ratio](https://papers.ssrn.com/abstract=2460551). *JPM* 40(5).
- Bailey, Borwein, López de Prado & Zhu (2017). [The probability of backtest overfitting](https://papers.ssrn.com/abstract=2326253). *J. Computational Finance* 20(4); [PDF](https://carmamaths.org/jon/backtest2.pdf).
- White, H. (2000). A reality check for data snooping. *Econometrica* 68(5).
- Hansen, P. (2005). [A test for superior predictive ability](https://typeset.io/pdf/a-test-for-superior-predictive-ability-1fbgz05jht.pdf). *JBES* 23(4).
- Aronson, D. (2006). *Evidence-Based Technical Analysis*, Wiley. Masters, T. *Permutation and Randomization Tests for Trading System Development*.
- Implementation references: [quantstrat `deflatedSharpe`](https://rdrr.io/github/braverock/quantstrat/man/SharpeRatio.deflated.html);
  [CXO Advisory on data-snooping methods](https://www.cxoadvisory.com/big-ideas/methods-for-mitigating-data-snooping-bias/).
