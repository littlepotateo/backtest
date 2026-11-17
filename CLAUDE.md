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
- `backtester/web/` local dashboard (FastAPI, server-rendered pages, Plotly from the installed package, no JS build); `bt serve`; the whole workflow (data, runs, papers) works from the browser; launchers `start.sh`, `Start Backtester.command`, `start.bat`; `bt doctor` diagnoses setup/network; optional OpenAlex key in git-ignored `settings.local.json`; `backtester/claude_code.py` runs the local `claude -p` for dashboard jobs (paper analysis, Consensus search): read-only tools, JSON reply validated and saved by Python (never give it Bash or Write), override the program path with `BACKTEST_CLAUDE`
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
- Dashboard charts: strategy is always series 1 (blue), benchmark or second run series 2 (orange); the palette was validated for
  light and dark; look at every new chart in a browser (Playwright is installed) before calling it done.
- Results are research, not investment advice.
