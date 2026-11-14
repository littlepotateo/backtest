# Method research

Stage 1 of the build: each test method is researched before any test code is written.
The build follows the "Decision" section of each write-up.

| Write-up | Covers |
|---|---|
| [walk-forward.md](walk-forward.md) | In-sample / out-of-sample split, walk-forward optimisation, parameter sensitivity |
| [monte-carlo.md](monte-carlo.md) | Trade reshuffle, bootstrap, block bootstrap, trade skipping, price noise, risk of ruin |
| [kelly.md](kelly.md) | Kelly criterion, fractional Kelly, growth-versus-leverage curve |
| [overfitting-statistics.md](overfitting-statistics.md) | Probabilistic and deflated Sharpe, probability of backtest overfitting, permutation tests, Reality Check / SPA |
| [regimes-costs-lookahead.md](regimes-costs-lookahead.md) | Regime breakdown, cost stress, look-ahead and other bias checks |
| [options-pricing.md](options-pricing.md) | Black-Scholes, volatility surface, synthetic chains, gamma surfaces |
| [portfolio-allocation.md](portfolio-allocation.md) | Black-Litterman and the other weighting methods |
| [lean-integration.md](lean-integration.md) | What a QuantConnect LEAN backend would need |
| [literature-sweep.md](literature-sweep.md) | Consensus literature sweep: findings and what each changes |

## Status and how far to trust these

- **Second pass, 2026-11-14:** primary pages were read for the LEAN data and result
  formats, the `arch` library API, PyPortfolioOpt's Black-Litterman source, freqtrade's
  look-ahead analysis, and Idzorek (2005) in full; Idzorek's worked example was
  reproduced numerically. IBKR's commission pages could not be read (access refused).
- **First pass, 2026-11-13.** Built from web search plus the standard literature. The
  searches mostly returned secondary sources (blogs, library docs, abstracts); the primary
  papers are cited but were **not re-read in full** in this pass.
- Formulas given here are the standard published forms. Each one is pinned down by the
  "Known-answer tests" in its write-up, so a wrong formula fails a test rather than
  silently producing numbers.
- Items marked **[verify]** are recalled, not confirmed this pass, and must be checked
  against the primary source before the code that depends on them is merged.
- **Consensus pass, 2026-11-14:** a first sweep is in `literature-sweep.md` (abstracts
  only). Three topics are not yet searched and one [verify] item is still open; see that file.

Grouping note: the design called for one file per method; related methods are grouped
where they share formulas and pitfalls.
