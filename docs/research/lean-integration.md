# QuantConnect LEAN — what a future `lean` backend needs

LEAN is not part of the first version. This note records what was learned so the door
stays open, and which design seams exist for it.

## What LEAN is and costs

- Open-source event-driven engine (C#, with Python algorithms), run locally through the
  **LEAN CLI** (`pip install lean`).
- **Docker is required** for local backtests: they run in the `quantconnect/lean` image.
- `lean backtest "<project>"` writes results to `<project>/backtests/<timestamp>/`,
  overridable with `--output`; the main results file is `<backtestId>.json`.
- **Data** is the real cost. LEAN reads its own on-disk format from a data folder.
  Free sample data is tiny. Real US equity and, especially, **historical option chain
  data** comes from QuantConnect's dataset marketplace (paid, per-dataset) or from the
  QuantConnect cloud. This is the one thing LEAN offers that our engine cannot: real
  historical option prices.
- Local use of the CLI needs a QuantConnect account; some CLI features require a paid
  tier. **[verify]** current pricing and which commands are gated, at the time of integration.

## Data format (for exporting our cache)  **[verify all of this against the LEAN docs/repo before building]**

Recalled, not confirmed in this pass:
- Equity daily: `data/equity/usa/daily/<ticker>.zip` containing `<ticker>.csv`, rows
  `YYYYMMDD HH:MM,open,high,low,close,volume`, prices stored as integers scaled by 10,000.
- Equity minute: `data/equity/usa/minute/<ticker>/<YYYYMMDD>_trade.zip`, time as
  milliseconds since midnight.
- Corporate actions via `map_files/` and `factor_files/` (LEAN adjusts prices itself
  from raw data).
- Custom data can instead be fed through a `PythonData` class reading local CSV, which
  avoids the native format entirely and is the easier first route.

## Result format  **[verify]**

The result JSON contains charts (including the strategy equity series), orders, closed
trades, and summary statistics. Field names have changed between LEAN versions
(PascalCase → camelCase), so the converter must be written against a real file produced
by the version in use, with a version check.

## Seams already in the design

| Seam | In our code | LEAN side |
|---|---|---|
| Execution backend | `Backend.run(strategy, config) -> RunResult`; `native` backend first | `lean` backend: write project folder, call `lean backtest`, parse output |
| Result format | `RunResult`: equity curve, orders, fills, trades, positions, metadata, `backend` field | Converter from LEAN result JSON |
| Strategy definition | Engine-neutral `spec.md` → generated `strategy.py` | Same spec → generated `main.py` (`QCAlgorithm`) |
| Strategy interface | `init(ctx)`, `on_bar(ctx)`, `ctx.order_target_percent`, option selection by days-to-expiry and strike/delta range | `initialize`, `on_data`, `set_holdings`, `add_option` + `set_filter` |
| Data | Parquet cache keyed by symbol and bar size, UTC + exchange time zone | Exporter to LEAN folder format, or `PythonData` reader |
| Option chain source | `ChainSource` interface: synthetic now | Real chains from QuantConnect data |

Everything downstream of `RunResult` — metrics, walk-forward, Monte Carlo, Kelly,
overfitting statistics, explanations, dashboard — is backend-agnostic. Two caveats:

- Tests that **re-run** the strategy many times (walk-forward, price-noise Monte Carlo,
  Masters permutation, cost stress) would be slow through Docker; LEAN has its own
  optimiser (`lean optimize`) that a `lean` backend could use for walk-forward.
- Tests that re-run on **synthetic price paths** need custom data injection in LEAN.

## Naming conventions adopted now to ease mapping

- Bar sizes named `tick / second / minute / hour / daily` (LEAN's `Resolution` values)
  alongside our minute multiples.
- Symbols stored upper-case with a market field (`usa`) and security type
  (`equity`, `option`, `index`).
- Option contracts identified by (underlying, expiry, strike, right, style).

## When integration would be worth doing

- You decide to pay for real historical option data, or
- you want live/paper trading through the same strategy code, or
- you need asset classes with awkward mechanics (futures rolls, forex, crypto margin).

## Sources

- [LEAN CLI: backtesting](https://www.quantconnect.com/docs/v2/lean-cli/backtesting),
  [deployment](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment),
  [datasets](https://www.quantconnect.com/docs/v2/lean-cli/datasets),
  [projects](https://www.quantconnect.com/docs/v2/lean-cli/projects).
- [lean on PyPI](https://pypi.org/project/lean/).
- Forum: [backtesting with custom and local option chains](https://www.quantconnect.com/forum/discussion/11970/backtesting-with-custom-and-local-optionchains/),
  [local environment with custom data](https://www.quantconnect.com/forum/discussion/6921/running-backtest-in-local-environment-with-custom-data/).
