# Strategy Backtester

Describe a trading or investment strategy in plain English (or supply a research paper) and get strategy code, a backtest, robustness tests and a plain-language explanation.

Design: `docs/superpowers/specs/2026-11-13-strategy-backtester-design.md`
Method research: `docs/research/`

## Status

Built: data cache, stock/ETF engine (daily and intraday), metrics, the validation tests (walk-forward, Monte Carlo, Kelly, overfitting statistics, regimes, cost stress, look-ahead check), and portfolio allocation (equal weight, inverse volatility, risk parity, minimum variance, mean-variance, Black-Litterman).
Options (stage 5): Black-Scholes pricing on a calibrated volatility surface, a synthetic chain, defined-risk option positions in the engine, and 3D gamma surfaces. Option prices are modelled, not quotes; read the pricing-sensitivity line in `bt validate` output.
Explanations and papers (stage 6): `bt validate` writes `explanation.md`; `bt explain` regenerates it; `bt paper` keeps a library of research papers with their claims and linked runs; `.claude/skills/backtest/SKILL.md` is the workflow for turning a description or paper into a result.
Dashboard (stage 7): `bt serve` opens a local web app with the run list, run pages (charts, monthly returns, validation, explanation, 3D option surfaces), comparison of two runs, the research library, and re-runs with changed settings.
All seven stages of the original plan are built.

## First run

Run this once from the repository root. A fresh clone does not include `.venv`;
this creates it and installs the `bt` command and its dependencies.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

## Download data and run a backtest

Run these from the repository root, after setup. The first command creates
`data/cache/`; the validation command creates a results folder under `runs/`.
Those generated folders are ignored by Git, so they start empty in a fresh clone.

```bash
.venv/bin/bt fetch-yahoo SPY --start 2005-01-01
```

```bash
.venv/bin/bt fetch-rates
```

```bash
.venv/bin/bt run strategies/examples/sma_cross.py --start 2006-01-01
```

```bash
.venv/bin/bt validate strategies/examples/sma_cross.py --start 2006-01-01
```

```bash
.venv/bin/bt calibrate-options data/calibration/SPY-2026-11-13.json
```

```bash
.venv/bin/bt serve
```

**Browser only (no terminal commands):** double-click `Start Backtester.command` (Mac), `start.bat` (Windows) or run `./start.sh` (Linux). The first start creates `.venv`, installs everything and opens the dashboard. From then on, the Data page downloads prices and interest rates, the New backtest page runs strategies, and the Research page takes dropped PDFs and searches published papers. Paper search offers two sources: OpenAlex (instant, in the page) and Consensus (the page saves a request and gives one line to paste into Claude Code, which searches Consensus and saves the papers to the library). The Refresh button reloads from disk and clears the page state. `bt doctor` checks the setup and network if a download fails.

Then open http://127.0.0.1:8000 (use `--port` to change it). The server listens on this computer only and refuses form posts from other websites.

Other commands: `bt data`, `bt check`, `bt optimize`, `bt ingest-ibkr`, `bt compare-ibkr`, `bt import-csv`. Run `bt <command> --help` for options.

Each run is saved under `runs/` with its equity curve, fills, trades, `metrics.json` and, for `validate`, `validation.json`.

## Assumptions to know about

- Costs follow IBKR Lite as stated by the account holder: no commission on US stocks and ETFs. Slippage of 1 basis point per fill is an assumption (`config/costs.toml`).
- Idle cash earns the 13-week Treasury bill yield minus 1%; borrowed cash pays it plus 2.5%.
- Orders fill at the next bar's open.
- Short borrow fees are not modelled.
- For rebalanced portfolios, "trades" counts every partial sale at a rebalance, so win rate and profit factor say little; read the return and drawdown figures instead.
- The example ETF strategy's Black-Litterman reference portfolio is a rough assumption, not measured market weights.

Results are not investment advice.
