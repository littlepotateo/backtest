# Strategy Backtester

Describe a trading or investment strategy in plain English (or supply a research paper) and get strategy code, a backtest, robustness tests and a plain-language explanation.

Design: `docs/superpowers/specs/2026-11-13-strategy-backtester-design.md`
Method research: `docs/research/`

## Status

Built: data cache, stock/ETF engine (daily and intraday), metrics, and the validation tests (walk-forward, Monte Carlo, Kelly, overfitting statistics, regimes, cost stress, look-ahead check).
Not built yet: portfolio allocation (Black-Litterman), options, written explanations and the Claude Code skill, the dashboard.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

## Use

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

Other commands: `bt data`, `bt check`, `bt optimize`, `bt ingest-ibkr`, `bt compare-ibkr`, `bt import-csv`. Run `bt <command> --help` for options.

Each run is saved under `runs/` with its equity curve, fills, trades, `metrics.json` and, for `validate`, `validation.json`.

## Assumptions to know about

- Costs follow IBKR Lite as stated by the account holder: no commission on US stocks and ETFs. Slippage of 1 basis point per fill is an assumption (`config/costs.toml`).
- Idle cash earns the 13-week Treasury bill yield minus 1%; borrowed cash pays it plus 2.5%.
- Orders fill at the next bar's open.
- Short borrow fees are not modelled.

Results are not investment advice.
