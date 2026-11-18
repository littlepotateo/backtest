# Claimed results of Zakamulin (2026), as the paper states them

Source: the full text (33 pages), read in this project. Page numbers are the paper's own. Quotations are exact; table values are
copied from the tables.

## Abstract (p. 1)

- "optimal regime-dependent allocation delivers economically meaningful and robust improvements in out-of-sample risk-adjusted performance relative to the time-series momentum strategy of Moskowitz, Ooi, and Pedersen (2012) and the dynamic speed momentum strategy of Goulding, Harvey, and Mazzoleni (2023)."
- "These gains persist across assets and portfolio implementations, highlighting the central role of optimal positioning in trend following."

## Statements in the text

- p. 4: "in the standard two-regime setting, the Sharpe-optimal allocation typically implies that Bear-regime exposure should be strongly attenuated relative to the full short position embedded in conventional long-short momentum; empirically, optimal Bear weights are often close to zero and may even be mildly positive."
- p. 4: "in the four-regime setting, OPT delivers systematic improvements relative to DSM."
- p. 16: for the four US portfolios (large, small, value, growth) "the estimated Bear-regime weights are always close to zero or strictly positive, ranging from w_Be = 0.03 for value stocks to w_Be = 0.31 for small-cap stocks."
- p. 17: "in every country, the OPT strategy outperforms the TSM strategy in terms of risk-adjusted performance"; "On average across markets, the Sharpe ratio increases from 0.054 under TSM to 0.295 under OPT."
- p. 24: "On average across markets, the Sharpe ratio increases from 0.192 under DSM to 0.319 under OPT"; "the cross-country average [Bear weight] equal to w_Be = -0.03."
- p. 27-28: "the diversified DSM strategy uniformly outperforms the diversified TSM benchmark across all datasets"; "In all 18 portfolio datasets, the Sharpe ratio difference (DIF) between the OPT strategy and its corresponding benchmark ... is strictly positive."

## Table 2 (p. 15): US total market, two regimes. Out-of-sample annualised Sharpe ratio, evaluation to 2025-12

| Training window ends | TSM | OPT | OPT weights (w_Bu, w_Be) |
|---|---|---|---|
| 1968-12 | 0.413 | 0.559 | (1.00, 0.05) |
| 1973-12 | 0.422 | 0.597 | (1.00, -0.01) |
| 1978-12 | 0.477 | 0.647 | (1.00, 0.00) |
| 1983-12 | 0.497 | 0.666 | (1.00, 0.01) |
| 1988-12 | 0.567 | 0.734 | (1.00, 0.05) |
| 1993-12 | 0.530 | 0.709 | (1.00, 0.04) |
| 1998-12 | 0.459 | 0.631 | (1.00, 0.05) |
| 2003-12 | 0.494 | 0.727 | (1.00, 0.05) |

## Table 3 (p. 17): four US portfolios, two regimes, training to 2003-12, evaluation 2004-01 to 2025-12

| Portfolio | TSM | OPT | (w_Bu, w_Be) |
|---|---|---|---|
| Large | 0.553 | 0.790 | (1.00, 0.13) |
| Small | 0.074 | 0.366 | (1.00, 0.31) |
| Value | 0.689 | 0.856 | (1.00, 0.03) |
| Growth | 0.092 | 0.521 | (1.00, 0.27) |

## Table 5 (p. 21): US total market, four regimes (DSM versus OPT)

| Training window ends | DSM | OPT | OPT weights (Bu, Co, Be, Re) |
|---|---|---|---|
| 1968-12 | 0.504 | 0.625 | (1.00, 0.61, 0.01, 0.09) |
| 1973-12 | 0.520 | 0.668 | (1.00, 0.50, -0.10, 0.11) |
| 1978-12 | 0.568 | 0.718 | (1.00, 0.45, -0.13, 0.17) |
| 1983-12 | 0.557 | 0.690 | (1.00, 0.31, -0.11, 0.19) |
| 1988-12 | 0.603 | 0.714 | (1.00, 0.27, -0.08, 0.21) |
| 1993-12 | 0.590 | 0.763 | (1.00, 0.45, -0.11, 0.24) |
| 1998-12 | 0.495 | 0.635 | (1.00, 0.38, -0.09, 0.22) |
| 2003-12 | 0.507 | 0.735 | (1.00, 0.41, -0.14, 0.23) |

## Table 6 (p. 23): four US portfolios, four regimes

| Portfolio | DSM | OPT | (w_Bu, w_Co, w_Be, w_Re) |
|---|---|---|---|
| Large | 0.566 | 0.756 | (1.00, 0.48, -0.05, 0.25) |
| Small | 0.329 | 0.394 | (1.00, -0.28, -0.05, 0.52) |
| Value | 0.742 | 0.814 | (1.00, 0.62, -0.24, 0.36) |
| Growth | 0.237 | 0.564 | (1.00, 0.23, 0.04, 0.35) |

## Tables 4, 7 and 8 (pp. 18, 25, 29; replicated in the second pass, see results.md section D)

Table 4 (14 countries, two states; training 1975-01 to 2003-12, evaluation to 2025-12 as the paper states): TSM / OPT / wBe
Australia 0.095 / 0.399 / 0.54; Belgium 0.078 / 0.280 / 0.14; France -0.239 / 0.086 / 0.01; Germany 0.124 / 0.332 / -0.07;
Hong Kong 0.083 / 0.310 / 0.26; Italy -0.226 / -0.084 / -0.30; Japan 0.165 / 0.269 / -0.37; Netherlands 0.168 / 0.444 / 0.31;
Norway 0.001 / 0.224 / -0.08; Singapore 0.024 / 0.438 / 0.38; Spain 0.123 / 0.238 / -0.40; Sweden 0.071 / 0.425 / 0.43;
Switzerland 0.127 / 0.419 / 0.07; UK 0.158 / 0.350 / 0.43; average 0.054 / 0.295 / 0.10 (DIF 0.241).

Table 7 (four states, same countries): DSM / OPT / (wBu, wCo, wBe, wRe) are in `strategies/regime_optimal/replicate_extra.py` (`PAPER_T7`);
average DSM 0.192, OPT 0.319, DIF 0.127, average weights (0.89, 0.69, -0.03, 0.27).

Table 8 (18 datasets, training 1963-07 to 1997-12, evaluation 1998-01 to 2025-12): the 18 rows are in `PAPER_T8`; averages
two-state TSM 0.208, OPT 0.506, DIF 0.299; four-state DSM 0.496, OPT 0.628, DIF 0.132. The strategies are equation 21 and its DSM analogue:
equal-weight average over assets, regimes per asset, no volatility scaling (p. 26).

Figures 1 and 2 (pp. 16, 22): for each start month t from 1969-01 to 2012-12 the Sharpe ratio of OPT and TSM (Figure 1) or DSM (Figure 2)
from t to 2025-12, with the OPT weights fixed on 1926-07 to 1968-12; OPT is above in every month and the gap widens with t.

## What the paper does not report

No transaction costs, no short-borrowing costs, no confidence intervals or tests of the Sharpe differences, no robustness to the
lookback length (12 months throughout) or to the training-window choice beyond the eight windows shown.
