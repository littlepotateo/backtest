# A Quantitative Approach to Tactical Asset Allocation

Meb Faber (2007). The Journal of Wealth Management

https://consensus.app/papers/details/w:a04e459f-3043-492a-9ff4-3151aef09092/

## Key finding

A moving-average timing model, tested in-sample on US equities and out-of-sample on more than twenty other markets, then in an allocation across five asset classes since 1972, gives equity-like returns with bond-like volatility and drawdown.

## Rules (as stated)

Only the abstract was available (via Consensus). It says: a moving-average timing model, tested in-sample on US
equities and out-of-sample on more than twenty other markets, then in an allocation across the S&P 500, MSCI EAFE,
GSCI, NAREIT and US 10-year Treasury bonds since 1972. **It does not state the rule's details.**

## Assumptions I had to make

- **The rule itself is from my recollection, not from the paper's text:** hold an asset if its latest month-end price is
  above the average of its last 10 month-end prices, else hold cash; equal weights across five assets; monthly. Verify
  against the full text before treating this as the paper's strategy.
- Instruments are ETFs standing in for the paper's indices: SPY, EFA, IEF, DBC, VNQ (Yahoo data, dividend-adjusted).
- Signal at the last close of the month; the order fills at the next bar's open; 1 basis point slippage per fill;
  idle cash earns the Treasury bill rate minus 1% (IBKR Lite).
- Period 2007-06-01 to 2026-11-16, set by DBC's history. The paper's sample starts in 1972.

## Replication notes (2026-11-16)

Strategy `strategies/examples/faber_timing.py`; full validation output in `faber-run-explanation.md`.
Comparison against always holding the same five ETFs in equal weight (monthly rebalanced), same period and costs:

| | Timing | Always invested | SPY | IEF (10-year Treasury ETF) |
|---|---|---|---|---|
| Annual return | 4.53% | 5.91% | 10.53% | 3.13% |
| Volatility | 7.98% | 14.37% | 19.68% | 6.97% |
| Max drawdown | -14.92% | -46.48% | -55.2% | -23.9% |
| Sharpe (2% risk-free) | 0.34 | 0.33 | n/a | n/a |

Against the three claims in the abstract:

1. **"Improves risk-adjusted returns."** Not clearly. Volatility and the worst fall were cut sharply, but return fell
   with them: the Sharpe ratio is 0.34 against 0.33, essentially unchanged. The validation tests also could not separate the
   timing from chance (permutation p = 0.66) and put the probability that the true Sharpe is above zero at 93%.
2. **"Equity-like returns with bond-like volatility and drawdown."** Partly. Volatility (8.0%) and the worst fall (-14.9%)
   are in the range of a Treasury ETF's (7.0%, -23.9%), but the return (4.5% a year) is nearer the Treasury ETF's than
   SPY's 10.5%. Equity-like returns did not appear in this sample.
3. **"Over thirty consecutive years of positive performance."** Cannot be tested: the sample is 19 years. For what it is
   worth, 5 of the 20 full or part calendar years were negative (2008, 2011, 2015, 2018, 2022), all small (worst -4.9%).

**Verdict: partly replicated.** Lower volatility and drawdown reproduced; higher risk-adjusted return and equity-like
returns did not. The comparison is not like for like (period, instruments, and a rule I could not check against the full
text), so this is weak evidence about the paper, not a refutation. Next: read the full text, then re-run with the
paper's exact rule and, if possible, longer index histories.
