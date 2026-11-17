# Sharpe-optimal regime-dependent allocation (replication)

**Paper:** Valeriy Zakamulin, "Rethinking Trend Following: Optimal Regime-Dependent Allocation", working paper, University of Agder,
9 March 2026. Library id: `rethinking-trend-following-optimal-2026`. All numbers below marked "paper" were read from the full text
(PDF supplied by the account holder), page numbers in brackets.

## Rules (as the paper states them)

- Excess return `r_t` of a risky asset, regime `s(t-1)` observed at the end of the previous month, weight `w_s` in [-1, 1] in the
  risky asset, the rest in the risk-free asset: `R_t = w_{s(t-1)} r_t` (p. 5, eq. 1).
- **Two regimes** (p. 13): Bull if the trailing 12-month excess return is positive, Bear otherwise.
- **Four regimes** (p. 18-19): slow signal = sign of the trailing 12-month excess return, fast signal = sign of the latest month's
  excess return; Bull (slow +, fast +), Correction (+, -), Bear (-, -), Rebound (-, +).
- **Optimal weights** (p. 8-9, eqs. 16-19): with `m_s = mean(r | s)` and `q_s = mean(r^2 | s)` estimated on a training window,
  `score_s = m_s / q_s`, `c = max score`, `w_s = max(score_s / c, -1)`. The regime with the best score gets 1.
- **Benchmarks:** TSM = +1 in Bull, -1 in Bear (p. 13). DSM (Goulding, Harvey and Mazzoleni 2023) = Bull +1, Bear -1, Correction and
  Rebound weights in [-1, 1] chosen to maximise the Sharpe ratio (p. 19).
- **Test design** (p. 14, 20): training windows start July 1926 and end 1968-12, 1973-12, ..., 2003-12; weights estimated once on the
  training window and held fixed through December 2025; the evaluation Sharpe ratio is annualised, on monthly returns.
- **Data (paper):** Kenneth French's data library, monthly value-weighted US market, July 1926 - December 2025; risk-free = one-month
  T-bill (p. 11).

## What was built

| Piece | File |
|---|---|
| Strategy for the engine | `strategy.py` (`mode` opt / tsm / dsm, `states` 2 / 4, `train_end`) |
| Data for the engine | `make_data.py`: French **daily** Mkt-RF as an index of excess returns, symbol `FFMKT` |
| Exact-method cross-check on monthly data | `replicate_tables.py` (Tables 2, 3, 5, 6) |
| Engine versus paper, all training windows | `engine_vs_paper.py` (Tables 2 and 5) |
| Known-answer tests | `tests/test_regime_optimal.py` |
| Record the paper, claims and run in your library | `record_in_library.py` |

Why an excess-return index: holding a fraction `w` of equity in an index built from excess returns, with the rest in cash earning
nothing, gives exactly `R = w r`, so the engine's Sharpe ratio equals the paper's definition (run with `--risk-free 0
--no-cash-interest`). One bar per trading day, with open = previous close so that a fill "at the next open" is a fill at the last
close; the weight is set at the close of the last business day of the month.

## Assumptions I had to make (the paper does not settle them)

1. **Trailing 12-month return = the SUM of the 12 monthly excess returns.** The paper says only "trailing excess return over the
   previous 12 months". Compounding gives different results (TSM Sharpe 0.300 against the paper's 0.413 for the first window); the sum
   reproduces the paper's TSM values to about 0.002, so this is inferred from its numbers, not stated.
2. **No regime with a positive score = no investment** (weights 0). The paper's normalisation needs a positive maximum; this case did not occur in any reported table.
3. **A regime never seen in the training window gets weight 0** (did not occur either).
4. **The four-state DSM weights are found by numerical optimisation** (box-constrained, four starting points); the paper does not say how.
5. **Timing in the engine:** weights set at the close of the last weekday of the month; if that day was a market holiday the update happens
   on the first bar of the next month (a handful of months).
6. **Data vintage:** the paper used data through December 2025; the library file used here (CRSP 202609 release) has been revised and
   extends to September 2026. The sample is cut at 2025-12-31; small differences from the paper's numbers (a few thousandths) can come from revisions.
7. **Costs:** none in the paper. The headline replication runs use zero costs; the validated run uses the project's default (no
   commission, 1 basis point of slippage per fill, an assumption).

## What the paper claims (for the library, abstract and results as stated)

See `docs/replications/regime-optimal/claims.md` (quoted from the paper with page numbers).

## Not replicated

- Table 4 and Table 7 (14 developed international markets, Jan 1975 - Dec 2025) and Table 8 (18 diversified portfolio datasets):
  not attempted; the data exist in the same library but this was a first replication of the single-asset results.
- Figures 1 and 2 (rolling out-of-sample Sharpe ratios) were not reproduced.
- The paper's Table 3 / Table 6 "Value" and "Growth" rows match our Growth and Value rows (see `replicate_tables.py` output): the labels
  appear swapped in the paper; not confirmed with the author.
