# Replication results: intraday momentum

Produced by `strategies/intraday_momentum/replicate_tables.py`, `synthetic_demo.py` and the engine strategy. Paper values: `claims.md`. See `strategies/intraday_momentum/spec.md` for assumptions and the data limit.

## A. The paper's method on the real data available (SPY, 30-minute bars from IBKR, 2026-07-31 to 2026-11-17)

**Not comparable with the paper**: 75 days against about 5,200, and a different period. The recursive out-of-sample tables cannot start (they need 60 days of history before the first forecast and the paper starts in 1998).

```
Sample: 2026-08-03 to 2026-11-17, 76 complete trading days (76 with r13; 1 days dropped).
The paper's sample is SPY ticks from TAQ, 1993-02-01 to 2013-12-31 (about 5,200 days). Numbers below are comparable with the paper only on that sample.

TABLE 1 predictive regression of r13 (slopes x100, intercept x252x100, Newey-West t in brackets)   [paper: r1 6.94 (4.08) R2 1.6; r12 11.8 (2.62) 1.1; both 2.6; OOS R2 1.4 / 0.9 / 2.0]
     r1: n=75  const=-4.37 (-0.97)  r1=-8.80 (-2.76)  R2=12.30%  OOS R2=n/a%  [only 0 observations before 2026-08-04; at least 60 are needed to start the recursion]
    r12: n=76  const=-5.95 (-1.18)  r12=5.27 (0.25)  R2=0.18%  OOS R2=n/a%  [only 0 observations before 2026-08-03; at least 60 are needed to start the recursion]
   both: n=75  const=-4.51 (-1.00)  r1=-9.54 (-2.77)  r12=16.16 (0.56)  R2=13.91%  OOS R2=n/a%  [only 0 observations before 2026-08-04; at least 60 are needed to start the recursion]

TABLE 2 R2 % by period   [paper: crisis 4.1 / 3.1 / 6.9 (r1, r12, both); excluding crisis 0.8 / 0.3 / 1.1]
             crisis: n=0  r1=n/a  r12=n/a  both=n/a
   excluding crisis: n=75  r1=12.30  r12=0.18  both=13.91
      before crisis: n=0  r1=n/a  r12=n/a  both=n/a
       after crisis: n=75  r1=12.30  r12=0.18  both=13.91

TABLE 6 strategies (annualised, percent)   [paper eta(r1): mean 6.67 sd 6.19 Sharpe 1.08 skew 0.90 kurt 15.65 success 54.37; both signals mean 4.39 success 77.05; Always Long -1.11; Buy-and-Hold 6.04 / 20.57 / 0.29]
       eta_r1: mean=-9.76  sd=2.26  Sharpe=-4.32  skew=-0.50  kurt=4.97  success=34.67%  (n=75)
      eta_r12: mean=1.05  sd=2.34  Sharpe=0.45  skew=0.62  kurt=5.13  success=49.33%  (n=75)
   eta_r1_r12: mean=-4.36  sd=1.33  Sharpe=-3.29  skew=-0.77  kurt=7.97  success=65.33%  (n=75)
  always_long: mean=-5.64  sd=2.32  Sharpe=-2.44  skew=-0.15  kurt=5.21  success=40.00%  (n=75)
     buy_hold: mean=-10.36  sd=14.45  Sharpe=-0.72  skew=-1.15  kurt=9.48  success=42.67%  (n=75)

TABLE 7 mean-variance investor, gamma 5, weight in [-0.5, 1.5]   [paper r1: mean 6.51 sd 5.62 Sharpe 1.16 CER 6.02; both: mean 6.68 Sharpe 1.07 CER 6.18]
     r1: only 0 observations before 2026-08-04; at least 60 are needed to start the recursion
   both: only 0 observations before 2026-08-04; at least 60 are needed to start the recursion

TABLE 10 net of IBKR costs (half-spread 1 bp at entry, no spread at the close auction; SEC/FINRA/clearing fees from config/costs.toml)   [paper, after 2005: eta(r1) 7.96 gross, 6.52 net]
  half-spread 0.6 bp: eta_r1: gross -9.76 -> net -11.81 (cost 2.05/yr)   eta_r1_r12: gross -4.36 -> net -5.45 (cost 1.09/yr)
  half-spread 1 bp: eta_r1: gross -9.76 -> net -12.82 (cost 3.06/yr)   eta_r1_r12: gross -4.36 -> net -5.99 (cost 1.63/yr)
  half-spread 1.2 bp: eta_r1: gross -9.76 -> net -13.33 (cost 3.56/yr)   eta_r1_r12: gross -4.36 -> net -6.25 (cost 1.90/yr)
  half-spread 2.4 bp: eta_r1: gross -9.76 -> net -16.35 (cost 6.59/yr)   eta_r1_r12: gross -4.36 -> net -7.87 (cost 3.51/yr)
```

## B. The machinery on simulated data with the paper's headline parameters planted

