# Option pricing, volatility surface, synthetic chains, gamma surfaces

IBKR supplies no history for expired options, so option prices in backtests are
**modelled**. This write-up fixes the model and is frank about its accuracy.

## 1. Pricing model

Black-Scholes-Merton with continuous dividend yield `q`:

```
d1 = [ln(S/K) + (r − q + σ²/2)·T] / (σ·√T)        d2 = d1 − σ·√T
Call = S·e^(−qT)·Φ(d1) − K·e^(−rT)·Φ(d2)
Put  = K·e^(−rT)·Φ(−d2) − S·e^(−qT)·Φ(−d1)

Delta(call) = e^(−qT)·Φ(d1)          Delta(put) = −e^(−qT)·Φ(−d1)
Gamma = e^(−qT)·φ(d1) / (S·σ·√T)                         (same for calls and puts)
Vega  = S·e^(−qT)·φ(d1)·√T
Theta(call) = −S·e^(−qT)·φ(d1)·σ/(2√T) − r·K·e^(−rT)·Φ(d2) + q·S·e^(−qT)·Φ(d1)
```

- `T` in years, calendar-day count / 365 by default; intraday uses fractional days.
- `r`: 3-month Treasury bill yield series (Yahoo `^IRX`), as of each date.
- `q`: trailing 12-month dividend yield of the underlying.
- **American exercise**: US equity and ETF options are American. For calls with small
  dividends the early-exercise premium is negligible; for deep in-the-money puts it is
  not. v1 prices with Black-Scholes and handles early exercise by rule (below); a
  binomial or Bjerksund-Stensland price is an optional refinement.
- Implied volatility solver (for calibration to live quotes): Brent's method on price,
  bounded [0.01, 5.0].

## 2. Volatility surface (the main source of error)

Flat volatility is not acceptable: equity index puts trade at much higher implied
volatility than calls (skew), and VIX overstates at-the-money volatility because it
includes that skew.

Model for implied volatility at date `t`, time to expiry `T`, strike `K`:

```
σ(t, T, K) = ATM(t, T) · [ 1 + skew(T)·m + curv(T)·m² ]      m = ln(K/F) / (ATM·√T)   (standardised moneyness)
ATM(t, T)  = level(t) · term(T)
```

- `level(t)`:
  - index products with a volatility index (SPY/SPX → VIX, QQQ → VXN, IWM → RVX):
    `level = a · VIX_t/100`, with `a < 1` to remove the skew premium;
  - other underlyings: `level = b · RV_t`, where `RV_t` is trailing 21-day realised
    volatility and `b` the implied-to-realised ratio.
- `term(T)`: power law in `T` relative to 30 days, with exponent tied to the level
  (high volatility → inverted term structure).
- `skew(T)`, `curv(T)`: negative slope, positive curvature, scaling roughly with `1/√T`.
- **Calibration**: `a` or `b`, the skew, curvature and term parameters are fitted to
  **today's live IBKR chain** for that underlying (several expiries, strikes around
  spot), then applied historically. Defaults per asset class exist for when no chain is
  available.
- Floors and caps keep `σ` in [5%, 300%] and total variance non-decreasing in `T`
  (no calendar arbitrage).

Alternative considered: **SVI** (Gatheral; arbitrage-free conditions in Gatheral &
Jacquier 2014): total variance `w(k) = a + b·(ρ(k − m) + √((k − m)² + σ²))`. It is the
right tool for fitting a full observed chain, but we have only one live snapshot per
underlying, so five free parameters per expiry would be fitted once and frozen. The
simpler quadratic-in-standardised-moneyness form is preferred for v1; the surface is
behind an interface so SVI (or real historical surfaces) can replace it.

**Dynamics**: because the surface is expressed in standardised moneyness, the smile
moves with spot ("sticky moneyness"). That is an assumption, not a fact; real markets
sit between sticky-strike and sticky-delta.

## 3. Synthetic chain and trading rules

- **Expiries**: standard monthlies (third Friday) for all; weeklies (Fridays) and
  dailies only for underlyings that list them, from a start date in configuration.
- **Strikes**: grid by price level ($1 for most ETFs, wider at higher prices, $5 for
  large indices) — configuration per underlying, checked against the live chain.
- **Selection helpers**: by days to expiry (nearest to target, min/max) and by delta,
  strike offset or percent moneyness.
- **Bid/ask**: `half-spread = max(minimum tick, pct · mid)` with `pct` rising for far
  out-of-the-money and short-dated contracts; calibrated to the live chain. Opening
  fills pay the half-spread; multi-leg orders pay a configurable fraction of the summed
  leg spreads.
