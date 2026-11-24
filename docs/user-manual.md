# Strategy Backtester: user manual

This manual covers installing the backtester, getting data, running and testing a strategy, using the
dashboard, reading the results and fixing common errors. For the design see `docs/superpowers/specs/`;
for the research methods see `docs/research/`.

> Results are research, not investment advice. Option prices are modelled, not quotes. Costs follow the
> assumptions in `config/costs.toml`.

Commands below use `.venv/bin/` (macOS and Linux). On Windows, use `.venv\Scripts\` instead.

---

## 1. What the program does

You describe a strategy (in plain language, or from a research paper). The program:

1. loads price data (Yahoo Finance, Interactive Brokers exports, or your own CSV) into a local cache;
2. runs your strategy file bar by bar in a simulator that charges costs and cannot see the future;
3. saves the run (equity curve, fills, trades, metrics) under `runs/`;
4. optionally runs robustness tests (`bt validate`) and writes a plain-language `explanation.md`;
5. shows everything in a local dashboard (`bt serve`).

---

## 2. Installing

### Option A: browser only (recommended for most people)

- **Mac:** double-click `Start Backtester.command`.
- **Windows:** double-click `start.bat`.
- **Linux:** run `./start.sh`.

The first start creates `.venv`, installs the packages and opens the dashboard at
<http://127.0.0.1:8000>. Each start first updates the program from GitHub (`scripts/update.sh` or
`scripts/update.bat`). If an update is not possible, it says why and starts the code you already have.
To turn updates off, set `BACKTEST_NO_UPDATE=1`.

### Option B: terminal

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Requires Python 3.11 or newer. The `bt` command is then available as `.venv/bin/bt`.

### Checking the installation

```bash
.venv/bin/bt doctor
```

`doctor` checks the Python version, folders, packages, cached data and the connection to Yahoo Finance and
OpenAlex. Run it first whenever a download fails.

---

## 3. Getting data

| Command | What it does |
|---|---|
| `bt fetch-yahoo SPY --start 2005-01-01` | Downloads daily bars for a symbol into the cache. `--interval` and `--end` are also available. |
| `bt fetch-rates` | Downloads the 13-week Treasury bill yield used for idle-cash and margin interest. |
| `bt import-csv SYMBOL INTERVAL FILE` | Loads bars from your own CSV. Use `--source` and `--adjusted` to describe the file. |
| `bt ingest-ibkr SYMBOL FILE...` | Loads Interactive Brokers price-history JSON files for a symbol. `--adjusted` sets the adjustment flag. |
| `bt compare-ibkr` | Compares an IBKR sample with the cached bars. |
| `bt data` | Lists the cached data sets. |
| `bt calibrate-options FILE` | Fits the volatility surface to a snapshot of option quotes, for option strategies. |

The cache is `data/cache/` (Parquet files). Downloads are kept there, so you only need to fetch once.

The Data page of the dashboard does the same downloads with buttons.

---

## 4. Writing a strategy

A strategy is a Python file. The `sma_cross.py` example in `strategies/examples/` is the smallest complete one:

```python
from backtester import Strategy

class SmaCross(Strategy):
    universe = ["SPY"]              # symbols the strategy trades
    interval = "1d"                 # bar size
    params = {"fast": 50, "slow": 200}
    param_grid = {"fast": [20, 50, 100], "slow": [100, 150, 200, 250]}

    @classmethod
    def valid_params(cls, params):
        return params["fast"] < params["slow"]

    def on_bar(self, ctx):
        symbol = self.universe[0]
        closes = ctx.closes(symbol, self.params["slow"])
        if len(closes) < self.params["slow"]:
            return
        ...
