# Market intraday momentum (replication)

**Paper:** Lei Gao, Yufeng Han, Sophia Zhengzi Li, Guofu Zhou, "Market Intraday Momentum", June 2017 working paper. Library id `market-intraday-momentum-2017`.
All paper values are in `docs/replications/intraday-momentum/claims.md`, with page numbers.

## Rules (as the paper states them)

1. Split each trading day 09:30-16:00 New York time into 13 half-hours; `r_j = p_j / p_(j-1) - 1`, `p_0` = the previous day's 16:00 price (eq. 1).
2. Predictor: the first half-hour return `r_1` (previous close to 10:00) and the twelfth `r_12` (15:00 to 15:30).
3. **Timing strategy** (eqs. 4-5): at 15:30 go long if the signal is positive and short otherwise (signal `r_1`), or long only if `r_1 > 0` and `r_12 > 0`, short if both `<= 0`, flat otherwise; close at 16:00. Annualised by multiplying the daily mean by 252.
4. **Mean-variance investor** (eqs. 6-8): weight `w = rhat / (gamma sigma2)` on the market in the last half-hour, `gamma = 5`, weight in [-0.5, 1.5], the rest in T-bills; `rhat` from a recursive regression of `r_13` on the signals, benchmark the historical-average forecast; `CER = U2 - U1`.
5. **Predictability** (eqs. 2-3): `r_13 = a + b r_1 + e`, Newey-West t-statistics; out-of-sample `R2_OS = 1 - sum(r13 - rhat)^2 / sum(r13 - rbar)^2`, first estimate on data to 1997-12-31, adding one month at a time.

## What was built

| Piece | File |
|---|---|
| Bars to p0..p13 and r1..r13 (any 1-30 minute bars, DST-safe, half-days dropped) | `halfhours.py` |
| Timing signals and the paper's summary statistics | `signals.py` |
| Regressions, Newey-West, recursive forecasts, `R2_OS` | `predict.py` |
| Mean-variance weight, utility, CER | `sizing.py` |
| Exact-method Tables 1, 2, 6, 7, 10 beside the paper's values | `replicate_tables.py` |
| Engine strategy (`bt check`, `bt run`, `bt validate`, dashboard) | `strategy.py` |
| Planted-relation check of the table code | `synthetic_demo.py` |
| Figures (equity and drawdown, volume profile, recursive coefficients) | `make_figures.py` and `backtester/viz/` |
| Library record | `record_in_library.py` |
| Tests | `tests/test_intraday_*.py`, `tests/test_viz.py`, `tests/test_costs_regulatory.py` |

Run the engine strategy with `--fill close --no-cash-interest` (and `--max-leverage 1.5` for `mode="mean_variance"`): the entry fills at the 15:30
price and the exit at the 16:00 close, as in the paper.

## DATA: the paper's sample is not available

The paper uses SPY ticks from TAQ, 1993-02-01 to 2013-12-31 (paid academic database). **What was tested here is the 1,000 most recent 30-minute SPY bars
the IBKR connector returns (2026-07-31 to 2026-11-17, 76 complete days).** The connector limits one request to 1,000 bars and cannot page back, so a longer
30-minute history cannot be obtained through it. The result on that window is a *check that the code runs on real data*, not a replication and not
evidence for or against the paper (75 daily observations carry almost no statistical power for an R2 of about 1.6%). The code runs unchanged on any
1-minute or 30-minute file (`--file`), so the paper's tables can be reproduced when such a file for 1993-2013 is supplied.

## Assumptions the paper does not settle

1. **Newey-West lag:** `floor(4 (T/100)^(2/9))` (the Newey-West 1994 rule).
2. **Recursive regression:** re-estimated once a month, on all earlier months only; the first estimate uses data before the start of the out-of-sample period.
3. **Variance forecast** in eq. 6: the residual variance of the training regression (the paper says only "estimated from the recursive regressions").
4. **The 500-trade rule** cannot be applied to bars; a day is kept only if every half-hour has at least one bar, and half-days are dropped.
5. **Risk-free return in the last half-hour:** zero (half an hour of T-bill interest).
6. **The 10:00 price** is the close of the 09:30-10:00 bar; bar timestamps are start times (`--label end` for vendors that stamp the end).
7. **Table 6 statistics:** kurtosis is raw (not excess), the success rate counts days with a zero or positive return, Sharpe ratios do not subtract a risk-free rate (6.67 / 6.19 = 1.08).
8. **Out-of-sample coefficient rows of Table 1** (the paper reports t-statistics of the recursive estimates) are not reproduced; only `R2_OS`.

## Costs (IBKR, per the account holder)

Commission USD 0.00 (IBKR Lite). Sell-side SEC fee USD 0.0000206 per dollar sold; FINRA trading activity fee (IBKR shows 0.00 during a fee holiday to 2026-12-31;
the usual USD 0.000166 per share with an USD 8.30 cap is used, unconfirmed); audit-trail and clearing fees per share. All in `config/costs.toml` with sources and dates.
The spread is measured from IBKR quotes; the figure used is stated in `results.md`. The engine charges `slippage_bps` on **both** fills, the exact-method Table 10 only
at the 15:30 entry (the 16:00 close auction pays no spread, as in the paper), so engine costs are higher.
