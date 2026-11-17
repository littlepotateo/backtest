# Narrative: Sharpe-optimal regime allocation (OPT, two regimes, training to 1968-12)

*Written on top of `explanation.md`. Numbers come from `metrics.json`, `validation.json`, the explanation, or are labelled with the script that produced them. Prices are Kenneth French's US market excess return, not a tradable fund; this is research, not investment advice.*

## What this strategy really is

With the weights the paper's method estimates on 1926-07 to 1968-12 (Bull 1.00, Bear 0.05), OPT is a long-only trend filter on the US market: fully invested while the trailing 12-month excess return is positive, almost entirely in cash while it is not. The engine confirms it: it was invested 99.99% of the time at an average beta of 0.61, with 25 closed trades in 57 years (about one switch every two years).

So the headline claim is not "a new signal". It is that the paper's *sizing* rule, near zero in the Bear regime instead of -1, beats the usual long-short TSM rule. That is a claim about one parameter, the Bear weight.

## Did the paper's numbers reproduce?

Yes for the single-asset US results, with one inferred assumption.

- Using the paper's exact method on French's monthly data (`replicate_tables.py`), Table 2 matches to within 0.002 in every training window (OPT 0.558 against 0.559 for the first window; TSM 0.413 against 0.413), and the Bear weights match (0.05, -0.01, 0.00, 0.01, 0.05, 0.04, 0.05; the last window gives 0.01 where the paper has 0.05). Table 5 Sharpe ratios match to about 0.002 and its weights to within 0.03. Large and Small portfolios in Tables 3 and 6 match to about 0.005.
- Running the strategy through this repository's engine (daily bars, orders filled at the next open) and measuring the Sharpe ratio on the equity curve's monthly returns gives 0.559 (OPT) and 0.410 (TSM) for the first window, against the paper's 0.559 and 0.413, and 0.625 and 0.502 (four regimes: OPT, DSM) against 0.625 and 0.504. All eight training windows are in `results.md`; the largest gap between engine and paper is 0.023 (four-regime DSM, last window; the engine's DSM weights come from a different optimiser run than the cross-check script's).
- The assumption: the paper does not say whether the trailing 12-month return is a sum or a compounded return. Compounding does not reproduce its numbers (TSM 0.300 for the first window); the sum does. I inferred "sum" from the paper's own tables.
- The engine's own Sharpe ratio (0.53 for the validated run) is lower than the monthly-return figure (0.559) because the engine annualises daily returns. It is the same equity curve measured two ways, not a different result.

Not reproduced: the international tables (4 and 7), the 18-dataset diversified tables (8) and the two rolling-Sharpe figures. The paper's "Value" and "Growth" rows match our Growth and Value rows, so its labels look swapped (unconfirmed).

## What the result does and does not show

- **Against what?** The paper compares OPT with TSM (+1/-1) and DSM. On the same sample, buy-and-hold of the market's excess return has a Sharpe ratio of 0.442 (monthly, 1969-2025, computed from French's data in this session), so OPT's 0.559 is about 0.12 above doing nothing, and TSM's 0.410 is below it. Most of the paper's measured gain over TSM is that TSM's short positions lose money; any rule that stops shorting would show a similar gain. The paper itself says full short exposure is "neither necessary nor optimal" (p. 14).
- **Max drawdown.** The strategy's worst fall was -34.0% against -59.2% for the benchmark (`metrics.json`), but the Monte Carlo (2,000 block-resampled histories) puts the 1-in-20 case at -58% and finds 17% of histories fall 50% from a peak. A 0.61 beta to equities is still a large equity risk. Size for the -58%, not the -34%.
- **Statistical evidence.** "Probability true Sharpe > 0" is 100%: true of almost any strategy long US equities for 57 years, so it says little. The timing test, which shuffles returns while keeping the exposures, gives p = 0.07: suggestive, not significant at 5%.
- **Selection.** The weights are estimated out of sample (training ends 1968), which is the honest part. The design itself (12-month sign signal, US market, Sharpe as the objective, the eight window ends) was chosen with knowledge of the whole sample. Only 2 configurations were counted in the trial ledger, but the real number of researcher choices is larger.
- **Flags that are artefacts of this design.** "The chosen value of `states` jumps around between windows" and the split test (Sharpe 0.52 to 0.70 with four regimes) come from a parameter grid of {2 regimes, 4 regimes}: two different strategy designs, not a tuned knob, so they are not evidence of overfitting. The four-regime version scored higher (0.58 in the sensitivity test; the paper reports 0.625 against 0.559 on the monthly measure).
- **Costs.** One basis point of slippage per fill (an assumption) cost 2.2 percentage points of 2,909% total return, and the break-even is far above any plausible cost. The paper models no costs either. Short borrow fees are not modelled; OPT does not short (Bear weight 0.05) but TSM does.
- **Data.** The data check flagged 5 bars that moved more than 10 standard deviations; a simple rule of my own finds nine such days, on well-known dates (28-30 October 1929, the March 1933 reopening after the bank holiday, 19 October 1987, 13 October 2008, 16 March 2020), so they look like real moves, not errors. The longest gap, 12 days, is the March 1933 bank holiday.

## What to try next

1. Replicate Tables 4, 7 and 8 (international and 18 portfolio datasets) with the same code; they carry the paper's claim of uniform dominance.
2. Test lookback sensitivity (6, 9, 12, 15 months) and a rule fixed at Bear weight 0 (a plain trend filter), which would show how much of OPT is just "stop shorting".
3. Use tradable instruments (SPY and a Treasury bill ETF from 1993, or French's total return with an actual T-bill series) to test the same rule with real costs and cash interest.
4. Ask whether the "Value/Growth label swap" is a mistake in the paper; it changes the reading of Table 3.
