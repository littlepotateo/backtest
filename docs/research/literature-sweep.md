# Literature sweep (Consensus), 2026-11-14

Searches run through the Consensus connector once it became available. Abstracts were
read; full texts were not. Each finding lists what it changes in this project.

## Findings and their effect

| Finding | Source | Effect on the build |
|---|---|---|
| In a controlled synthetic comparison, combinatorial purged cross-validation (CPCV) beat walk-forward at preventing false discoveries; walk-forward showed "notable shortcomings" and higher variability | [1] | Walk-forward stays (it mirrors how a strategy would actually be re-tuned), but its output now has to be read as weaker evidence than it looks. CPCV goes on the backlog as an additional test. |
| Walk-forward performance depends strongly on the chosen training and test window lengths | [2] | Confirms the rule in `walk-forward.md`: fix the windows before running, never tune them. |
| A deliberately leaky strategy (Sharpe 35) passed both the deflated Sharpe ratio and the probability-of-backtest-overfitting test. Recording every evaluation and deflating by that count rejected all LLM-discovered strategies in their study | [3] | The statistical tests cannot detect look-ahead; the separate truncation test in `analysis/checks.py` is necessary. Our trial ledger matches their approach. Directly relevant, since Claude writes the strategies here. |
| Out-of-sample holdouts become unreliable when many models are selected on them; multiple-testing "haircuts" to the Sharpe ratio are needed | [4], [5] | Supports reporting the deflated Sharpe next to every optimised result. Harvey & Liu's haircut is an alternative to consider. |
| A composite of deflated Sharpe, overfitting probability, SPA and minimum track record separated real from lucky strategies in synthetic markets (AUROC 0.989) but showed **no** forward relationship on unseen real data | [6] | Our flags use the same four quantities. They rank statistical support; they do not predict future profit. The explanation layer (stage 6) must say this. |
| The plug-in Kelly estimate is biased toward over-betting; shrinkage estimators reduce growth loss | [7] | Supports recommending well below the point estimate. |
| Fractional Kelly succeeds "not because of reduced risk, but because of reduced estimation error" | [8] | Same; the rule (smaller of half-Kelly and the 25th-percentile bootstrap estimate) is a shrinkage in that spirit. |
| The stationary bootstrap (Politis & Romano) gave the most precise maximum-drawdown distribution estimates among bootstrap methods | [9], [10] | Confirms the choice in `analysis/montecarlo.py`. |
| IID resampling of backtests is biased when returns are autocorrelated, though often modestly for Sharpe ratios | [11] | Confirms using block resampling as the headline Monte Carlo and showing the plain reshuffle only beside it. |
| Drawdown depth and duration respond differently to skew, fat tails and volatility clustering; a Gaussian table "mis-warns" | [12] | Supports resampling actual returns instead of assuming normality. |
| All six Cboe S&P 500 option-writing indices earned positive alpha over 35 years, plausibly as compensation for short-volatility risk | [13] | Gives an external benchmark: compare our modelled covered-call and put-write backtests with the Cboe BuyWrite (BXM) and PutWrite (PUT) indices. |
| A covered call is equity exposure plus short volatility plus an uncompensated reversal exposure; equity drives most of the risk and return | [14] | The explanation for covered-call results should separate the equity return from the option overlay. |
| For short-dated put-writing, position sizing (Kelly, VIX scaling, hybrid) is a key determinant of long-run performance | [15] | Kelly output for short-premium strategies needs care: the sample may contain no large loss. Already flagged in `monte-carlo.md`. |

## Not yet searched

Black-Litterman extensions, volatility-surface modelling for synthetic option histories,
and permutation-test methodology. The open **[verify]** item on Masters' price-path
permutation recipe remains open.

## References

