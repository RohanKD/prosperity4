#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Installing prosperity4btx (replay backtester) ==="
pip install -U prosperity4btx

echo ""
echo "=== Installing jsonpickle ==="
pip install -U jsonpickle

echo ""
echo "=== Cloning kevin-fu1 backtester ==="
if [ ! -d "$SCRIPT_DIR/kevin-fu1-backtester" ]; then
    git clone https://github.com/kevin-fu1/imc-prosperity-4-backtester.git "$SCRIPT_DIR/kevin-fu1-backtester"
else
    echo "Already cloned, pulling latest..."
    git -C "$SCRIPT_DIR/kevin-fu1-backtester" pull
fi

echo ""
echo "=== Cloning chrispyroberts Monte Carlo backtester ==="
if [ ! -d "$SCRIPT_DIR/monte-carlo-backtester" ]; then
    git clone https://github.com/chrispyroberts/imc-prosperity-4.git "$SCRIPT_DIR/monte-carlo-backtester"
else
    echo "Already cloned, pulling latest..."
    git -C "$SCRIPT_DIR/monte-carlo-backtester" pull
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Available backtesters:"
echo "  1. prosperity4btx        -> run: prosperity4btx trader.py 0"
echo "  2. kevin-fu1 backtester  -> run: cd backtesting/kevin-fu1-backtester && python -m prosperity4bt ../../trader.py 0"
echo "  3. Monte Carlo backtester -> see backtesting/monte-carlo-backtester/README.md for setup (requires Rust + Node)"
echo ""
echo "Visualizer (browser): https://jmerle.github.io/imc-prosperity-3-visualizer/"
