# Claimed results of Gao, Han, Li and Zhou, "Market Intraday Momentum" (June 2017 working paper), as the paper states them

Source: the full text (48 pages), read in this project (pages 1-37 including Tables 1 and 2). Page numbers are the paper's own. Quotations are
exact; numbers are copied from the text and tables. Values from Tables 3-5, 8, 9 and 11-13 were not transcribed (out of scope for this pass).

## Data and definitions

- Sample: "high frequency data of the S&P 500 ETF from 1993-2013" (abstract); SPY from TAQ, "February 1, 1993 through December 31, 2013"; days with fewer than 500 trades are excluded (p. 4-5).
- 13 half-hours from 09:30 to 16:00; `r_j,t = p_j,t / p_(j-1,t) - 1`, with `p_0,t` the previous day's 16:00 price, "so that the first half-hour return captures the impact of information released after the previous day's market close" (p. 5, eq. 1).

## Main claims

- "the first half-hour return on the market since the previous day's market close predicts the last half-hour return" (abstract). The predictability "is stronger on more volatile days, on higher volume days, on recession days, and on major macroeconomic news release days" (abstract).
- "The predictive R2 of the first half-hour return on the last half-hour return is 1.6%"; with the twelfth half-hour 2.6%; out of sample R2_OS 1.4% and 2.0%; when the first half-hour volatility is high R2 is 3.3% for the combined predictors (p. 2).
- "the predictability based on the first half-hour return can generate an extra risk-adjusted return or 'certainty equivalent gains' of 6.02% per annum" for a mean-variance investor with risk aversion 5, 6.18% with the twelfth half-hour added (p. 2-3).
- Market timing with the sign of the first half-hour return: average return 6.67% a year, standard deviation 6.19%, Sharpe ratio 1.08, against 0.29 for daily buy-and-hold (6.04% a year, standard deviation 20.57%) (p. 3, 16).
- "the outperformance remains significant even after accounting for transaction costs" (p. 3); "the intraday momentum profit survives from transaction costs" (p. 23).
- The pattern also holds for ten other ETFs (DIA, QQQ, IWM, EEM, FXI, EFA, VWO, XLF, IYR, TLT): in-sample R2 from 1.16% (DIA) to 8.54% (EEM), out-of-sample R2 from 0.70% (QQQ) to 6.53% (EEM), certainty-equivalent gains up to 17.71% (FXI) (p. 23).

## Table 1 (p. 34): predictive regression of the last half-hour return, in sample 1993-02-01 to 2013-12-31

Slopes scaled by 100, returns annualised and in percent, Newey-West t-statistics in brackets.

| Predictor | r1 | r12 | r1 and r12 |
|---|---|---|---|
| In-sample slope on r1 | 6.94 (4.08) | | 6.81 (4.14) |
| In-sample slope on r12 | | 11.8 (2.62) | 11.4 (2.60) |
| In-sample R2 | 1.6% | 1.1% | 2.6% |
| Out-of-sample R2 (recursive, first estimate from data to 1997-12-31) | 1.4% | 0.9% | 2.0% |

## Table 2 (p. 35): financial crisis (2007-12-03 to 2009-06-30)

| | r1 | r12 | both |
|---|---|---|---|
| Crisis: slope on r1 | 13.6 (2.76) | | 13.2 (2.88) |
| Crisis: R2 | 4.1% | 3.1% | 6.9% |
| Excluding the crisis: R2 | 0.8% | 0.3% | 1.1% |
| Before the crisis: R2 | 0.6% | 0.2% | 0.8% |
| After the crisis: R2 | 1.2% | 1.0% | 2.1% |

## Table 3 (p. 9): volatility terciles, both predictors

R2 0.6% on low first-half-hour-volatility days, 1.0% on medium, 3.3% on high (text, p. 9).

## Table 6 (p. 15-17): timing strategies, annualised by multiplying by 252

| Strategy | Mean | Std dev | Sharpe | Skew | Kurtosis | Success rate |
|---|---|---|---|---|---|---|
| eta(r1) | 6.67% | 6.19% | 1.08 | 0.90 | 15.65 | 54.37% |
| eta(r12) | 1.77% | | 0.29 | 0.38 | 15.73 | 50.93% |
| eta(r1, r12) | 4.39% | | | | | 77.05% |
| Always Long (last half-hour only) | -1.11% | 6.21% | -0.18 | -0.46 | | 50.42% |
| Buy-and-Hold | 6.04% | 20.57% | 0.29 | -0.16 | | |

Excluding the days on which eta(r1, r12) is flat: mean 8.85%, standard deviation 6.36%, Sharpe 1.39, skew 1.19, kurtosis 18.30 (footnote 11).

## Table 7 (p. 18-19): mean-variance investor, risk aversion 5, weight between -0.5 and 1.5, out of sample

| Forecast | Mean | Std dev | Sharpe | CER |
|---|---|---|---|---|
| r1 | 6.51% | 5.62% | 1.16 | 6.02% |
| historical average (benchmark) | 0.46% | 3.06% | 0.15 | |
| r1 and r12 | 6.68% | | 1.07 | 6.18% |

## Table 10 (p. 21-23): transaction costs (bid/ask at 15:30 from TAQ; no spread at the 16:00 close)

- After decimalisation (July 1, 2001): eta(r1) falls to 4.46% a year net, "2.47% lower than the average return before transaction costs" (6.93% gross); Always Long -0.74%; Buy-and-Hold 4.90% (p. 22).
- Both signals: "reduced by only 1.22% to 4.30%" (p. 22), and "4.74% after transaction costs versus 5.50% before" (p. 23). The two statements differ in the paper.
- From January 1, 2005 (proportional spread about 1.2 basis points): eta(r1) 6.52% net against 7.96% gross (p. 22-23).

## What the paper does not give

The estimator of the variance forecast in equation (6) ("estimated from the recursive regressions"), the Newey-West lag, the re-estimation frequency of the recursive regression beyond "progressively add one more month", how the 500-trade day filter is applied to ETF bars, the risk-free rate used in the last half-hour, and any confidence interval for the strategy statistics.
