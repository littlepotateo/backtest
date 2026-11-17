#!/usr/bin/env bash
# Starts the dashboard. The first run sets everything up (about a minute); later runs start at once.
# Mac: double-click "Start Backtester.command". Linux: ./start.sh
set -e
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }
has_new_python() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }

if [ -x .venv/bin/python ] && ! has_new_python .venv/bin/python; then
  say "The .venv folder was built with an older Python; rebuilding it."
  rm -rf .venv
fi

if [ ! -x .venv/bin/python ]; then
  PY=""
  for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && has_new_python "$(command -v "$c")"; then PY="$(command -v "$c")"; break; fi
  done
  if [ -z "$PY" ]; then
    say "This needs Python 3.11 or newer, and none was found."
    say "  Mac:    install it from https://www.python.org/downloads/  (or: brew install python@3.12)"
    say "  Linux:  install python3.11 or newer with your package manager"
    say "Then run this again."
    exit 1
  fi
  say "Setting up (first run only) using $PY ..."
  "$PY" -m venv .venv
fi

STAMP=".venv/.installed-stamp"
NOW="$(.venv/bin/python -c "import hashlib; print(hashlib.sha256(open('pyproject.toml','rb').read()).hexdigest())")"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$NOW" ] || [ ! -x .venv/bin/bt ]; then
  say "Installing the backtester and its dependencies ..."
  # The install output is kept in a file and shown only if something goes wrong.
  if ! { .venv/bin/python -m pip install --quiet --upgrade pip && .venv/bin/python -m pip install --quiet -e .; } > .venv/install.log 2>&1; then
    cat .venv/install.log
    say "The installation failed (see above). If it mentions the network, check the internet connection and run this again."
    exit 1
  fi
  printf '%s' "$NOW" > "$STAMP"
fi

OPEN="--open"
[ -n "$BACKTEST_NO_BROWSER" ] && OPEN=""
exec .venv/bin/bt serve $OPEN "$@"