5,200 simulated days with `r13 = 0.0694 r1 + noise` (the paper's scaled slope 6.94). This tests the code, not the paper. The table code recovers the planted slope (7.10 against 6.94 planted), R2 (1.63% against about 1.6%) and out-of-sample R2 (1.58%); Newey-West t-statistics are larger than the paper's 4.08 because the simulated noise has no volatility clustering.

```
Simulated SPY-like data with the paper's headline parameters planted (5,200 days):

Sample: 1993-02-01 to 2013-01-04, 5200 complete trading days (5200 with r13; 0 days dropped).
The paper's sample is SPY ticks from TAQ, 1993-02-01 to 2013-12-31 (about 5,200 days). Numbers below are comparable with the paper only on that sample.

TABLE 1 predictive regression of r13 (slopes x100, intercept x252x100, Newey-West t in brackets)   [paper: r1 6.94 (4.08) R2 1.6; r12 11.8 (2.62) 1.1; both 2.6; OOS R2 1.4 / 0.9 / 2.0]
     r1: n=5200  const=0.66 (0.60)  r1=7.10 (9.59)  R2=1.63%  OOS R2=1.58%
    r12: n=5200  const=0.70 (0.63)  r12=5.13 (2.05)  R2=0.08%  OOS R2=0.05%
   both: n=5200  const=0.63 (0.57)  r1=7.06 (9.54)  r12=4.52 (1.82)  R2=1.69%  OOS R2=1.62%

TABLE 2 R2 % by period   [paper: crisis 4.1 / 3.1 / 6.9 (r1, r12, both); excluding crisis 0.8 / 0.3 / 1.1]
             crisis: n=412  r1=4.74  r12=0.70  both=5.54
   excluding crisis: n=4788  r1=1.45  r12=0.06  both=1.49
      before crisis: n=3870  r1=1.73  r12=0.02  both=1.74
       after crisis: n=918  r1=0.52  r12=0.40  both=0.89

TABLE 6 strategies (annualised, percent)   [paper eta(r1): mean 6.67 sd 6.19 Sharpe 1.08 skew 0.90 kurt 15.65 success 54.37; both signals mean 4.39 success 77.05; Always Long -1.11; Buy-and-Hold 6.04 / 20.57 / 0.29]
       eta_r1: mean=8.66  sd=5.09  Sharpe=1.70  skew=0.01  kurt=2.89  success=54.48%  (n=5200)
      eta_r12: mean=2.59  sd=5.12  Sharpe=0.51  skew=-0.06  kurt=2.91  success=52.21%  (n=5200)
   eta_r1_r12: mean=5.62  sd=3.64  Sharpe=1.54  skew=0.21  kurt=5.73  success=77.94%  (n=5200)
  always_long: mean=0.74  sd=5.12  Sharpe=0.14  skew=-0.02  kurt=2.90  success=51.25%  (n=5200)
     buy_hold: mean=2.46  sd=14.62  Sharpe=0.17  skew=0.09  kurt=3.04  success=50.09%  (n=5199)

TABLE 7 mean-variance investor, gamma 5, weight in [-0.5, 1.5]   [paper r1: mean 6.51 sd 5.62 Sharpe 1.16 CER 6.02; both: mean 6.68 Sharpe 1.07 CER 6.18]
     r1: mean=9.17  sd=5.64  Sharpe=1.63  historical-mean forecast: mean=-0.51 Sharpe=-0.12  CER=9.34  (days=3917)
   both: mean=9.16  sd=5.61  Sharpe=1.63  historical-mean forecast: mean=-0.51 Sharpe=-0.12  CER=9.34  (days=3917)

TABLE 10 net of IBKR costs (half-spread 0.6 bp at entry, no spread at the close auction; SEC/FINRA/clearing fees from config/costs.toml)   [paper, after 2005: eta(r1) 7.96 gross, 6.52 net]
  half-spread 0.6 bp: eta_r1: gross 8.66 -> net 7.14 (cost 1.51/yr)   eta_r1_r12: gross 5.62 -> net 4.86 (cost 0.77/yr)
  half-spread 1.2 bp: eta_r1: gross 8.66 -> net 5.63 (cost 3.02/yr)   eta_r1_r12: gross 5.62 -> net 4.09 (cost 1.54/yr)
  half-spread 2.4 bp: eta_r1: gross 8.66 -> net 2.61 (cost 6.05/yr)   eta_r1_r12: gross 5.62 -> net 2.55 (cost 3.07/yr)
```

## C. The engine run (`bt validate`, `--fill close --no-cash-interest`)

Total return -4.56% over 77 days, 76 trades, costs $158.95 commission and $1,489.62 slippage; the exact-method eta(r1) mean is -9.76% a year gross. See `run/narrative.md` and `run/explanation.md`. The engine daily returns equal the exact-method returns to 1e-9 on simulated data (`tests/test_intraday_strategy.py`).

## D. Costs

- Commission 0.00 (IBKR Lite; confirmed on IBKR's commission page 2026-11-18). SEC fee 0.0000206 per dollar sold; FINRA activity fee shown as 0.00 by IBKR (fee holiday to 2026-12-31), usual 0.000166 per share used (unconfirmed); audit trail 0.000003 and clearing 0.00020 per share.
- Spread: IBKR regular-hours quotes for SPY on 2026-11-18, about 15:36 New York, REALTIME: 730.37 / 730.40 (half-spread 0.21 bp) and 12 seconds later 730.46 / 730.48 (0.14 bp), so about 0.2 bp against the paper's 1.2 bp. The earlier 02:06 ET quote (734.14 / 734.23, 1.2 bp wide) was overnight and is not a regular-hours spread. Two quotes on one day are not a history; `slippage_bps` in `config/costs.toml` stays at the 1 bp assumption (the measured half-spread is about 0.2 bp of it, the rest is an unmeasured slippage allowance), and the paper's 1.2 bp, 2x and 3x rows remain the sensitivity check.
