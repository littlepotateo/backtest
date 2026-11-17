#!/bin/bash
# Double-click this file on a Mac to start the dashboard. A Terminal window opens and stays open
# while the dashboard runs; close it (or press Ctrl+C) to stop.
cd "$(dirname "$0")" || exit 1
./start.sh
status=$?
if [ $status -ne 0 ]; then
  echo
  echo "Something went wrong (see the message above). Press Enter to close this window."
  read -r _
fi
