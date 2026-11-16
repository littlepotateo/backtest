---
name: backtest
description: Use when the user describes a trading or investment strategy (stocks, ETFs, intraday, options, portfolio allocation) and wants it backtested, validated and explained, or gives a research paper or asks to find papers on a strategy idea and test them. Writes the strategy code, loads data, runs the checks and tests, and writes the explanation.
---

# Backtest a strategy from a description or a paper

You turn a plain-language strategy into code, run it through this repository's engine,
validate it, and explain the result honestly. The engine, the tests and the explanation
template already exist; do not rebuild them. Never state a number that did not come from
a run in this repository.

## Workflow

1. **Understand the strategy.** If the description leaves out something that changes
   the result (universe, period, rebalance rule, sizing, what happens on a signal
   flip), ask one question at a time. Otherwise choose a default, and write it down as
   an assumption in the spec.
2. **Write `strategies/<name>/spec.md`.** Rules in plain words, independent of any
   engine; universe; period; sizing; costs; every assumption you made and why; for a
   paper, the paper's claimed results with where they come from.
3. **Write `strategies/<name>/strategy.py`.** One `Strategy` subclass (see "Strategy
   interface"). Declare `param_grid` for parameters worth testing, and `valid_params`
   if some combinations make no sense.
4. **Get the data** (see "Data"). Run `bt data` to confirm what is cached.
5. **Run the checks, then the backtest, then the validation**:
   ```bash
   .venv/bin/bt check strategies/<name>/strategy.py --start YYYY-MM-DD
   .venv/bin/bt run strategies/<name>/strategy.py --start YYYY-MM-DD
   .venv/bin/bt validate strategies/<name>/strategy.py --start YYYY-MM-DD --risk-free 0.02
   ```
   A failed look-ahead check stops everything: fix the strategy first. `bt validate`
   saves `runs/<id>/validation.json` and `explanation.md`.
6. **Write `runs/<id>/narrative.md`** on top of the generated explanation (see
   "Narrative").
7. **Tell the user**: the headline numbers, the flags that matter, what you assumed, and
   what you could not verify. Offer the next step; do not oversell.

## Strategy interface

```python
from backtester import Strategy

class MyStrategy(Strategy):
    universe = ["SPY"]                 # symbols traded
    interval = "1d"                    # "1d", "1h", "5m", ...
    params = {"fast": 50, "slow": 200} # defaults; override with --param fast=20
    param_grid = {"fast": [20, 50, 100], "slow": [150, 200, 250]}
    options_on = []                    # underlyings whose options it trades

    @classmethod
    def valid_params(cls, p): return p["fast"] < p["slow"]

    def init(self, ctx): ...           # once, before the first bar
    def on_bar(self, ctx): ...         # after each bar closes
```

`ctx` shows only bars up to and including the one that just closed. Orders fill at the
next bar's open.

- Data: `ctx.closes(sym, n)`, `ctx.history(sym, n)`, `ctx.price(sym)`, `ctx.returns(symbols, n)`, `ctx.now`
- Session (intraday): `ctx.bars_into_session(sym)`, `ctx.bars_left_in_session(sym)`, `ctx.session_date(sym)`
- Account: `ctx.equity`, `ctx.cash`, `ctx.position(sym)`
- Orders: `ctx.order(sym, qty)`, `ctx.order_target(sym, shares)`, `ctx.order_target_percent(sym, pct)`, `ctx.rebalance({sym: weight})`
- Records: `ctx.record(name, value)` saves values (e.g. weights) into the run
- Weights: `from backtester.portfolio import allocate, View`; methods `equal`, `inverse_vol`, `risk_parity`, `min_variance`, `mean_variance`, `black_litterman`
- Options (declare `options_on`): `ctx.options.select(sym, "C"|"P", dte, delta=|strike=|pct=)`, `.order(contract, n)` (negative = sell), `.close(contract)`, `.positions(sym)`, `.price(contract)`, `.greeks(contract)`. Only defined-risk books are accepted: covered calls, cash-secured puts, spreads, condors. An uncovered short is rejected and recorded.

Look at `strategies/examples/` first: `sma_cross.py` (trend), `opening_range_breakout.py`
(intraday), `etf_allocation.py` (portfolio, Black-Litterman), `faber_timing.py` (monthly
timing), `covered_call.py`, `cash_secured_put.py`, `iron_condor.py`.

**Never** read data from outside `ctx` (the look-ahead test only sees what the engine
supplies), never use `ctx._sim`, and never size from future information.

## Data

- **Yahoo (default for history):** `bt fetch-yahoo SPY --start 2005-01-01`; intraday only goes back about 60 days (5-minute).
  Also `bt fetch-rates` (Treasury bill yield, needed for interest) and volatility indices (`^VIX`, `^VXN`) for options.
- **IBKR connector (cross-check, intraday):** call `get_price_history` (contract id from `search_contracts`), save the JSON
  response to a file, then `bt ingest-ibkr SYMBOL file.json`; `bt compare-ibkr SYMBOL file.json` compares it with cached
  Yahoo bars. IBKR returns at most five years and the response passes through the conversation, so keep pulls small.
  Option history for expired contracts does not exist: option prices are modelled.
- **Options:** run `bt calibrate-options` on a snapshot of real quotes when you can (see `data/calibration/`); say what the
  pricing error was. Options results are a range, not a point; quote the pricing-sensitivity line.
- Always state the data source, the period and whether prices are adjusted.

## Narrative

Start from `explanation.md` (generated from the numbers). In `narrative.md`, add what a
careful analyst would: what the strategy is really exposed to (equity beta, short
volatility, trend), why it did or did not work in the periods that mattered, what the
flags mean in practice, how much capital and drawdown it would have required, and what to
try next. Rules:

- Use only numbers from `metrics.json`, `validation.json` or the explanation.
- Say plainly when a test could not run or a sample is too short.
- The statistical measures rank evidence; they do not forecast profit. Look-ahead is
  detected only by the truncation test.
- Keep risk (how much could be lost) separate from evidence (whether there is an edge).
- Mention unconfirmed assumptions: slippage, modelled option prices, survivorship.

## Papers

1. **Find:** use the Consensus `search` tool (at most three searches at once). Present
   results with the numbered citations and links Consensus gives, and include the
   upgrade line the tool returns, word for word.
2. **Save the ones the user wants:** `bt paper add --title ... --authors ... --year ... --venue ... --url ... --consensus-id ... --finding "..."`.
3. **Read the paper.** Search results are abstracts only. For rules and reported results
   you need the full text: ask the user for the PDF if the connector cannot supply it.
   Record claims with `--claim "..."` **as the paper states them**; pass `--full-text` only
   if you read the full text. Never fill in numbers from memory.
4. **Write the spec** with the rules, universe, period and claimed results; list every
   assumption where the paper is vague; note where your data differs (period, instruments).
5. **Implement, run, validate**, then `bt paper link <paper-id> runs/<id>` and
   `bt paper compare <paper-id>`. Judge the claims yourself in the notes: replicated,
   partly, or not, and why. A different period or instrument is not a failed replication.
   Set `bt paper status <paper-id> <status>`.

## Rules of conduct

- Do not run live trading or place orders; this is research only.
- Report failures and unverified items as plainly as successes.
- Commit work in small steps on a branch; open a draft pull request.
