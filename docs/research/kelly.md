# Kelly criterion

Kelly is a **sizing** analysis, not a validity test: given the strategy's return
distribution, what bet size maximises long-run compound growth, and how punishing is
over-betting? (Kelly 1956; Thorp 1969, 2006.)

## Formulas

- **Binary bet** (win probability `p`, lose `q = 1−p`, win/loss payoff ratio `b`):
  `f* = p − q/b`.
- **General discrete outcomes** (the right form for a trade list): choose `f` to maximise
  `G(f) = mean( ln(1 + f·r_i) )` over per-trade returns `r_i` (as a fraction of capital
  risked at f = 1). Solved numerically on `f ∈ [0, f_max)` where `f_max = 1/|worst r_i|`.
  The binary formula is a poor approximation when wins and losses vary in size.
- **Continuous approximation** (return series): `f* = (μ − r) / σ²` with per-period mean
  `μ`, risk-free `r`, variance `σ²`. Growth rate `g(f) = r + f(μ − r) − f²σ²/2`, maximum
  at `f*`, back to the risk-free rate at `2f*`, negative beyond.
- **Multi-asset / multi-strategy**: `F* = Σ⁻¹(μ − r)` (same form as mean-variance with
  risk aversion 1).
- **Fractional Kelly** `c·f*`: under the continuous model, growth is `c(2 − c)` of the
  maximum excess growth and volatility is `c` of full Kelly's — half Kelly keeps 75% of
  the growth for half the volatility.
- Useful drawdown result under the continuous model: at fraction `c` of Kelly, the
  probability of ever falling to a fraction `x` of current wealth is `x^(2/c − 1)`
  (full Kelly: 50% chance of a 50% drawdown). **[verify]** against Thorp (2006).

## Pitfalls found

- **Estimation error dominates.** `f*` depends on the mean return, the worst-estimated
  input (errors in means matter roughly an order of magnitude more than errors in
  variances — Chopra & Ziemba 1993). The plug-in estimate is biased toward over-betting.
- Over-betting is asymmetrically bad: at `2f*` growth is zero; under-betting costs little.
- Backtest returns are optimistically biased, so backtest Kelly is an **upper bound**.
- Fat tails and skew (short options, mean reversion) break the continuous approximation;
  it over-states `f*`. Use the empirical log-growth maximisation for those.
- Fractional Kelly is justified as shrinkage of an uncertain estimate, and (MacLean,
  Thorp, Ziemba 2010; Davis & Lleo) is only exactly optimal under lognormal assumptions.
- Kelly assumes reinvestment and divisible bets; leverage limits, margin and borrowing
  costs cap usable `f`.

## Decision

- Compute three estimates and show them side by side: binary formula (for intuition),
  empirical log-growth optimum from trades, continuous formula from bar returns.
- **Bootstrap `f*`** (reusing the stationary bootstrap) and report its 5th–95th
  percentile range. Recommend the conservative end: default recommendation =
  `min(half of point estimate, 25th-percentile bootstrap f*)`, capped by the leverage limit.
- Plot the growth-versus-leverage curve `G(f)` from the empirical returns with markers
  at quarter, half, full and 2× Kelly, plus expected max drawdown at each from Monte Carlo.
- If `f* ≤ 0` say plainly that the strategy has no edge to size.
- For options strategies, express `f` relative to maximum loss (defined-risk) or margin
  requirement (undefined-risk), and state which.
- Express results in terms the user can act on: "risk X% of capital per trade" or
  "run at Y× the backtested position size".

## Known-answer tests

- Coin flip `p = 0.6`, even payoff: `f* = 0.2`; numeric optimiser agrees to 1e-4.
- `p = 0.5`, `b = 2`: `f* = 0.25`.
- Continuous: `μ − r = 0.08`, `σ = 0.20` → `f* = 2.0`; `g(2f*) = r`.
- Half Kelly gives 75% of full-Kelly excess growth in the continuous formula.
- No-edge series (`μ = r`): `f* = 0`. Negative-edge trades: optimiser returns 0.
- Empirical optimiser never returns `f ≥ 1/|worst loss|`.

## Sources

- Kelly, J. (1956). A new interpretation of information rate. *Bell System Technical Journal*.
- Thorp, E. (2006). The Kelly criterion in blackjack, sports betting and the stock market.
  *Handbook of Asset and Liability Management*.
- MacLean, Thorp & Ziemba (2010). [Good and bad properties of the Kelly criterion](https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf).
- Ziemba et al., [Kelly chapter (Springer)](https://www.maths.ed.ac.uk/mckinnon/blackouts/StochOptFinanceAndEnergySpringer/Chap1_KellyZiemba.pdf);
  [Davis & Lleo, fractional Kelly](https://him-application.uni-bonn.de/uploads/media/DavisLleoKellyChapter.pdf);
  [arXiv 2503.17927](https://arxiv.org/html/2503.17927v1) (estimation error and shrinkage).
- Chopra, V. & Ziemba, W. (1993). The effect of errors in means, variances and
  covariances on optimal portfolio choice. *Journal of Portfolio Management*.