- **Multiplier** 100; **commission** per contract from the cost config.
- **Expiry**: in-the-money by ≥ $0.01 is exercised/assigned into shares (physical) or
  cash (index); out-of-the-money expires worthless.
- **Early assignment (rule-based)**: a short call is assigned on the day before
  ex-dividend if its remaining time value is less than the dividend; a short put is
  assigned if deep in the money with time value below a small threshold.
- **Margin**: defined-risk positions reserve maximum loss; short stock-covered and
  cash-secured positions reserve the stock or cash; naked shorts use a Reg-T style
  approximation **[verify]** against IBKR's published margin rules.

## 4. How accurate is this?

- No independent study quantifying the error of VIX/Black-Scholes synthetic option
  backtests was found. Vendor claims ("within $0.05") are marketing. Practitioners
  agree: fine for exploring structure and volatility dynamics, **not reliable for
  judging profitability of strategies that depend on skew, short expiries or events**
  (earnings).
- We therefore measure it ourselves: the **calibration report** compares modelled and
  live IBKR mid prices across the chain and reports error by moneyness and expiry.
  Every options run shows this error next to its results.
- Sensitivity: every options backtest is re-run with level ±10% and skew ±25%;
  if the conclusion flips, the explanation says the result is not robust to pricing.
- Known blind spots, stated in each options report: earnings volatility ramps and
  crush, single-name skew changes, liquidity gaps in stress, pin risk.

## 5. Gamma surfaces (dashboard, 3D)

**(a) Contract gamma surface.** Axes: strike (or moneyness) × days to expiry;
height = Black-Scholes gamma using the surface volatility at each point. Available for
any backtest date (modelled) and for today (live IBKR chain, where gamma is recomputed
from each contract's implied volatility). Shows the characteristic ridge at the money
that sharpens as expiry approaches. Option to display **dollar gamma**
`Γ·S²/100` (P&L curvature per 1% move) so values compare across underlyings.

**(b) Position gamma surface.** For a strategy's open position on a chosen date:
axes underlying price (±20% around spot) × days forward (today → last expiry);
height = `Σ quantity·multiplier·Γ_leg` re-priced at each grid point, legs dropping out
as they expire. Companion surfaces with the same axes for delta, theta, vega and P&L.

Rendering: Plotly `Surface`, computed vectorised on a ~60 × 60 grid; numerical care
near `T → 0` (grid stops at a minimum of ~0.5 day).

## Decision

Black-Scholes-Merton + calibrated parametric surface + rule-based exercise for v1,
with three interfaces kept swappable: pricer, surface, chain source (synthetic or real
historical data — also the plug-in point for QuantConnect/paid option data).

## Known-answer tests

- Textbook value: S = 100, K = 100, r = 5%, q = 0, σ = 20%, T = 1 → call ≈ 10.4506,
  put ≈ 5.5735.
- Put-call parity `C − P = S·e^(−qT) − K·e^(−rT)` to 1e-10 over a grid.
- Greeks match finite differences of price; call delta − put delta = `e^(−qT)`.
- Gamma is maximal near the money and, at the money, grows as `T` shrinks; surface
  values equal the closed form at spot-checked points; position gamma of a long
  straddle is positive everywhere, of an iron condor negative between the short strikes.
- Implied-volatility solver round-trips price → σ → price.
- Surface: total variance non-decreasing in `T`; `σ` within bounds; put-side σ above
  call-side for index defaults.
- Expiry: a call 1¢ in the money converts to 100 shares at the strike; covered call
  assigned → shares removed, cash = strike × 100.

## Sources

- Black & Scholes (1973); Merton (1973).
- Gatheral, J. (2006). *The Volatility Surface*, Wiley. Gatheral & Jacquier (2014),
  [Arbitrage-free SVI volatility surfaces](https://arxiv.org/pdf/1204.0646).
- Derman, E. (1999). Regimes of volatility (sticky strike / sticky delta).
- Hull, J. *Options, Futures, and Other Derivatives* (textbook test values).
- Practitioner views on synthetic option backtests: [Wealth-Lab OptionSynthetic](https://www.wealth-lab.com/Support/ApiReference/OptionSynthetic),
  [EliteTrader thread 1](https://www.elitetrader.com/et/threads/backtesting-options-strategy-without-option-historical-data.254414/),
  [EliteTrader thread 2](https://elitetrader.com/et/threads/creating-synthetic-option-prices-for-backtest.372787),
  [Nasdaq: 7 pitfalls](https://www.nasdaq.com/articles/avoid-these-7-options-backtesting-pitfalls-2019-07-01).
