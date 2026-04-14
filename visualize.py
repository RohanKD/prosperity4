"""Visualize IMC Prosperity 4 trading logs."""

import json
import csv
import io
import sys
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from collections import defaultdict

def load_json_log(path):
    with open(path) as f:
        return json.load(f)

def parse_activities(data):
    """Parse the activitiesLog CSV into structured data per product."""
    reader = csv.DictReader(io.StringIO(data["activitiesLog"]), delimiter=";")
    products = defaultdict(lambda: {"timestamps": [], "mid_prices": [], "pnl": [],
                                     "bid1": [], "ask1": [], "spread": [],
                                     "bid_vol1": [], "ask_vol1": []})
    for row in reader:
        ts = int(row["timestamp"])
        product = row["product"]
        mid = float(row["mid_price"])
        pnl = float(row["profit_and_loss"])
        bid1 = float(row["bid_price_1"]) if row["bid_price_1"] else None
        ask1 = float(row["ask_price_1"]) if row["ask_price_1"] else None
        bid_vol1 = int(row["bid_volume_1"]) if row["bid_volume_1"] else 0
        ask_vol1 = int(row["ask_volume_1"]) if row["ask_volume_1"] else 0

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

def parse_graph_log(data):
    """Parse the graphLog (total PnL over time)."""
    timestamps, values = [], []
    for line in data["graphLog"].strip().split("\n"):
        if line.startswith("timestamp"):
            continue
        parts = line.split(";")
        timestamps.append(int(parts[0]))
        values.append(float(parts[1]))
    return timestamps, values

def estimate_positions(products):
    """Estimate positions from PnL changes and mid price movements.

    Since the JSON only has final positions, we infer position from
    the relationship: dPnL ≈ position * dMidPrice (mark-to-market).
    We back out approximate position from consecutive PnL/price ticks.
    """
    positions = {}
    for product, pdata in products.items():
        ts = pdata["timestamps"]
        mids = pdata["mid_prices"]
        pnls = pdata["pnl"]
        pos_list = [0]
        for i in range(1, len(mids)):
            dp = mids[i] - mids[i - 1]
            dpnl = pnls[i] - pnls[i - 1]
            if abs(dp) > 0.01:
                est_pos = dpnl / dp
                # Smooth: blend with previous estimate
                prev = pos_list[-1]
                pos_list.append(0.3 * est_pos + 0.7 * prev)
            else:
                pos_list.append(pos_list[-1])
        positions[product] = {"timestamps": ts, "positions": pos_list}
    return positions

