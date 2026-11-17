#!/usr/bin/env bash
# Brings the program up to date from GitHub before the dashboard starts, so a restart can never run an old version.
# (The explicit refspec makes the fetch work even in a clone whose remote has none configured.)
# It never stops the start-up: any problem is reported in plain words and the code you already have is used.
# Opt out with the environment variable BACKTEST_NO_UPDATE=1.
cd "$(dirname "$0")/.." || exit 0
[ -n "$BACKTEST_NO_UPDATE" ] && exit 0
[ -d .git ] || exit 0
say() { printf '%s\n' "$*"; }
command -v git >/dev/null 2>&1 || { say "Git was not found, so the program cannot update itself. Starting with the code you have."; exit 0; }

branch="$(git branch --show-current 2>/dev/null)"
if ! git fetch --quiet origin "+refs/heads/*:refs/remotes/origin/*" >/dev/null 2>&1; then
  say "Could not check for updates (no internet connection?). Starting with the code you have."
  exit 0
fi

if [ "$branch" != "main" ]; then
  # Never leave work that exists only on this computer: switch only if every commit here is also on GitHub.
  if [ -z "$(git branch -r --contains HEAD 2>/dev/null)" ]; then
    say "You are on the branch '$branch', which has commits that are only on this computer, so it was left alone and no update was made."
    exit 0
  fi
  if git checkout --quiet main >/dev/null 2>&1; then
    say "Switched from '$branch' to 'main', the branch that carries the latest released program."
  else
    say "You are on the branch '$branch' and could not switch to 'main' because of local changes. Starting with the code you have."
    say "To update by hand: git stash push -u, git checkout main, git pull origin main, git stash pop"
    exit 0
  fi
fi

before="$(git rev-parse --short HEAD)"
if git merge --ff-only --quiet origin/main >/dev/null 2>&1; then
  after="$(git rev-parse --short HEAD)"
  [ "$before" != "$after" ] && say "Updated the program: $before -> $after."
else
  say "Could not update automatically (a file you changed is also changed in the new version). Starting with the code you have (version $before)."
  say "To update by hand: git stash push -u, then git pull origin main, then git stash pop"
fi
exit 0
