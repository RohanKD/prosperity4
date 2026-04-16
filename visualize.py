"""Visualize IMC Prosperity 4 trading logs.

Supports both:
  - Prosperity submission logs (JSON with activitiesLog field)
  - prosperity4btx backtester logs (text with 'Activities log:' section)

Usage:
  python visualize.py <log1> [<log2>] [--out <output.png>]
  python visualize.py backtests/98988.log backtests/98687.log --out logs/compare.png
"""

import csv
import io
import sys
import os
import json
import argparse
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from collections import defaultdict


# ── Parsers ──────────────────────────────────────────────────────────────────

def load_log(path):
    """Load a log file and return (activities_csv_str, total_profit)."""
    with open(path) as f:
        raw = f.read()

    # Backtester text format: has 'Activities log:' section header
    if "Activities log:" in raw:
        return _parse_backtester(raw)

    # Prosperity submission JSON format
    try:
        data = json.loads(raw)
        return data["activitiesLog"], data.get("profit", 0)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Unrecognised log format: {path}")


def _parse_backtester(raw):
    """Parse prosperity4btx text log into (csv_str, total_profit)."""
    act_start = raw.index("Activities log:\n") + len("Activities log:\n")

    # Section ends at 'Trade History:' or end of file
    for marker in ["Trade History:", "\nSandbox logs:"]:
        if marker in raw[act_start:]:
            act_end = raw.index(marker, act_start)
            break
    else:
        act_end = len(raw)

    csv_str = raw[act_start:act_end].strip()

    # Compute profit from CSV: sum of final PnL per (day, product)
    profit = _compute_profit_from_csv(csv_str)

    return csv_str, profit


def _compute_profit_from_csv(csv_str):
    """Sum the last profit_and_loss value per (day, product) across all days."""
    reader = csv.DictReader(io.StringIO(csv_str), delimiter=";")
    last_pnl = {}
    for row in reader:
        key = (row["day"], row["product"])
        try:
            last_pnl[key] = float(row["profit_and_loss"])
        except (ValueError, KeyError):
            pass
    return sum(last_pnl.values())


def parse_activities(csv_str):
    """Parse CSV into per-product time series dict."""
    reader = csv.DictReader(io.StringIO(csv_str), delimiter=";")
    products = defaultdict(lambda: {
        "timestamps": [], "mid_prices": [], "pnl": [],
        "bid1": [], "ask1": [], "spread": [],
        "bid_vol1": [], "ask_vol1": [],
    })
    for row in reader:
        ts = int(row["timestamp"])
        product = row["product"]
        mid = float(row["mid_price"])
        pnl = float(row["profit_and_loss"])
        bid1 = float(row["bid_price_1"]) if row.get("bid_price_1") else None
        ask1 = float(row["ask_price_1"]) if row.get("ask_price_1") else None
        bid_vol1 = int(row["bid_volume_1"]) if row.get("bid_volume_1") else 0
        ask_vol1 = int(row["ask_volume_1"]) if row.get("ask_volume_1") else 0

        p = products[product]
        p["timestamps"].append(ts)
        p["mid_prices"].append(mid)
        p["pnl"].append(pnl)
        p["bid1"].append(bid1)
        p["ask1"].append(ask1)
        p["spread"].append((ask1 - bid1) if (bid1 and ask1) else None)
        p["bid_vol1"].append(bid_vol1)
        p["ask_vol1"].append(ask_vol1)

    return products


def total_pnl_curve(products):
    """Sum per-product PnL into a single total curve, aligned by timestamp."""
    all_ts = sorted({ts for p in products.values() for ts in p["timestamps"]})
    # Last known PnL per product at each ts
    last = {prod: 0.0 for prod in products}
    pnl_idx = {prod: 0 for prod in products}
    totals = []
    for ts in all_ts:
        for prod, pdata in products.items():
            while pnl_idx[prod] < len(pdata["timestamps"]) and pdata["timestamps"][pnl_idx[prod]] <= ts:
                last[prod] = pdata["pnl"][pnl_idx[prod]]
                pnl_idx[prod] += 1
        totals.append(sum(last.values()))
    return all_ts, totals


# ── Plot helpers ──────────────────────────────────────────────────────────────

COLORS = {"EMERALDS": "#00ff88", "TOMATOES": "#ff6644"}
STYLE = {"axes.facecolor": "#1a1a2e", "figure.facecolor": "#0d0d1a",
         "axes.edgecolor": "#444", "axes.labelcolor": "#ccc",
         "xtick.color": "#888", "ytick.color": "#888",
         "grid.color": "#333", "text.color": "#ddd",
         "legend.facecolor": "#111", "legend.edgecolor": "#444"}

def rolling(arr, w):
    if len(arr) < w:
        return arr
    return np.convolve(arr, np.ones(w) / w, mode="valid")


