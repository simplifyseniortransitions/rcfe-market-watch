#!/bin/bash
# RCFE Deal Room Market Watch — weekly pipeline.
#   ./run.sh                 process every CSV dropped in inbox/
#   ./run.sh --file X.csv    process one file (add --as-of YYYY-MM-DD if the
#                            date is not in the file name)
#   ./run.sh test            run the automated tests
#   ./run.sh golden          compare Oct 18 metrics with the acceptance numbers
set -euo pipefail
cd "$(dirname "$0")"

# This project always uses Homebrew's Python 3.12, by full path, inside its own
# .venv folder. It never touches Apple's python3 or your other apps.
PY312="/opt/homebrew/opt/python@3.12/bin/python3.12"
VENV_PY=".venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  if [ ! -x "$PY312" ]; then
    echo "Python 3.12 was not found at $PY312"
    echo "Install it with:  brew install python@3.12   then run ./run.sh again."
    exit 1
  fi
  echo "First-time setup: creating the project's private Python environment..."
  "$PY312" -m venv .venv
fi

# Install/refresh libraries only when requirements.txt changes.
REQ_HASH="$(shasum -a 256 requirements.txt | cut -d' ' -f1)"
if [ ! -f .venv/.requirements-hash ] || [ "$(cat .venv/.requirements-hash)" != "$REQ_HASH" ]; then
  echo "Installing libraries (one time)..."
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet -r requirements.txt
  echo "$REQ_HASH" > .venv/.requirements-hash
fi

export PYTHONPATH="$PWD"

case "${1:-}" in
  test)
    shift
    exec "$VENV_PY" -m pytest "$@"
    ;;
  golden)
    exec "$VENV_PY" -m pipeline.golden
    ;;
  *)
    exec "$VENV_PY" -m pipeline.run "$@"
    ;;
esac