```

Key points:

- **`on_bar(ctx)`** runs once per bar. It may only use data through `ctx`; looking at anything later is a
  look-ahead, which `bt check` catches.
- **Reading data:** `ctx.closes(symbol, n)`, `ctx.history(symbol, n)`, `ctx.returns(symbols, n)`,
  `ctx.price(symbol)`, `ctx.now()`.
- **Trading:** `ctx.order(symbol, qty)`, `ctx.order_target(symbol, qty)`,
  `ctx.order_target_percent(symbol, pct)`, `ctx.rebalance({symbol: weight, ...})`.
- **Account:** `ctx.position(symbol)`, `ctx.cash()`, `ctx.equity()`.
- **Intraday:** `ctx.bars_into_session(symbol)`, `ctx.bars_left_in_session(symbol)`, `ctx.session_date(symbol)`.
- **Options:** the `OptionsApi` on the context (`select`, `price`, `greeks`, `order`, `close`, `close_all`).
- **Logging a series:** `ctx.record(name, value)`.
- **Parameters:** `self.params` holds the current values; `param_grid` is what `bt optimize` searches.

Working examples: `strategies/examples/` (SMA cross, ETF allocation, Faber timing, opening-range breakout,
covered call, cash-secured put, iron condor). Two paper replications are in `strategies/intraday_momentum/`
and `strategies/regime_optimal/`; each has a `spec.md` that lists its assumptions.

---

### Strategies page

The **Strategies** page (top menu) lists every strategy you can backtest.

- **Add a strategy:** choose a Python (`.py`) file that defines one class inheriting from `Strategy`, with `universe` and `interval` set. Tick the trust box: the file runs on this computer with your permissions. The file is checked for structure and run once on its own data before it is added (no data is downloaded for you; if the data is missing, the file is still added and the page says it was checked for structure only). Your strategies go into `strategies/user/`.
- **Drafts:** on the Research page, an analysed paper has a **Draft a strategy for review** button. Claude writes a strategy from the paper's rules into the drafts queue, with the choices the paper does not settle listed. Drafts also appear under "Drafts waiting for your review" here. The draft is only checked for structure when it is created; **Approve** runs it once on its data and moves it into your strategies, and a draft that fails stays in the queue with the reason. **Reject** deletes the draft after you confirm.
- **Descriptions:** **Describe with Claude** on any strategy writes a short description, the edge it aims at, and its risks, marked as AI-written with the date. Claude reads the strategy's code (and, from the Research page, the paper it is tested against) and cannot change any file; the text is saved in `data/strategy_descriptions.json`. A description you typed for an uploaded strategy is kept and shown above the AI one.
- **Remove:** moves a strategy you added into `strategies/removed/`. Move the files back by hand to restore it. Shipped examples cannot be removed from the page.

---

## 5. Running a backtest

```bash
.venv/bin/bt run strategies/examples/sma_cross.py --start 2006-01-01
```

Common options (all commands that run a strategy accept them):

| Option | Meaning |
|---|---|
| `--start`, `--end` | Date range. |
| `--cash` | Starting cash. |
| `--param NAME=VALUE` | Override a strategy parameter (repeatable). |
| `--costs FILE` | Use a different cost file (default `config/costs.toml`). |
| `--cost-multiplier X` | Scale all costs by X, for a quick stress. |
| `--fill next_open` or `--fill close` | When an order fills. `next_open` (default) is the realistic choice. `close` fills at the same bar's close and is flagged. |
| `--max-leverage X` | Cap on gross exposure (default 1.0). |
| `--no-short` | Forbid short positions. |
| `--no-cash-interest` | Do not credit or charge interest on cash. |
| `--raw-prices` | Ignore dividend adjustment. |
| `--benchmark SYMBOL` | Compare against this symbol. |
| `--risk-free RATE` | Risk-free rate for the Sharpe ratio. |
| `--out DIR` | Where to save the run. |

Other commands:

- `bt check strategy.py` runs the look-ahead and data checks. Run it before trusting any result.
- `bt optimize strategy.py` tries every combination in `param_grid` and reports them.
- `bt validate strategy.py` runs the backtest plus the robustness tests and writes `validation.json` and
  `explanation.md`. Useful options: `--tests`, `--paths N` (Monte Carlo paths), `--synthetic N`,
  `--walk-forward rolling|anchored`, `--seed`.
- `bt explain runs/<folder>` rewrites `explanation.md` for a saved run.

Each run is saved in `runs/<timestamp>-<name>/`: `equity.parquet`, `fills.parquet`, `orders.parquet`,
`trades.parquet`, `metrics.json` and `meta.json`, plus `validation.json` and `explanation.md` for validated runs.

---

## 6. Reading the results

- **Total return and annualised return** versus the benchmark.
- **Sharpe and Sortino** — return per unit of risk. Compare against the benchmark, not against zero.
- **Max drawdown** — the worst fall from a peak. Read it alongside return.
- **Trades, win rate, profit factor** — for rebalanced portfolios, every partial sale counts as a trade, so
  these say little. Trust the return and drawdown figures.
- **Validation** — walk-forward results, Monte Carlo spread, Kelly fraction, overfitting statistics,
  regime breakdown, cost stress and the look-ahead check. A flag is a prompt to investigate, not a verdict.
- **Option strategies** — the price sensitivity line in `bt validate` output tells you how much the modelled
  prices could move results.

Assumptions the program makes (read `config/costs.toml` and the README):

- Commission on US stocks and ETFs is zero (IBKR Lite, as stated by the account holder).
- Slippage is 1 basis point per fill. This is an assumption.
- Options cost USD 0.65 per contract. This is an assumption, not read from IBKR.
- Idle cash earns the 13-week Treasury bill yield minus 1%; borrowed cash pays it plus 2.5%.
- Short borrow fees are not modelled.

---

## 7. The dashboard

Start it with `bt serve` (or the launcher). Pages:

| Page | Use it to |
|---|---|
| Home (`/`) | See recent runs and status. |
| New backtest | Pick a strategy, set dates, parameters and costs, and run. |
| Runs | Browse saved runs. Open one for charts (equity and drawdown, monthly returns), validation, the explanation and option surfaces. |
| Compare | Put two runs side by side. The strategy is always the blue series; the benchmark or second run is orange. |
| Re-run | Run a saved strategy again with changed settings. |
| Data | Download prices and rates; see what is cached. |
| Research | Drop a PDF to analyse a paper; search OpenAlex or Consensus; see requests; browse the paper library (claims, status, linked runs). |
| Jobs | Watch a background download, run or analysis, and its activity log. |

The server listens on this computer only, and refuses form posts from other websites.

### Papers and Claude Code

If the `claude` program is installed and signed in, the Research page runs it in the background to analyse
dropped papers and to run Consensus searches. Claude gets read-only access to that one file or search and
no shell. Without it, the page shows a one-line instruction to paste into Claude Code instead.
To point the dashboard at a specific program, set `BACKTEST_CLAUDE` to its path.

---

## 8. Paper libraries and replications

```bash
.venv/bin/bt paper list
.venv/bin/bt paper add --title "..." --authors "..." --year 2026 --finding "..." --claim "..." --full-text
.venv/bin/bt paper status <id> "partly replicated"
.venv/bin/bt paper link <id> runs/<folder>
.venv/bin/bt paper compare <id>
```

Record claims as the paper states them, with page numbers, and mark `--full-text` only when they came from the
full text. Link a run to the claim it tests.

---

## 9. When something goes wrong

Every dashboard error ends with a code such as `BT-PDF-002`. `docs/error-codes.md` explains each code and what to do.

| Symptom | Try |
|---|---|
| Dashboard says "Internal server error" on start | Run `bt doctor`; restart with the launcher. Quote the `BT-HTTP-500` code and the terminal output. |
| Page shows a 404 or 405 error | The server is an older version than the page. Restart with the launcher. |
| A download fails | `bt doctor` checks the internet connection and the data sources. |
| `.venv/bin/python` not found on Windows | Use `.venv\Scripts\python`, or run the launcher, which creates `.venv`. |
| A PDF will not load | Codes `BT-PDF-001` to `BT-PDF-007` say why; the file may be damaged or password-protected. |
| The Claude analysis does not start | Check the `claude` program is installed and signed in; set `BACKTEST_CLAUDE` if it is elsewhere. |
| A result looks too good | Run `bt check`, then `bt validate`, and read the flags. Re-run with `--fill close` or higher `--cost-multiplier` as a stress. |

When asking for help, give the error code, the command you ran, and the terminal output.

---

## 10. Files and folders

| Path | Contents |
|---|---|
| `data/cache/` | Cached price data (Parquet). Generated; not in git. |
| `runs/` | Saved runs. Generated; not in git. |
| `research/` | Paper library and uploaded PDFs. |
| `config/costs.toml` | Commission, fee and slippage assumptions. |
| `config/` | Other settings, including option surface parameters. |
| `strategies/examples/` | Worked strategies. |
| `strategies/intraday_momentum/`, `strategies/regime_optimal/` | Paper replications, each with `spec.md`. |
| `docs/` | Research write-ups, replication results, error codes. |
| `settings.local.json` | Optional OpenAlex key. Git-ignored. Do not commit it. |

---

## 11. Limits

- Only data you have loaded is used. The engine does not fetch prices during a run.
- Results depend on the cost and fill assumptions above. Change them and the result changes.
- Option prices are modelled from a calibrated surface, not market quotes.
- Short borrow costs, market impact and tax are not modelled.
- Backtests of past data do not predict future results.
