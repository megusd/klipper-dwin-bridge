#!/usr/bin/env bash
set -euo pipefail

# run_tests.sh - activate venv, run pytest, print PASS/FAIL
# Usage: ./run_tests.sh [venv_path]

VENV_PATH=${1:-.venv}

# Resolve repository root (script directory)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT="$SCRIPT_DIR"
SRC_PATH="$PROJECT_ROOT/src"

if [ -d "$VENV_PATH" ]; then
  # shellcheck disable=SC1091
  source "$VENV_PATH/bin/activate"
else
  echo "Virtualenv not found at $VENV_PATH; continuing with system Python"
fi

# Ensure local src/ is on PYTHONPATH so tests can import modules from it
export PYTHONPATH="$SRC_PATH":${PYTHONPATH:-}

if python3 -m pytest "$SRC_PATH" -v; then
  echo "PASS"
  exit 0
else
  echo "FAIL"
  exit 1
fi