[1] [Backtest Overfitting in the Machine Learning Era: A Comparison of Out-of-Sample Testing Methods in a Synthetic Controlled Environment](https://consensus.app/papers/details/w:5d377ec1-4c5f-4633-a323-afed6cb5eb4f/?utm_source=claude_desktop) (Arian et al., 2024, SSRN)
[2] [A novel approach to trading strategy parameter optimization using double out-of-sample data and walk-forward techniques](https://consensus.app/papers/details/w:94da67ac-bdfb-4a98-aba5-c99c1fa15c1e/?utm_source=claude_desktop) (Mroziewicz et al., 2026, arXiv)
[3] [What survives honest evaluation? Leakage-safe, search-aware assessment of LLM-driven trading strategy discovery](https://consensus.app/papers/details/w:8ae65f7d-9b56-469d-af09-fbfcb59f0c0e/?utm_source=claude_desktop) (Gençay, 2026, arXiv)
[4] [A Bayesian Approach to Backtest Overfitting](https://consensus.app/papers/details/w:38cfcb00-4a9d-4d35-884e-6b0f00cb1cf8/?utm_source=claude_desktop) (Witzany, 2017, Risks)
[5] [Backtesting](https://consensus.app/papers/details/w:4b27bb58-abcd-49ce-8668-a630f02fed8e/?utm_source=claude_desktop) (Harvey et al., 2015, The Journal of Portfolio Management)
[6] [Equity Strategy Backtesting: Luck or Edge? The MinervaScore as a Statistical Robustness Grade](https://consensus.app/papers/details/w:8b00fdda-5ba9-403a-b242-3fb836a3dfff/?utm_source=claude_desktop) (Santoni et al., 2026, arXiv)
[7] [Shrinkage estimation of Kelly portfolios](https://consensus.app/papers/details/w:1b51ad51-9abe-43dc-9b5c-1e2711228076/?utm_source=claude_desktop) (Han et al., 2018, Quantitative Finance)
[8] [Partial Kelly portfolios and shrinkage estimators](https://consensus.app/papers/details/w:a1009681-78ec-4e3a-b475-14d3b95f1fef/?utm_source=claude_desktop) (Rising et al., 2012, IEEE ISIT)
[9] [Bootstrapping and Bias: The Economic Costs of Misjudging Downside Risk](https://consensus.app/papers/details/w:b1538075-1f04-4462-a9ef-1ed604439c7d/?utm_source=claude_desktop) (Dichtl et al., 2026, The Journal of Portfolio Management)
[10] [The Stationary Bootstrap](https://consensus.app/papers/details/w:3e6e9bbf-33ef-4d64-bcdb-008aa6a77a45/?utm_source=claude_desktop) (Politis et al., 1994, JASA)
[11] [The bias of IID resampled backtests for rolling window mean-variance portfolios](https://consensus.app/papers/details/w:127d123e-70ee-4ec0-969a-50e2f2f4ca36/?utm_source=claude_desktop) (Paskaramoorthy et al., 2025, Investment Analysts Journal)
[12] [Drawdown Risk Beyond Brownian Motion](https://consensus.app/papers/details/w:de721b5f-def3-4670-872d-6b21be74abaa/?utm_source=claude_desktop) (Landolfi, 2026, SSRN)
[13] [35-Year Performance Analysis of Cboe S&P 500 Option-Selling Indices](https://consensus.app/papers/details/w:6d5b7104-dfbd-41fb-9a5e-afcb301bfafe/?utm_source=claude_desktop) (Black et al., 2022, The Journal of Beta Investment Strategies)
[14] [Covered Calls Uncovered](https://consensus.app/papers/details/w:4ae0e8de-b901-485e-8e6d-da30669ec3ef/?utm_source=claude_desktop) (Israelov et al., 2015, Financial Analysts Journal)
[15] [Sizing the risk: Kelly, VIX, and hybrid approaches in put-writing on index options](https://consensus.app/papers/details/w:f47fdf66-b675-49e3-9ad6-fa5d00c7c766/?utm_source=claude_desktop) (Wysocki, 2026, Knowledge-Based Systems)
