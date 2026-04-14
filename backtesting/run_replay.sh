#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROUND="${1:-0}"

echo "Running prosperity4btx replay backtester (round $ROUND)..."
cd "$REPO_DIR"
prosperity4btx trader.py "$ROUND"
