"""Predictive regressions of the last half-hour return (Gao, Han, Li and Zhou, 2017, section 3): OLS with Newey-West t-statistics,
recursive out-of-sample forecasts, and the out-of-sample R-squared of equation (3).

Assumptions the paper leaves open (written down in spec.md): the Newey-West lag is `floor(4 (T/100)^(2/9))`; the recursive forecasts
are re-estimated once a month, on all data up to the end of the previous month (the paper "progressively adds one more month");
the variance forecast used for sizing is the residual variance of the training regression.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def default_lags(n: int) -> int:
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


def _fit(y: np.ndarray, Z: np.ndarray):
    beta = np.linalg.lstsq(Z, y, rcond=None)[0]
    return beta, y - Z @ beta


def predictive_regression(y: pd.Series, X: pd.DataFrame, lags: int | None = None) -> dict:
    """y = const + X b + e. Returns coefficients, Newey-West t-statistics, R-squared (a fraction), n and the lag used."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    yy, XX = d["y"].to_numpy(), d[list(X.columns)].to_numpy()
    n = len(d)
    Z = np.column_stack([np.ones(n), XX])
    beta, e = _fit(yy, Z)
    L = default_lags(n) if lags is None else lags
    g = Z * e[:, None]
    S = g.T @ g
    for l in range(1, L + 1):
        G = g[l:].T @ g[:-l]
        S += (1 - l / (L + 1)) * (G + G.T)
    bread = np.linalg.inv(Z.T @ Z)
    se = np.sqrt(np.diag(bread @ S @ bread))
    names = ["const", *X.columns]
    r2 = 1 - (e @ e) / (((yy - yy.mean()) ** 2).sum())
    return {"coef": dict(zip(names, map(float, beta))), "t": dict(zip(names, map(float, beta / se))), "r2": float(r2), "n": n, "lags": L}


def scale_like_table1(res: dict) -> dict:
    """The scaling of the paper's Table 1: the intercept annualised (x252) and in percent, slopes multiplied by 100, R-squared in percent."""
    out = {k: (v * 252 * 100 if k == "const" else v * 100) for k, v in res["coef"].items()}
    out["r2_pct"] = res["r2"] * 100
    return out


def recursive_forecast(y: pd.Series, X: pd.DataFrame, start, min_obs: int = 60) -> pd.DataFrame:
    """Out-of-sample forecasts of y for every day from `start` on. Each month the regression is re-estimated on all earlier months only.
    Columns: y, rhat (regression forecast), rbar (historical mean forecast), sigma2 (residual variance of the training regression),
    const and beta_<name> (the coefficients used)."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    dates = pd.Series(d.index, index=d.index)
    month = pd.Series([(x.year, x.month) for x in d.index], index=d.index)
    start = pd.Timestamp(start).date()
    out = []
    for key in sorted(set(month[dates >= start])):
        first_day = min(dt for dt in d.index[month == key])
        train = d[[dt < first_day for dt in d.index]]
        if len(train) < min_obs:
            raise ValueError(f"only {len(train)} observations before {first_day}; at least {min_obs} are needed to start the recursion")
        Z = np.column_stack([np.ones(len(train)), train[list(X.columns)].to_numpy()])
        beta, e = _fit(train["y"].to_numpy(), Z)
        sigma2 = float(e @ e / (len(train) - Z.shape[1]))
        test = d[month == key]
        test = test[[dt >= start for dt in test.index]]
        rhat = beta[0] + test[list(X.columns)].to_numpy() @ beta[1:]
        frame = pd.DataFrame({"y": test["y"], "rhat": rhat, "rbar": float(train["y"].mean()), "sigma2": sigma2, "const": beta[0]},
                             index=test.index)
        for i, name in enumerate(X.columns):
            frame[f"beta_{name}"] = beta[1 + i]
        out.append(frame)
    return pd.concat(out)


def r2_oos(y, rhat, rbar) -> float:
    """Equation (3): 1 - sum (y - rhat)^2 / sum (y - rbar)^2. Positive means the regression forecast beats the historical mean."""
    y, rhat, rbar = (np.asarray(v, dtype=float) for v in (y, rhat, rbar))
    return float(1 - ((y - rhat) ** 2).sum() / ((y - rbar) ** 2).sum())
