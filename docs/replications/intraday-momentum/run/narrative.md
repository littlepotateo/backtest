# Narrative: intraday momentum timing on the first half-hour return, SPY, 2026-07-31 to 2026-11-17

*Written on top of `explanation.md`. Numbers come from `metrics.json`, `validation.json`, the explanation, or the exact-method script
(`replicate_tables.py`, same data). This is research, not investment advice.*

## What was run, and why it is not a replication

The strategy is the paper's eq. (4): at 15:30 go long if the first half-hour return (previous close to 10:00) is positive and short otherwise, close at the 16:00
close. It was run through the engine on the only 30-minute SPY history the IBKR connector can supply: 1,000 bars, 77 trading days (76 complete). The paper's
sample is 1993-2013, about 5,200 days. With 75 daily observations the statistical power for a predictive R2 of about 1.6% is close to nil, so **this run checks
that the code works on real data; it says nothing for or against the paper's finding.**

## What the run shows

- Total return -4.56% in 77 days (annual return -14.17%), worst fall -4.56%, 76 trades, Sharpe -6.85 (a 77-day window annualised: treat as noise), costs $158.95
  commission (regulatory fees) and $1,489.62 slippage on $100,000. The benchmark (buy-and-hold SPY) returned -1.93%.
- The exact-method script on the same bars (no costs) gives a regression slope of -8.80 (Newey-West t -2.76) and R2 12.3% for r13 on r1 (n = 75), i.e. a
  *negative* relation in this window, and an eta(r1) mean of -9.76% a year against -5.64% for Always Long. The sign is the opposite of the paper's (+6.94, t 4.08).
  With 75 days and a window that ends in a falling market, a reversal this size is within what noise can produce; it should not be read as a refutation.
- Validation flags that matter: the strategy lost money; 100% of resampled histories lose money (a statement about this window only); fills at the close are optimistic by
  construction (see below); the timing permutation test p = 0.95; the sample has no bear market.

## Things to know about the engine run

- `--fill close` is required: the entry order fills at the 15:30 price and the exit at the 16:00 close, as in the paper. The engine flags this as optimistic.
- The engine charges the 1 bp slippage assumption on both fills; the paper's costs (and the exact-method Table 10) charge a spread only at the 15:30 entry because
  the closing auction pays none. Engine costs are therefore higher than the paper's convention.
- "Fills delayed one bar" is reported as +4.17% in the cost stress: it is not a robustness result, it reflects that the signal reversed in this window.

## What would make this a real test

1. SPY 1-minute or 30-minute bars for 1993-2013 (TAQ through a university, or a vendor file); `replicate_tables.py --file <file>` prints every table beside the paper's values.
2. Any longer recent history (several years of 30-minute bars from a vendor): the same script and the engine strategy run unchanged.
3. The regular-hours spread from IBKR (a snapshot taken during the 15:30 half-hour), to replace the 1 bp assumption.
