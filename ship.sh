#!/bin/bash
# Ship your changes in one command: tests -> push to GitHub -> publish the app.  See scripts/ship.py.
cd "$(dirname "$0")" || exit 1
exec python3 scripts/ship.py "$@"
