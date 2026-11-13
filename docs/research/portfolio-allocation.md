# Portfolio allocation: Black-Litterman and the other weighting methods

Used inside investment strategies at each rebalance to turn a universe (and optionally
views) into weights. Every input is estimated from data available **at the rebalance
date only**.

## 1. Covariance estimation (shared by all methods)

Sample covariance is noisy and makes optimisers produce extreme weights.
Default: **Ledoit-Wolf shrinkage** (Ledoit & Wolf 2004) on daily returns over a
trailing window (default 252 days), annualised. Alternative: exponentially weighted.
Minimum history: at least 2× as many observations as assets, else fall back to
inverse-volatility weighting with a warning.

## 2. Baseline methods

| Method | Rule | Notes |
|---|---|---|
| Equal weight | `w_i = 1/N` | Hard to beat out of sample (DeMiguel, Garlappi & Uppal 2009); always shown as the comparison |
| Inverse volatility | `w_i ∝ 1/σ_i` | Ignores correlations |
| Risk parity (equal risk contribution) | Solve for `w` with `w_i·(Σw)_i` equal for all `i` | Maillard, Roncalli & Teiletche 2010; convex solve |
| Minimum variance | `min w'Σw` s.t. constraints | No return estimates needed |
| Mean-variance | `max w'μ − (δ/2)·w'Σw` s.t. constraints | Extremely sensitive to `μ`; included mainly to show why Black-Litterman exists |

## 3. Black-Litterman

Black & Litterman (1992); He & Litterman (1999); Idzorek (2005); Meucci; Walters (survey).

**Step 1 — equilibrium (prior) returns by reverse optimisation**

```
Π = δ · Σ · w_mkt
```
`w_mkt` = market-capitalisation weights; `δ` = risk aversion. `δ` is either set
(2.5 is the conventional value) or implied from the benchmark:
`δ = (E[R_m] − r_f) / σ_m²`.

**Step 2 — views**

`P` (K views × N assets), `Q` (K view returns), `Ω` (K × K view uncertainty).
- Absolute view "asset A returns 8%": row of `P` has 1 at A; `Q = 0.08`.
- Relative view "A beats B by 3%": row has +1 at A, −1 at B; `Q = 0.03`.

**Step 3 — posterior**

```
M      = [ (τΣ)⁻¹ + P'Ω⁻¹P ]⁻¹
μ_BL   = M · [ (τΣ)⁻¹Π + P'Ω⁻¹Q ]
Σ_BL   = Σ + M
```
Numerically stable equivalent (no inversion of τΣ):
`μ_BL = Π + τΣP'·(PτΣP' + Ω)⁻¹·(Q − PΠ)`.

**Step 4 — weights**

Unconstrained: `w = (δ·Σ_BL)⁻¹·μ_BL`. With constraints (long-only, caps, fully
invested): feed `μ_BL`, `Σ_BL` to the mean-variance optimiser.

**Choices that sources disagree on**

- `τ` (uncertainty of the prior): 0.025–0.05 is typical; some use `1/T`.
- `Ω`:
  - He-Litterman: `Ω = diag(P·τΣ·P')` — view uncertainty proportional to the variance
    of the view portfolio. With this choice `τ` cancels out of `μ_BL`.
  - Idzorek: the user gives a **confidence 0–100%** per view. Idzorek's original
    procedure solves for each `Ω_k` so that the tilt away from market weights equals
    that percentage of the full-confidence tilt. A widely used closed-form shortcut
    (as in PyPortfolioOpt) is `Ω_k = τ·((1 − c_k)/c_k)·p_k Σ p_k'` **[verify]** that
    this reproduces Idzorek's worked example before relying on it.
- Whether to use `Σ_BL = Σ + M` or just `Σ` when optimising: with **no views**,
  `μ_BL = Π`, and using `Σ` returns exactly `w_mkt`, while using `Σ + M = (1 + τ)Σ`
  returns `w_mkt/(1 + τ)` (He & Litterman's result; identical after normalising to
  fully invested).

**Pitfalls found**

- **Market-cap weights are needed** and must be point-in-time. For ETF universes there
  is no clean "market weight"; options are benchmark weights supplied by the user,
  asset-class market values, or falling back to equal/inverse-vol as the prior (which
  is then no longer an equilibrium argument — say so).
- Views generated from backtested signals are themselves fitted; confidence should
  reflect that (default 50% or lower).
- `δ` and `τ` materially change the output; record them in the run.
- Long-only and cap constraints break the neat closed-form intuition; weights can stick
  at bounds.
- In a backtest, views must be produced by a rule from past data (e.g. momentum rank →
  relative views), or be fixed views stated in the strategy description with their
  date; a discretionary view written today and applied to 2019 is look-ahead.

## Decision

- Implement in-house with NumPy/SciPy (formulas are short); **cross-check against
  PyPortfolioOpt** in tests (dev dependency only).
- Defaults: Ledoit-Wolf covariance, 252-day window; `δ` implied from the benchmark,
  bounded to [1, 10]; `τ = 0.05`; `Ω` via view confidence (Idzorek shortcut), with
  He-Litterman available; long-only, fully invested, per-asset cap 40%.
- View sources: (1) explicit views in the strategy spec; (2) rule-generated views
  (momentum, value or any signal → relative views with confidence from signal strength).
- Prior: user-supplied benchmark weights where available; otherwise inverse-volatility
  weights, labelled as "non-equilibrium prior" in the run.
- Every Black-Litterman backtest is shown against equal weight and against the prior
  portfolio (no views), so the value added by the views is visible.
- Per-rebalance record: prior returns, views, posterior returns, weights — viewable in
  the dashboard.

## Known-answer tests

- No views → posterior equals prior; unconstrained weights equal `w_mkt` (using `Σ`)
  and `w_mkt/(1 + τ)` (using `Σ + M`).
- One view with confidence → 100% (Ω → 0): posterior satisfies `P·μ_BL = Q` exactly.
  Confidence → 0 (Ω → ∞): posterior → prior.
- The two algebraic forms of `μ_BL` agree to 1e-10.
- He-Litterman `Ω`: `μ_BL` unchanged when `τ` changes.
- Reproduce a published worked example (He & Litterman 1999 seven-country example,
  or Idzorek 2005 eight-asset example) from the paper's own input tables **[verify —
  inputs to be taken from the paper's full text]**.
- Results match PyPortfolioOpt's `BlackLittermanModel` on the same inputs.
- Risk parity: risk contributions equal to 1e-6; two-asset case equals inverse volatility.
- Constraint handling: weights sum to 1, respect bounds.

## Sources

- Black, F. & Litterman, R. (1992). Global portfolio optimization. *Financial Analysts Journal* 48(5).
- He, G. & Litterman, R. (1999). The intuition behind Black-Litterman model portfolios. Goldman Sachs.
- Idzorek, T. (2005). A step-by-step guide to the Black-Litterman model.
- Walters, J. (2014). The Black-Litterman model in detail. Meucci, A. (2010). The Black-Litterman approach: original model and extensions.
- Ledoit, O. & Wolf, M. (2004). Honey, I shrunk the sample covariance matrix. *JPM*.
- DeMiguel, Garlappi & Uppal (2009). Optimal versus naive diversification. *RFS*.
- Maillard, Roncalli & Teiletche (2010). The properties of equally weighted risk contribution portfolios. *JPM*.
- [PyPortfolioOpt Black-Litterman documentation](https://pyportfolioopt.readthedocs.io/en/stable/BlackLitterman.html).
