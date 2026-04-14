#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MC_DIR="$(dirname "${BASH_SOURCE[0]}")/monte-carlo-backtester"

if [ ! -d "$MC_DIR" ]; then
    echo "Error: Monte Carlo backtester not found. Run setup.sh first."
    exit 1
fi

echo "Running Monte Carlo backtester..."
cd "$MC_DIR"
prosperity4mcbt "$REPO_DIR/trader.py" --quick --out /tmp/prosperity4-mc-dashboard.json

echo ""
echo "Dashboard output: /tmp/prosperity4-mc-dashboard.json"
