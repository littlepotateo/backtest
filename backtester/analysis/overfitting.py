"""Is the result distinguishable from luck, given how many variants were tried?
See docs/research/overfitting-statistics.md.

Sharpe ratios inside this module are per period (not annualised) unless stated.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from backtester.analysis.metrics import TRADING_DAYS
from backtester.analysis.resample import optimal_block_length, stationary_bootstrap_indices
from backtester.engine.result import RunResult

EULER_GAMMA = 0.5772156649015329


# --- Sharpe-ratio statistics -----------------------------------------------------------

def _sr_denominator(sr: float, g3: float, g4: float) -> float:
    return math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))


def probabilistic_sharpe(returns, benchmark_sr: float = 0.0) -> float:
    """Probability that the true (per-period) Sharpe ratio exceeds `benchmark_sr`."""
    r = np.asarray(returns, dtype=float)
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else 0.0
    if n < 3 or sd == 0:
        return float("nan")
    sr = r.mean() / sd
    g3, g4 = float(skew(r)), float(kurtosis(r, fisher=False))
    return float(norm.cdf((sr - benchmark_sr) * math.sqrt(n - 1) / _sr_denominator(sr, g3, g4)))


def min_track_record_length(returns, benchmark_sr: float = 0.0, confidence: float = 0.95) -> float:
    """Observations needed before the Sharpe ratio is above `benchmark_sr` at `confidence`."""
    r = np.asarray(returns, dtype=float)
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    if sd == 0:
        return float("nan")
    sr = r.mean() / sd
    if sr <= benchmark_sr:
        return math.inf
    g3, g4 = float(skew(r)), float(kurtosis(r, fisher=False))
    return 1 + _sr_denominator(sr, g3, g4) ** 2 * (norm.ppf(confidence) / (sr - benchmark_sr)) ** 2


def expected_max_sharpe(n_trials: float, variance: float) -> float:
    """Sharpe ratio expected from the best of `n_trials` strategies with no skill, when
    Sharpe ratios across trials have the given variance."""
    if n_trials <= 1:
        return 0.0
    z = (1 - EULER_GAMMA) * norm.ppf(1 - 1 / n_trials) + EULER_GAMMA * norm.ppf(1 - 1 / (n_trials * math.e))
    return float(math.sqrt(variance) * z)


def effective_trials(returns_matrix: pd.DataFrame) -> float:
    """Approximate number of independent trials among correlated configurations:
    1 + (N - 1) * (1 - average pairwise correlation)."""
    n = returns_matrix.shape[1]
    if n <= 1:
        return float(n)
    corr = returns_matrix.corr().to_numpy()
    avg = np.nanmean(corr[np.triu_indices(n, 1)])
    if not np.isfinite(avg):
        return float(n)
    return float(1 + (n - 1) * (1 - min(max(avg, 0.0), 1.0)))


def deflated_sharpe(returns, n_trials: float, sr_variance: float) -> dict:
    hurdle = expected_max_sharpe(n_trials, sr_variance)
    return {"n_trials": n_trials, "hurdle_sharpe_annual": hurdle * math.sqrt(TRADING_DAYS),
            "probability": probabilistic_sharpe(returns, hurdle)}


# --- Probability of backtest overfitting (CSCV) ------------------------------------------

def pbo_cscv(returns_matrix: pd.DataFrame, n_blocks: int = 10) -> dict:
    """Bailey, Borwein, Lopez de Prado & Zhu: split time into blocks, and for every way
    of choosing half of them as in-sample, see where the in-sample winner ranks
    out-of-sample."""
    m = returns_matrix.dropna().to_numpy()
    t, n = m.shape
    if n < 2:
        raise ValueError("overfitting probability needs at least two configurations")
    if n_blocks % 2 or t < n_blocks * 5:
        raise ValueError("need an even number of blocks and at least 5 observations per block")
    size = t // n_blocks
    blocks = [m[i * size:(i + 1) * size] for i in range(n_blocks)]
    logits, is_perf, oos_perf = [], [], []

    def sr(x):
        sd = x.std(axis=0, ddof=1)
        return np.where(sd > 0, x.mean(axis=0) / np.where(sd > 0, sd, 1), -np.inf)

    for chosen in itertools.combinations(range(n_blocks), n_blocks // 2):
        ins = np.concatenate([blocks[i] for i in chosen])
        oos = np.concatenate([blocks[i] for i in range(n_blocks) if i not in chosen])
        s_in, s_out = sr(ins), sr(oos)
        best = int(np.argmax(s_in))
        rank = (s_out < s_out[best]).sum() + 0.5 * ((s_out == s_out[best]).sum() - 1) + 1
        w = min(max(rank / (n + 1), 1e-9), 1 - 1e-9)
        logits.append(math.log(w / (1 - w)))
        is_perf.append(s_in[best])
        oos_perf.append(s_out[best])
    logits, is_perf, oos_perf = np.array(logits), np.array(is_perf), np.array(oos_perf)
    ok = np.isfinite(is_perf) & np.isfinite(oos_perf)
    slope = float(np.polyfit(is_perf[ok], oos_perf[ok], 1)[0]) if ok.sum() > 2 and is_perf[ok].std() > 0 else None
    return {"pbo": float((logits <= 0).mean()), "splits": int(len(logits)), "configurations": n,
            "blocks": n_blocks, "median_logit": float(np.median(logits)),
            "oos_vs_is_slope": slope,
            "probability_oos_loss": float((oos_perf[ok] < 0).mean()) if ok.any() else None}


# --- Permutation tests ----------------------------------------------------------------

def bar_weights(result: RunResult, data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(weights, asset returns) per bar: each symbol's position value as a fraction of
    equity at each bar close, and each symbol's close-to-close return."""
    idx = result.equity.index
    use_adj = result.meta.get("config", {}).get("use_adjusted", True)
    weights, rets = {}, {}
    for s, df in data.items():
        close = df["close"] * df["adj_factor"] if use_adj and "adj_factor" in df else df["close"]
        close = close.reindex(idx).ffill()
        fills = result.fills[result.fills["symbol"] == s]
        qty = fills.groupby("time")["qty"].sum().cumsum().reindex(idx).ffill().fillna(0.0) \
            if len(fills) else pd.Series(0.0, index=idx)
        weights[s] = qty * close / result.equity
        rets[s] = close.pct_change().fillna(0.0)
    return pd.DataFrame(weights), pd.DataFrame(rets)


