# Strategy backtester

Describe a strategy (or a research paper) and get code, a backtest, robustness tests and
a plain-language explanation. Python 3.11+, `.venv/bin/python`, command `bt`.

## Layout

- `backtester/data/` cache (Parquet), IBKR / Yahoo / CSV loaders
- `backtester/engine/` native engine behind `Backend`; `RunResult` is the only output format
- `backtester/analysis/` metrics and the validation tests; `findings.py` runs them and raises flags
- `backtester/options/` pricing, volatility surface, chain, calibration, gamma surfaces
- `backtester/portfolio/` weighting methods and Black-Litterman
- `backtester/explain/` explanation text; `backtester/research/` paper library
- `strategies/examples/` worked strategies; `config/` costs and surface parameters
- `docs/research/` method write-ups (formulas, pitfalls, known-answer tests) and the literature sweep
- `.claude/skills/backtest/SKILL.md` the workflow for turning a description or paper into a result

## Conventions

- Tests first; known-answer tests come from the research write-ups. `pytest` must pass before a commit.
- No look-ahead: strategies see data only through `ctx`; `bt check` must pass.
- Every assumption that is not confirmed is written down (config comments, run notes, PR text).
- Option prices are modelled, never quotes; report their sensitivity.
- Costs: IBKR Lite (no commission on US stocks and ETFs, as the account holder stated); options USD 0.65 a contract
  (accepted by the account holder, not read from IBKR); slippage 1 basis point per fill is an assumption.
- Work on a branch per stage, open a draft pull request, report limits as plainly as results.
- The IBKR connector is callable only by Claude, not by Python; data reaches the cache through files.
- Results are research, not investment advice.