def plot_all(json_path, output_path="logs/analysis.png"):
    data = load_json_log(json_path)
    products = parse_activities(data)
    graph_ts, graph_pnl = parse_graph_log(data)
    positions = estimate_positions(products)

    fig = plt.figure(figsize=(20, 16))
    fig.suptitle(f"Prosperity 4 Analysis — Total PnL: {data['profit']:.1f}", fontsize=16, fontweight="bold")
    gs = gridspec.GridSpec(4, 2, hspace=0.35, wspace=0.3)

    # 1. Total PnL curve
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(graph_ts, graph_pnl, color="#00d4ff", linewidth=1)
    ax1.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax1.fill_between(graph_ts, graph_pnl, 0,
                     where=[p >= 0 for p in graph_pnl], color="#00d4ff", alpha=0.15)
    ax1.fill_between(graph_ts, graph_pnl, 0,
                     where=[p < 0 for p in graph_pnl], color="#ff4444", alpha=0.15)
    ax1.set_title("Total PnL Over Time")
    ax1.set_xlabel("Timestamp")
    ax1.set_ylabel("PnL")
    ax1.grid(alpha=0.3)

    # 2. Per-product PnL
    ax2 = fig.add_subplot(gs[1, 0])
    colors = {"EMERALDS": "#00ff88", "TOMATOES": "#ff6644"}
    for product, pdata in products.items():
        ax2.plot(pdata["timestamps"], pdata["pnl"], label=product,
                 color=colors.get(product, "white"), linewidth=0.8)
    ax2.set_title("PnL by Product")
    ax2.set_xlabel("Timestamp")
    ax2.set_ylabel("PnL")
    ax2.legend()
    ax2.grid(alpha=0.3)

    # 3. Mid prices
    ax3 = fig.add_subplot(gs[1, 1])
    for product, pdata in products.items():
        ax3.plot(pdata["timestamps"], pdata["mid_prices"], label=product,
                 color=colors.get(product, "white"), linewidth=0.8)
    ax3.set_title("Mid Prices")
    ax3.set_xlabel("Timestamp")
    ax3.set_ylabel("Price")
    ax3.legend()
    ax3.grid(alpha=0.3)

    # 4. Positions
    ax4 = fig.add_subplot(gs[2, 0])
    for product, posdata in positions.items():
        ax4.plot(posdata["timestamps"], posdata["positions"], label=product,
                 color=colors.get(product, "white"), linewidth=0.8)
    ax4.axhline(y=80, color="red", linestyle="--", alpha=0.5, label="Limit +80")
    ax4.axhline(y=-80, color="red", linestyle="--", alpha=0.5, label="Limit -80")
    ax4.set_title("Position Over Time")
    ax4.set_xlabel("Timestamp")
    ax4.set_ylabel("Position")
    ax4.legend(fontsize=8)
    ax4.grid(alpha=0.3)

    # 5. Spread over time
    ax5 = fig.add_subplot(gs[2, 1])
    for product, pdata in products.items():
        spreads = [s for s in pdata["spread"] if s is not None]
        ts = [t for t, s in zip(pdata["timestamps"], pdata["spread"]) if s is not None]
        # Rolling average for readability
        window = 50
        if len(spreads) > window:
            rolling = np.convolve(spreads, np.ones(window)/window, mode="valid")
            ax5.plot(ts[window-1:], rolling, label=product,
                     color=colors.get(product, "white"), linewidth=0.8)
        else:
            ax5.plot(ts, spreads, label=product,
                     color=colors.get(product, "white"), linewidth=0.8)
    ax5.set_title("Spread (50-tick rolling avg)")
    ax5.set_xlabel("Timestamp")
    ax5.set_ylabel("Spread")
    ax5.legend()
    ax5.grid(alpha=0.3)

    # 6. Volume at best bid/ask
    ax6 = fig.add_subplot(gs[3, 0])
    for product, pdata in products.items():
        window = 50
        if len(pdata["bid_vol1"]) > window:
            rolling_bid = np.convolve(pdata["bid_vol1"], np.ones(window)/window, mode="valid")
            rolling_ask = np.convolve(pdata["ask_vol1"], np.ones(window)/window, mode="valid")
            ts_r = pdata["timestamps"][window-1:]
            ax6.plot(ts_r, rolling_bid, label=f"{product} bid vol",
                     color=colors.get(product, "white"), linewidth=0.8)
            ax6.plot(ts_r, rolling_ask, label=f"{product} ask vol",
                     color=colors.get(product, "white"), linewidth=0.8, linestyle="--")
    ax6.set_title("Best Bid/Ask Volume (50-tick rolling avg)")
    ax6.set_xlabel("Timestamp")
    ax6.set_ylabel("Volume")
    ax6.legend(fontsize=7)
    ax6.grid(alpha=0.3)

    # 7. PnL distribution histogram (per-tick changes)
    ax7 = fig.add_subplot(gs[3, 1])
    for product, pdata in products.items():
        pnl_changes = np.diff(pdata["pnl"])
        ax7.hist(pnl_changes, bins=100, alpha=0.5, label=product,
                 color=colors.get(product, "white"))
    ax7.set_title("Per-Tick PnL Change Distribution")
    ax7.set_xlabel("PnL Change")
    ax7.set_ylabel("Count")
    ax7.legend()
    ax7.grid(alpha=0.3)

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved analysis to {output_path}")

    # Print summary stats
    print("\n=== Summary ===")
    print(f"Total PnL: {data['profit']:.2f}")
    for product, pdata in products.items():
        final_pnl = pdata["pnl"][-1] if pdata["pnl"] else 0
        min_pnl = min(pdata["pnl"]) if pdata["pnl"] else 0
        max_pnl = max(pdata["pnl"]) if pdata["pnl"] else 0
        spreads = [s for s in pdata["spread"] if s is not None]
        avg_spread = np.mean(spreads) if spreads else 0
        print(f"\n{product}:")
        print(f"  Final PnL: {final_pnl:.2f}")
        print(f"  Min PnL: {min_pnl:.2f}  Max PnL: {max_pnl:.2f}")
        print(f"  Avg Spread: {avg_spread:.2f}")

    for product, posdata in positions.items():
        pos = posdata["positions"]
        print(f"\n{product} estimated position:")
        print(f"  Min: {min(pos):.0f}  Max: {max(pos):.0f}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/98540.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "logs/analysis.png"
    plot_all(path, out)