def permutation_test(result: RunResult, data: dict[str, pd.DataFrame], n_perm: int = 2000,
                     seed: int = 0) -> dict:
    """Does the strategy's timing beat the same exposures applied to shuffled market
    returns? Market returns are detrended first, so simply being long a rising market
    earns no credit. Approximate: positions are taken as of each bar close."""
    w, r = bar_weights(result, data)
    w_prev = w.shift(1).fillna(0.0).to_numpy()
    detrended = (r - r.mean()).to_numpy()
    actual = float((w_prev * detrended).sum(axis=1).mean())
    rng = np.random.default_rng(seed)
    n = len(detrended)
    perm = np.array([(w_prev * detrended[rng.permutation(n)]).sum(axis=1).mean() for _ in range(n_perm)])
    return {"permutations": n_perm, "seed": seed,
            "p_value": float((1 + (perm >= actual).sum()) / (1 + n_perm)),
            "timing_return_per_bar": actual,
            "drift_return_per_bar": float((w_prev * r.mean().to_numpy()).sum(axis=1).mean()),
            "note": "p-value: chance of timing this good from shuffled, trend-free returns"}


def random_entry_test(result: RunResult, data: dict[str, pd.DataFrame], n_sims: int = 2000,
                      seed: int = 0) -> dict:
    """Compare the trades with random trades of the same direction and holding length
    in the same symbols."""
    t = result.trades
    if len(t) < 2:
        return {"skipped": "fewer than two closed trades"}
    use_adj = result.meta.get("config", {}).get("use_adjusted", True)
    start = result.equity.index[0]
    rng = np.random.default_rng(seed)
    actual = float(t["return"].mean())
    sims = np.zeros(n_sims)
    for s, grp in t.groupby("symbol"):
        df = data[s][data[s].index >= start]
        close = (df["close"] * df["adj_factor"] if use_adj and "adj_factor" in df else df["close"]).to_numpy()
        entry = df.index.searchsorted(pd.DatetimeIndex(grp["entry_time"]))
        exit_ = df.index.searchsorted(pd.DatetimeIndex(grp["exit_time"]))
        hold = np.maximum(exit_ - entry, 1)
        side = np.where(grp["side"].to_numpy() == "long", 1.0, -1.0)
        for h, sd in zip(hold, side):
            if len(close) <= h:
                continue
            e = rng.integers(0, len(close) - h, size=n_sims)
            sims += sd * (close[e + h] / close[e] - 1)
    sims /= len(t)
    return {"simulations": n_sims, "seed": seed, "average_trade_return": actual,
            "random_average_trade_return": float(sims.mean()),
            "p_value": float((1 + (sims >= actual).sum()) / (1 + n_sims))}


# --- Superior predictive ability (Hansen 2005) --------------------------------------------

def spa_test(returns_matrix: pd.DataFrame, n_boot: int = 2000, seed: int = 0,
             block: float | None = None) -> dict:
    """Does the best configuration beat doing nothing, allowing for the fact that it
    was picked from many? Returns Hansen's consistent p-value and White's Reality Check
    p-value (the upper, more conservative one)."""
    d = returns_matrix.dropna().to_numpy()
    n, k = d.shape
    rng = np.random.default_rng(seed)
    if block is None:
        block = float(np.mean([optimal_block_length(d[:, j]) for j in range(k)]))
    mean = d.mean(axis=0)
    boot_means = np.empty((n_boot, k))
    for b in range(n_boot):
        boot_means[b] = d[stationary_bootstrap_indices(n, block, rng)].mean(axis=0)
    omega = np.sqrt(n) * boot_means.std(axis=0, ddof=1)
    omega = np.where(omega > 0, omega, np.inf)
    stat = max(0.0, float(np.max(np.sqrt(n) * mean / omega)))
    threshold = -math.sqrt(2 * math.log(math.log(n)))
    keep = np.sqrt(n) * mean / omega >= threshold

    def p_value(centre):
        z = np.sqrt(n) * (boot_means - centre) / omega
        return float((np.maximum(z.max(axis=1), 0.0) >= stat).mean()) if stat > 0 else 1.0

    return {"configurations": k, "bootstrap_samples": n_boot, "seed": seed, "mean_block": block,
            "statistic": stat, "p_value": p_value(np.where(keep, mean, 0.0)),
            "p_value_reality_check": p_value(mean),
            "best_configuration": int(np.argmax(mean))}