def plot_single(ax_pnl, ax_prod, ax_spread, products, label, profit):
    """Fill a row of axes for one backtest run."""
    ts_total, pnl_total = total_pnl_curve(products)

    # Total PnL
    ax_pnl.plot(ts_total, pnl_total, color="#00d4ff", linewidth=1)
    ax_pnl.fill_between(ts_total, pnl_total, 0,
                         where=[p >= 0 for p in pnl_total], color="#00d4ff", alpha=0.12)
    ax_pnl.fill_between(ts_total, pnl_total, 0,
                         where=[p < 0 for p in pnl_total], color="#ff4444", alpha=0.12)
    ax_pnl.set_title(f"{label}  |  Total PnL: {profit:,.0f}", fontsize=10)
    ax_pnl.set_ylabel("PnL")
    ax_pnl.grid(alpha=0.3)

    # Per-product PnL
    for prod, pdata in products.items():
        ax_prod.plot(pdata["timestamps"], pdata["pnl"],
                     label=prod, color=COLORS.get(prod, "#fff"), linewidth=0.8)
    ax_prod.set_title("PnL by Product", fontsize=9)
    ax_prod.set_ylabel("PnL")
    ax_prod.legend(fontsize=7)
    ax_prod.grid(alpha=0.3)

    # Spread
    for prod, pdata in products.items():
        valid_ts = [t for t, s in zip(pdata["timestamps"], pdata["spread"]) if s is not None]
        valid_sp = [s for s in pdata["spread"] if s is not None]
        w = 50
        if len(valid_sp) > w:
            ax_spread.plot(valid_ts[w - 1:], rolling(valid_sp, w),
                           label=prod, color=COLORS.get(prod, "#fff"), linewidth=0.8)
        else:
            ax_spread.plot(valid_ts, valid_sp,
                           label=prod, color=COLORS.get(prod, "#fff"), linewidth=0.8)
    ax_spread.set_title("Spread (50-tick avg)", fontsize=9)
    ax_spread.set_ylabel("Spread")
    ax_spread.legend(fontsize=7)
    ax_spread.grid(alpha=0.3)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", help="Log file paths (1 or 2)")
    parser.add_argument("--out", default="logs/compare.png", help="Output image path")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    loaded = []
    for path in args.logs[:2]:
        csv_str, profit = load_log(path)
        products = parse_activities(csv_str)
        label = os.path.basename(path).replace(".log", "")
        loaded.append((label, products, profit))

    with plt.style.context(STYLE):
        if len(loaded) == 1:
            label, products, profit = loaded[0]
            fig = plt.figure(figsize=(18, 10))
            fig.suptitle(f"Prosperity 4 — {label}", fontsize=14, fontweight="bold", color="#eee")
            gs = gridspec.GridSpec(1, 3, hspace=0.35, wspace=0.3)
            plot_single(fig.add_subplot(gs[0, 0]),
                        fig.add_subplot(gs[0, 1]),
                        fig.add_subplot(gs[0, 2]),
                        products, label, profit)
        else:
            fig = plt.figure(figsize=(22, 12))
            fig.suptitle("Prosperity 4 — Side-by-Side Comparison", fontsize=14,
                         fontweight="bold", color="#eee")
            gs = gridspec.GridSpec(2, 3, hspace=0.42, wspace=0.3)

            # Diff row at the bottom
            for row, (label, products, profit) in enumerate(loaded):
                plot_single(fig.add_subplot(gs[row, 0]),
                            fig.add_subplot(gs[row, 1]),
                            fig.add_subplot(gs[row, 2]),
                            products, label, profit)

            # Add a difference annotation
            if len(loaded) == 2:
                p0 = loaded[0][2]
                p1 = loaded[1][2]
                diff = p1 - p0
                sign = "+" if diff >= 0 else ""
                fig.text(0.5, 0.01,
                         f"{loaded[1][0]} vs {loaded[0][0]}: {sign}{diff:,.0f} seashells",
                         ha="center", fontsize=12, color="#00d4ff" if diff >= 0 else "#ff4444",
                         fontweight="bold")

    plt.savefig(args.out, dpi=150, bbox_inches="tight",
                facecolor=STYLE["figure.facecolor"])
    plt.close()
    print(f"Saved to {args.out}")

    # Print summary
    for label, products, profit in loaded:
        print(f"\n-- {label}  (total: {profit:,.0f}) --")
        for prod, pdata in products.items():
            final = pdata["pnl"][-1] if pdata["pnl"] else 0
            spreads = [s for s in pdata["spread"] if s is not None]
            avg_sp = np.mean(spreads) if spreads else 0
            print(f"  {prod}: final PnL={final:,.1f}  avg spread={avg_sp:.2f}")


if __name__ == "__main__":
    main()
