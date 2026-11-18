# Replication results: engine and exact method against the paper

Produced by `strategies/regime_optimal/replicate_tables.py` and `strategies/regime_optimal/engine_vs_paper.py`. Paper values are from Tables 2, 3, 5 and 6 of Zakamulin (2026). Data: Kenneth French's data library (CRSP 202609 release), sample cut at 2025-12-31. See `strategies/regime_optimal/spec.md` for assumptions.

## A. The paper's exact method on monthly data

```
Monthly US market excess return: 1926-07 to 2026-09 (1203 months). Source: Kenneth French data library.

TABLE 2 (two-state, total US market). Out-of-sample annualised Sharpe, weights held fixed after the training window.
train end | TSM paper  TSM here | OPT paper  OPT here | wBe paper  wBe here
  1968-12 |     0.413     0.413 |     0.559     0.558 |      0.05      0.05
  1973-12 |     0.422     0.421 |     0.597     0.596 |     -0.01     -0.01
  1978-12 |     0.477     0.476 |     0.647     0.646 |      0.00     -0.00
  1983-12 |     0.497     0.497 |     0.666     0.664 |      0.01      0.01
  1988-12 |     0.567     0.566 |     0.734     0.732 |      0.05      0.05
  1993-12 |     0.530     0.529 |     0.709     0.707 |      0.04      0.04
  1998-12 |     0.459     0.458 |     0.631     0.629 |      0.05      0.05
  2003-12 |     0.494     0.492 |     0.727     0.725 |      0.05      0.01

TABLE 5 (four-state, total US market): DSM vs OPT
train end | DSM paper  DSM here | OPT paper  OPT here | weights paper (Bu,Co,Be,Re) | weights here
  1968-12 |     0.504     0.503 |     0.625     0.624 | (1.0, 0.61, 0.01, 0.09) | (1.00,0.61,0.01,0.09)
  1973-12 |     0.520     0.519 |     0.668     0.667 | (1.0, 0.5, -0.1, 0.11) | (1.00,0.50,-0.10,0.11)
  1978-12 |     0.568     0.567 |     0.718     0.717 | (1.0, 0.45, -0.13, 0.17) | (1.00,0.48,-0.13,0.17)
  1983-12 |     0.557     0.557 |     0.690     0.689 | (1.0, 0.31, -0.11, 0.19) | (1.00,0.31,-0.11,0.19)
  1988-12 |     0.603     0.602 |     0.714     0.713 | (1.0, 0.27, -0.08, 0.21) | (1.00,0.27,-0.08,0.21)
  1993-12 |     0.590     0.589 |     0.763     0.762 | (1.0, 0.45, -0.11, 0.24) | (1.00,0.45,-0.11,0.24)
  1998-12 |     0.495     0.494 |     0.635     0.634 | (1.0, 0.38, -0.09, 0.22) | (1.00,0.38,-0.09,0.22)
  2003-12 |     0.507     0.505 |     0.735     0.733 | (1.0, 0.41, -0.14, 0.23) | (1.00,0.41,-0.14,0.23)

TABLE 3 (two-state) and TABLE 6 (four-state), four US portfolios, training 1926-07 to 2003-12, evaluation 2004-01 to 2025-12
        |       TSM p/h |       OPT p/h |     wBe p/h |       DSM p/h |      OPT4 p/h
  Large | 0.553/ 0.551 | 0.790/ 0.787 |  0.13/ 0.13 | 0.566/ 0.564 | 0.756/ 0.754
  Small | 0.074/ 0.074 | 0.366/ 0.368 |  0.31/ 0.31 | 0.329/ 0.324 | 0.394/ 0.393
  Value | 0.689/ 0.097 | 0.856/ 0.529 |  0.03/ 0.27 | 0.742/ 0.245 | 0.814/ 0.573
 Growth | 0.092/ 0.684 | 0.521/ 0.851 |  0.27/ 0.03 | 0.237/ 0.738 | 0.564/ 0.810

NOTE on Value/Growth: with French's labels (Value = Hi 20 book-to-market, Growth = Lo 20) the rows come out nearly swapped
relative to the paper (its Value is close to our Growth and vice versa). Large and Small match well. Cause not determined.

```

```
SENSITIVITY (not in the paper): trailing 12-month return COMPOUNDED instead of summed (the default above)
  train end 1968-12: TSM 0.300, OPT 0.502, w_bear 0.10
  train end 2003-12: TSM 0.379, OPT 0.676, w_bear 0.11
```

## B. The same strategy through the backtest engine (zero costs, no cash interest)

