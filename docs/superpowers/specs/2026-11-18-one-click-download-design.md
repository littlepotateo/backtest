# One-click download: design

**Request (account holder, 2026-11-18):** "I want this program to be a one-click download program, where it can work out of the box."

## What "one click" means here

A person who has never heard of Python, Git or a terminal downloads **one file** from the project's GitHub releases page, double-clicks it, clicks through a standard installer, and gets a desktop icon. Double-clicking the icon opens the dashboard in the browser. Prices for the example strategies download by themselves on the first start, and the "New backtest" page can run an example within minutes. Updates arrive by a button in the dashboard. Nothing is typed.

## Decisions (each with the reason it was chosen)

1. **Windows 10/11 64-bit first.** The account holder uses Windows. macOS and Linux installers are out of scope; `start.sh` / `Start Backtester.command` keep working for them. The design leaves the seam (a bundle assembled per platform).
2. **Ship the program as ordinary Python files inside a bundled Python runtime** (the official Windows "embeddable" Python plus the installed packages), not as a PyInstaller executable. Reason: strategies are `.py` files that Claude Code writes and the engine imports at run time, and background jobs start `sys.executable -m backtester.cli`; both work unchanged with a real interpreter and break or need workarounds in a frozen executable. Frozen executables also trigger antivirus false positives more often.
3. **One installer, built by GitHub Actions.** An Inno Setup `.exe`, per-user (no administrator rights), installs to `%LOCALAPPDATA%\Programs\Strategy Backtester`, adds Start Menu and optional desktop shortcuts, and offers to launch. Releases are created as **drafts**; the account holder presses "Publish".
4. **Program and user data are separate.** Program: the install folder (replaced on update, removed on uninstall). Data: `Documents\Strategy Backtester` (runs, data cache, research library, strategies, config, settings, logs); never touched by update or uninstall. If Documents is redirected (OneDrive) it is resolved through the Windows API; if it is not writable the fallback is `%LOCALAPPDATA%\Strategy Backtester\data`.
5. **No console window.** The shortcut runs `pythonw.exe -m backtester.desktop`: one dashboard per computer (a second click opens the existing one), logs to a file in the data folder, a **Quit** button in the dashboard and a "Stop Strategy Backtester" Start Menu entry. Server stays bound to 127.0.0.1.
6. **First run works without choices.** On first start the data folder is seeded (config defaults, example strategies; existing files are never overwritten) and the starter data download runs in the background (daily prices 2005 onward for SPY, QQQ, IWM, EFA, EEM, IEF, AGG, GLD, DBC, VNQ; the volatility indices ^VIX, ^VXN, ^RVX; T-bill yield ^IRX). It is offered once automatically; afterwards a button on the Home page.
7. **Updates are one click, never silent.** At start, a background check reads the latest GitHub release; if newer, a banner offers "Update now": download the installer, verify its SHA-256 (published in the release notes), run it silently, restart. Failure of the check is silent; failure of the update is explained with a code. Source checkouts keep using `scripts/update.sh|bat`.
8. **Claude Code stays optional and separate.** Signing in to Claude cannot be bundled. Backtesting, data and results work without it; the Home page explains in three steps how to add it for paper analysis and Consensus search (detection already exists).

## Non-goals

macOS/Linux installers; code signing (Windows SmartScreen will warn that the publisher is unknown, documented with the exact clicks; signing is a later purchase); bundling price data; auto-installing Claude Code; an application icon beyond the default.

## Constraints that shaped this

- The runtime packages are about 0.5 GB unpacked (pyarrow 175 MB, scipy 138, pandas 77, numpy 68, plotly 58). Target after pruning: installed size at most 450 MB, installer at most 200 MB, enforced in the build.
- Unsigned installers raise warnings; the installer must therefore be per-user and the documentation must show the two clicks.
- The Python in the bundle uses the platform's default text encoding unless told otherwise: the launcher sets `PYTHONUTF8=1` (the project already requires UTF-8 for every file).
- This sandbox is Linux: the Windows build can only be verified by running the GitHub Actions workflow (with a smoke test of the installed copy) or by the account holder.

## Assumptions to confirm

- Windows only for now. - Releases come from the public repository `littlepotateo/backtest`. - Unsigned is acceptable for now. - The first release is `v0.2.0`.
