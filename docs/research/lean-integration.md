# QuantConnect LEAN — what a future `lean` backend needs

LEAN is not part of the first version. This note records what was learned so the door
stays open, and which design seams exist for it.

## What LEAN is and costs (confirmed from QuantConnect's docs, 2026-11-14)

- Open-source event-driven engine (C#, with Python algorithms), run locally through the
  **LEAN CLI** (`pip install lean`).
- **Docker is required**: commands that run the engine locally need Docker installed
  and running; local backtests run in the `quantconnect/lean` image.
- **A paid QuantConnect tier is required**: the docs state "To use the CLI, you must be
  a member in an organization on a paid tier." Whether a local backtest also needs
  `lean login` is not clearly stated.
- `lean backtest "<project>"` writes to `<project>/backtests/<timestamp>/`
  (overridable with `--output`); results are JSON, main file `<backtestId>.json`.
- **Data** is the real cost. The docs' table lists the US Equity Security Master at
  $1,200/year (needed for equity backtests), with US Equity and US Equity Options data
  priced per download on top. Real **historical option chains** are the one thing LEAN
  offers that our engine cannot.

## Data format (from the LEAN repository's data readmes)

US equities, New York time zone, prices as integers in "deci-cents" (divide by 10,000):

| Resolution | Path | CSV inside the zip | Time column |
|---|---|---|---|
| daily, hour | `equity/usa/{daily,hour}/<ticker>.zip` | `<ticker>.csv`: `DateTime,Open,High,Low,Close,Volume` | string `YYYYMMDD HH:MM` |
| minute (second inferred) | `equity/usa/minute/<ticker>/<YYYYMMDD>_{trade,quote}.zip` | e.g. `20140605_aapl_minute_trade.csv`: `Time,Open,High,Low,Close,Volume` | milliseconds since midnight |
| tick | `equity/usa/tick/<ticker>/<YYYYMMDD>_{trade,quote}.zip` | trade: `Time,TradeSale,Volume,Exchange,Condition,Suspicious` | milliseconds since midnight (fractional) |

US equity options (minute only documented): `option/usa/minute/<symbol>/<YYYYMMDD>_<tickType>_<optionType>.zip`,
with `tickType` one of `trade`, `quote`, `openinterest`; one CSV per contract named
`<YYYYMMDD>_<symbol>_<resolution>_<tickType>_<optionType>_<optionStyle>_<decicentStrike>_<expiryYYYYMMDD>.csv`.
Trade and quote columns as for equities; open interest is `Time,Open Interest`.

Not confirmed: map/factor file formats for corporate actions; time zone of option data.

**Easier first route — custom data.** A `PythonData` subclass with
`get_source(self, config, date, is_live)` returning a `SubscriptionDataSource` using
`SubscriptionTransportMedium.LOCAL_FILE`, and `reader(self, config, line, date, is_live)`
returning a data point with `symbol`, `time`, `end_time` and `value` set. This lets a
`lean` backend read our cache exported as plain CSV without the native format.

## Result format (from `Common/Result.cs` and `BacktestResultPacket.cs`)

Properties on the result object: `Charts`, `Orders`, `OrderEvents`, `ProfitLoss`,
`Statistics`, `RuntimeStatistics`, `TotalPerformance`, `State`, `AlgorithmConfiguration`,
plus `RollingWindow` for backtests. The C# names are PascalCase with no renaming
attribute, but the casing actually written to `<backtestId>.json` was **not confirmed**
(it has differed between LEAN versions), and where closed trades sit inside
`TotalPerformance` was not confirmed. The converter must therefore be written against
a real output file, accept either casing, and check the LEAN version.

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

- LEAN repository: [equity data readme](https://raw.githubusercontent.com/QuantConnect/Lean/master/Data/equity/readme.md),
  [option data readme](https://raw.githubusercontent.com/QuantConnect/Lean/master/Data/option/readme.md),
  [Result.cs](https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Result.cs).
- [LEAN CLI getting started](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started),
  [custom data key concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/importing-data/streaming-data/key-concepts).
- [LEAN CLI: backtesting](https://www.quantconnect.com/docs/v2/lean-cli/backtesting),
  [deployment](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment),
  [datasets](https://www.quantconnect.com/docs/v2/lean-cli/datasets),
  [projects](https://www.quantconnect.com/docs/v2/lean-cli/projects).
- [lean on PyPI](https://pypi.org/project/lean/).
- Forum: [backtesting with custom and local option chains](https://www.quantconnect.com/forum/discussion/11970/backtesting-with-custom-and-local-optionchains/),
  [local environment with custom data](https://www.quantconnect.com/forum/discussion/6921/running-backtest-in-local-environment-with-custom-data/).
