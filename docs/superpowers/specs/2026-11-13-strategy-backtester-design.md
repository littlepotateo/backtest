# Strategy Backtester — design and build plan

## Context

You want a personal tool where you describe a trading or investment strategy in plain
English (or hand over a research paper) and get back: working strategy code, a backtest,
a set of robustness tests (walk-forward, Monte Carlo, Kelly sizing and more), and a
plain-language explanation of what the results mean. It must cover stock/ETF strategies
(daily and intraday) and options strategies.

Nothing exists yet: `/home/user` is empty and is not a repository.

### Decisions you made
- **Personal local web app**, as an interactive dashboard.
- **Claude Code is the AI engine**: no API key. Claude Code reads the description or paper,
  writes the strategy, runs the tools and writes the explanation.
- **Interactive Brokers** as the data source.
- **Stocks, ETFs and options** in the first version.
- Code lives in a **new GitHub repository** that you create and attach.

### Added after your review
- **Research first**: before any test is built, each method is researched in depth and
  written up with sources; the build follows those write-ups.
- **Consensus** for finding research papers on any strategy.
- **Black-Litterman** as a portfolio-allocation method for investment strategies
  (it does not price options; options stay on Black-Scholes).
- **3D gamma surfaces**: per-contract gamma over strike × time to expiry, and a strategy's
  total position gamma over underlying price × time.

### What I found that shapes the design
- **Consensus is already connected to your Claude account** but switched off for this
  session, so its tools are not loaded here. It needs to be enabled in your claude.ai
  connector settings. I found no public API key for it, so paper search runs through
  Claude Code, not from the dashboard on its own. Full-text retrieval may depend on your
  Consensus plan; where it is unavailable, you supply the PDF.
- The IBKR connector works (SPY bars pulled successfully) but returns **at most 5 years**,
  and only Claude can call it; a Python program cannot. So Claude fetches, and the
  program reads from a local cache.
- IBKR has **no history for expired options**, only chains live today. Options backtests
  must use modelled prices.
- Yahoo Finance and PyPI are reachable from this environment; Stooq is not.

### My calls (not things you chose — say so if you disagree)
- Python engine, written for this project rather than wrapping an existing library.
- Yahoo Finance as fallback for history beyond 5 years and for re-runs from the dashboard.
- Options priced by model (Black-Scholes with a volatility surface), checked against
  today's live IBKR chain, with an import slot for real option data later.
- Dashboard built with FastAPI + server-rendered pages + Plotly charts (no JS build step).
- Every result carries a label saying which data source and pricing assumptions it used.

## Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| **Own small bar-by-bar engine** with one strategy interface for stocks, intraday and option legs | More code to write and test; full control, options treated as first-class, look-ahead prevented by construction | **Chosen** |
| Wrap an existing library (backtesting.py, vectorbt, backtrader) | Fast start for stocks; none handle multi-leg options, expiry and assignment well, so options would become a second, separate engine | Rejected |
| QuantConnect LEAN | Most complete, real option data available with a subscription; heavy (Docker/C#), slow to iterate, poor fit for a small personal app | **Not now, kept open** — see "LEAN-ready seams" |

## How it works

```
You: "Buy SPY when 50-day avg crosses above 200-day, sell on the reverse"   (or a PDF)
        │
Claude Code (project skill: backtest)
  1. writes strategies/<name>/spec.md   – rules, assumptions, anything ambiguous
  2. writes strategies/<name>/strategy.py
  3. fetches data via IBKR connector → saves to data cache
  4. runs: bt check → bt run → bt validate
  5. writes runs/<id>/explanation.md from the structured findings
        │
Dashboard (http://localhost:8000)
  list of runs · charts · metrics · test results · explanation
  re-run with different dates / parameters / test methods (no Claude needed)
```

### Parts

1. **Data layer** (`backtester/data/`)
   - Cache: one Parquet file per symbol and bar size under `data/cache/`.
   - `bt ingest`: converts IBKR connector output (columnar JSON: time/open/high/low/close/volume)
     into the cache. Intraday is pulled in chunks and stitched.
   - Yahoo provider (daily back decades; 1-hour ≈ 2 years; 5-min ≈ 60 days), CSV import.
   - Records source, date range and adjustment status per file. Whether IBKR bars are
     split/dividend adjusted is checked during build (`include_corporate_actions`).

2. **Engine** (`backtester/engine/`)
   - Strategy interface: `params`, `universe`, `init(ctx)`, `on_bar(ctx)`.
   - `ctx` only exposes data up to the current bar, so a strategy cannot see the future.
   - Orders fill on the next bar's open by default; commissions modelled on IBKR's
     schedule; configurable slippage; shorting, cash, margin and position limits.
   - Works on any bar size, with session awareness for intraday (e.g. flat by close).

3. **Options** (`backtester/options/`)
   - Black-Scholes pricing and greeks with dividends and a risk-free rate series.
   - Volatility surface: level from VIX (index products) or realised volatility times a
     premium ratio (single names), plus skew and term-structure parameters; ratio and skew
     calibrated to today's live IBKR chain.
   - Synthetic chain per day: select contracts by days-to-expiry and delta or strike.
   - Multi-leg positions (covered call, cash-secured put, verticals, iron condor, straddle,
     calendar), bid/ask spread model, expiry, exercise and assignment.
   - Loader interface for real historical chains (CSV/Parquet) so paid data drops in later.
   - **3D gamma surfaces** (rotatable Plotly charts in the dashboard):
     (a) per-contract gamma over strike × time to expiry, for any backtest date from the
     modelled chain and for today from the live IBKR chain;
     (b) the strategy's total position gamma over underlying price × time, for any open
     position in a run.

3b. **Portfolio allocation** (`backtester/portfolio/`)
   - Weighting methods usable inside any investment strategy at each rebalance:
     equal weight, inverse volatility, risk parity, mean-variance, and **Black-Litterman**.
   - Black-Litterman: market-implied equilibrium returns (from benchmark weights and a
     covariance estimate) blended with views and view confidences, then optimised with
     constraints (long-only, weight caps). Views can be stated in the strategy description
     ("tech outperforms utilities by 3%") or generated by a rule (e.g. momentum signal).
   - Only data available at the rebalance date is used.

4. **Analysis and validation** (`backtester/analysis/`)
   - Metrics: return, CAGR, volatility, Sharpe, Sortino, Calmar, max drawdown and duration,
     win rate, profit factor, expectancy, exposure, turnover, alpha/beta vs benchmark.
   - In-sample / out-of-sample split.
   - Walk-forward optimisation (rolling and anchored) with walk-forward efficiency.
   - Parameter sensitivity grid and heatmap.
   - Monte Carlo: trade-order reshuffle, block bootstrap of returns, random trade skipping,
     price-noise injection → distributions of return and drawdown, risk of ruin.
   - Kelly criterion: full and fractional, from trade outcomes and from return series, with
     a growth-versus-leverage curve.
   - Overfitting checks: probabilistic and deflated Sharpe ratio, random-entry permutation test.
   - Regime breakdown (bull / bear / high-volatility), cost stress (2× and 3× costs).
   - `bt check`: look-ahead test (signals must be identical when future data is cut off),
     minimum trade count, data gaps.

5. **Explanation** (`backtester/explain/`)
   - The engine writes `findings.json`: every metric plus rule-based flags with severity
     (e.g. "walk-forward efficiency 0.31 — likely overfit", "only 14 trades — not
     statistically meaningful", "edge disappears at 2× costs").
   - A template turns findings into a baseline written explanation, so dashboard re-runs
     always have one.
   - When Claude Code runs the strategy it writes a fuller narrative on top: what worked,
     what didn't, why, how much to trust it, and what to try next.

6. **Dashboard** (`backtester/web/`)
   - Runs list; run page with equity curve, drawdown, trades, monthly returns, each test's
     charts, and the explanation.
   - Re-run form: dates, parameters, costs, which tests. Jobs run as background processes.
   - Compare two runs side by side. Storage is plain folders under `runs/`.

7. **Claude Code integration** (`.claude/skills/backtest/`, `CLAUDE.md`)
   - Skill describing the workflow above, the strategy interface, and worked examples
     (trend following, opening-range breakout, covered call, iron condor, monthly rebalance).
   - **Paper search with Consensus**: "find research on <strategy idea>" searches Consensus,
     and results (title, authors, year, journal, key finding, link) are saved to
     `research/library/` so they persist. You pick a paper; Claude retrieves the full text
     through Consensus where your plan allows, otherwise from a PDF you provide.
   - The dashboard gets a **Research page**: the saved paper library, which papers have
     been turned into strategies, and each paper's claimed-versus-replicated results.
   - Paper workflow: read the paper, extract rules/universe/period/claimed results into
     `spec.md`, list assumptions where the paper is vague, implement, then compare the
     replication against the paper's reported numbers.

### LEAN-ready seams (so QuantConnect LEAN can be added later without a rewrite)

LEAN is not built now, but these boundaries are in from the first stage:

- **Swappable execution backend.** Everything that runs a backtest goes through one
  interface, `Backend.run(strategy, config) -> RunResult`. The engine built here is the
  first backend (`native`); LEAN would be a second (`lean`, driving the LEAN CLI/Docker).
  Each run records which backend produced it.
- **One result format.** `RunResult` (equity curve, orders, fills, trades, positions,
  metadata) is the only thing the validation suite, explanation layer and dashboard read.
  A LEAN backend only has to convert LEAN's result JSON into it; walk-forward, Monte
  Carlo, Kelly, the explanations and all charts then work unchanged.
- **Engine-neutral strategy spec.** `spec.md` describes the rules without reference to
  any engine, so Claude can generate either a native strategy or a LEAN `QCAlgorithm`
  from the same spec.
- **Strategy interface shaped like LEAN's.** `init` / `on_bar`, target-percent orders,
  and option selection by days-to-expiry and strike/delta range mirror LEAN's
  `initialize` / `on_data`, `set_holdings` and option filters, so strategies translate
  mechanically.
- **Data.** Symbols, bar sizes and time zones follow conventions that map onto LEAN's;
  the cache gets an export path to LEAN's data folder format, and the real-option-data
  loader slot is where QuantConnect option data would plug in.
- **Research write-up** `docs/research/lean-integration.md` (stage 1): how LEAN's CLI,
  data format and result JSON work, what a `lean` backend needs, and its costs
  (Docker, data subscription), so the later decision is quick.

### Limits to be upfront about
- Option results are estimates from modelled prices, not real quotes. Good for judging
  whether a structure has an edge; weaker on fill realism and volatility skew.
- IBKR intraday history passes through the Claude session, so very long minute-level
  histories are slow to pull; long intraday tests will be limited by available data.
- No live trading, no order placement, and results are not investment advice.

## Build order

Each stage ends with working, tested software, committed and pushed (draft PR per stage).

0. **Setup needed from you**: (a) create an empty GitHub repo and give me its name;
   (b) enable the Consensus connector in your claude.ai connector settings. I attach the repo,
   scaffold the Python project (`pyproject.toml`, `backtester/`, `tests/`), and commit this
   design as `docs/superpowers/specs/2026-11-13-strategy-backtester-design.md`.
1. **Research (no test code is written before this is done).** For each method —
   walk-forward, Monte Carlo variants, Kelly, in/out-of-sample, parameter sensitivity,
   probabilistic and deflated Sharpe, permutation tests, regime analysis, cost stress,
   look-ahead detection, option pricing and volatility-surface modelling, gamma surfaces,
   Black-Litterman and the other weighting methods — a write-up in `docs/research/<method>.md`:
   what it measures, the original and key follow-up papers, the exact formulas, known
   pitfalls and how practitioners misuse it, implementation choices with a recommendation,
   how existing open-source libraries implement it, and known-answer test cases.
   Sources: Consensus (once enabled) for the academic literature, web search for
   practitioner material and library source code. You review the write-ups; anything they
   change in this design is updated before building.
2. **Data + engine for stocks/ETFs** (daily and intraday), metrics, `bt` command line.
3. **Validation suite**, built to the research write-ups, plus `bt check`.
4. **Portfolio allocation**, including Black-Litterman.
5. **Options**: pricing, volatility surface, synthetic chains, multi-leg positions, gamma surfaces.
6. **Explanation layer** and **Claude Code skill**, including Consensus search and the paper workflow.
7. **Dashboard**, including the Research page and 3D charts.

Tests are written first for each piece.

## Verification

- **Unit tests with known answers** (`pytest`): buy-and-hold equals the asset's return;
  costs reduce returns by the exact expected amount; Black-Scholes matches published
  values and put-call parity; Kelly matches the closed form for a coin-flip bet; the
  look-ahead check catches a deliberately cheating strategy.
- **End-to-end, from a plain description**, using real IBKR data:
  0. Black-Litterman: with no views the weights equal the market weights; a published
     worked example (He & Litterman) is reproduced. Gamma surface values match
     Black-Scholes gamma at spot-checked points.
  1. Daily: SPY 50/200-day moving-average crossover.
  2. Intraday: opening-range breakout on 5-minute bars.
  3. Options: monthly covered call and an iron condor on SPY.
  4. Investment: monthly-rebalanced multi-ETF momentum portfolio.
  5. Paper: one published strategy paper (yours, or a well-known momentum paper),
     comparing replication against the paper's reported results.
- **Dashboard**: start the server, open each run in the pre-installed browser, screenshot
  the pages, re-run one strategy with changed parameters from the form.
- Calibration check: modelled option prices compared against today's live IBKR chain,
  with the error reported.