```
TABLE 2 on the engine: two regimes, total US market, zero costs
train end | TSM paper engine(m) engine(d) | OPT paper engine(m) engine(d)
  1968-12 |     0.413     0.410     0.399 |     0.559     0.559     0.530
  1973-12 |     0.422     0.418     0.401 |     0.597     0.595     0.559
  1978-12 |     0.477     0.468     0.443 |     0.647     0.639     0.597
  1983-12 |     0.497     0.497     0.456 |     0.666     0.667     0.604
  1988-12 |     0.567     0.554     0.508 |     0.734     0.719     0.647
  1993-12 |     0.530     0.523     0.467 |     0.709     0.706     0.613
  1998-12 |     0.459     0.448     0.398 |     0.631     0.622     0.526
  2003-12 |     0.494     0.485     0.425 |     0.727     0.728     0.606

TABLE 5 on the engine: four regimes, total US market, zero costs
train end | DSM paper engine(m) engine(d) | OPT paper engine(m) engine(d)
  1968-12 |     0.504     0.502     0.484 |     0.625     0.625     0.584
  1973-12 |     0.520     0.518     0.491 |     0.668     0.664     0.611
  1978-12 |     0.568     0.560     0.521 |     0.718     0.706     0.648
  1983-12 |     0.557     0.556     0.500 |     0.690     0.685     0.612
  1988-12 |     0.603     0.588     0.530 |     0.714     0.692     0.623
  1993-12 |     0.590     0.585     0.512 |     0.763     0.757     0.655
  1998-12 |     0.495     0.490     0.425 |     0.635     0.639     0.540
  2003-12 |     0.507     0.530     0.462 |     0.735     0.738     0.619

(m) = Sharpe of the engine equity curve's monthly returns, annualised with sqrt(12), as in the paper; (d) = the engine's own daily Sharpe.
```

## C. The validated run

`run/` is the complete run folder of the validated run (equity curve, fills, `validation.json`, explanation and narrative; 1.5 MB).
`strategies/regime_optimal/record_in_library.py` copies it into your `runs/` folder, so the dashboard can open it, and records the
paper in your library (claims as the paper states them, the run linked, status "partly replicated"). To regenerate the run:

```bash
.venv/bin/python strategies/regime_optimal/make_data.py
.venv/bin/bt validate strategies/regime_optimal/strategy.py --start 1968-12-31 --end 2025-12-31 --no-cash-interest --risk-free 0 --benchmark FFMKT --paths 2000
```

Default project costs apply (no commission, 1 basis point slippage per fill, an assumption). Total return 2,909.4%, 6.2% a year,
engine Sharpe 0.53 (0.559 on monthly returns), worst fall -34.0% against -59.2% for the benchmark, 25 trades.

## D. Second pass: Tables 4, 7, 8 and Figures 1-2 (exact method)

Reproduce with `.venv/bin/python -I strategies/regime_optimal/replicate_extra.py --figures docs/replications/regime-optimal/figures`
(complete output: `tables_4_7_8_output.txt`). All Sharpe ratios are annualised, weights are estimated on the training window and held fixed.

| Table | Result | Evidence |
|---|---|---|
| 4 (14 countries, two states) | **Reproduced exactly** when the evaluation window ends 2024-12: mean absolute difference 0.000 for TSM and for OPT, all 14 Bear weights equal to two decimals; average 0.054 / 0.295 as in the paper | the weights match to two decimals for every country also with the window ending 2025-12, so the training data agree; the paper's country series evidently stop in 2024-12 although its text says 2025-12 |
| 7 (14 countries, four states) | **Reproduced closely** with the window ending 2024-12: mean absolute difference 0.007 (DSM) and 0.004 (OPT), largest single gap 0.057 (DSM) | most weights identical; Italy, Japan, Spain and Sweden differ by 0.02-0.10 in one or two weights (the in-sample DSM optimiser can settle on a different point) |
| 4 and 7 with the window ending 2025-12, as the paper states | Not matched: mean absolute difference 0.042 (TSM), 0.060 (OPT) in Table 4 | same weights, different evaluation months |
| 8 (18 diversified datasets) | **Direction and size reproduced, numbers not.** TSM within 0.008 on average; OPT 0.543 against 0.506 (mean absolute difference 0.037), DSM 0.521 against 0.496, four-state OPT 0.655 against 0.628 | OPT beats TSM in all 18 datasets and four-state OPT beats DSM in all 18, as the paper says; datasets 8, 10 and 13 are the largest misses (OPT 0.562 against 0.494, 0.551 against 0.412, 0.517 against 0.384) |
| Figures 1, 2 | Reproduced: the first point of Figure 1 is 0.558 (OPT) and 0.413 (TSM), Table 2's 0.559 and 0.413; OPT is above its benchmark at every start month 1969-01 to 2012-12 and the gap widens, as the paper describes | `figures/figure1_*.html`, `figure2_*.html`, opened in a browser, light and dark |

What I tried for Table 8 and could not settle: weights pooled across assets instead of per asset (no better: dataset 13 gives 0.614),
dataset 5 cut to 25 portfolios (35 in French's file; no better), evaluation ending 2025-06 or 2024-12 (closer for DSM and four-state OPT, not for
OPT). The remaining gap is therefore not explained by what the paper states; I did not tune anything to close it.

### Assumptions added in this pass

1. Country returns are French's Dollar-return country market returns (first block of the `.Dat` files, `Mkt` column), less the US one-month
   Treasury bill rate (the paper does not name a risk-free rate for them; with raw returns the difference from the paper is 0.10-0.20).
2. Table 8 returns are excess over the same rate, equal-weighted across the portfolios of a dataset, regimes and weights per asset (equation 21).
3. The diversified DSM mixing coefficient is estimated per asset by maximising the in-sample Sharpe ratio, as in the single-asset case.
4. Dataset 5 is used with all 35 columns of French's file; the paper states 25.
5. The country data differ in vintage from the paper's (see Table 4).
