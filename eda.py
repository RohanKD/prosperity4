"""EDA: Find mathematical patterns between EMERALDS and TOMATOES."""

import json
import csv
import io
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import defaultdict


def load_data(path):
    with open(path) as f:
        data = json.load(f)
    reader = csv.DictReader(io.StringIO(data["activitiesLog"]), delimiter=";")

    products = defaultdict(lambda: {"ts": [], "mid": [], "pnl": [],
                                     "bid1": [], "ask1": [], "spread": [],
                                     "bid_vol1": [], "ask_vol1": []})
    for row in reader:
        ts = int(row["timestamp"])
        product = row["product"]
        mid = float(row["mid_price"])
        pnl = float(row["profit_and_loss"])
        bid1 = float(row["bid_price_1"]) if row["bid_price_1"] else None
        ask1 = float(row["ask_price_1"]) if row["ask_price_1"] else None

        p = products[product]
        p["ts"].append(ts)
        p["mid"].append(mid)
        p["pnl"].append(pnl)
        p["bid1"].append(bid1)
        p["ask1"].append(ask1)
        p["spread"].append((ask1 - bid1) if (bid1 and ask1) else None)
        p["bid_vol1"].append(int(row["bid_volume_1"]) if row["bid_volume_1"] else 0)
        p["ask_vol1"].append(int(row["ask_volume_1"]) if row["ask_volume_1"] else 0)

    return products


def align_series(products):
    """Align EMERALDS and TOMATOES by timestamp."""
    e_data = {t: m for t, m in zip(products["EMERALDS"]["ts"], products["EMERALDS"]["mid"])}
    t_data = {t: m for t, m in zip(products["TOMATOES"]["ts"], products["TOMATOES"]["mid"])}

    common_ts = sorted(set(e_data.keys()) & set(t_data.keys()))
    e_mids = np.array([e_data[t] for t in common_ts])
    t_mids = np.array([t_data[t] for t in common_ts])
    ts = np.array(common_ts)
    return ts, e_mids, t_mids


def run_eda(path, output_path="logs/eda.png"):
    products = load_data(path)
    ts, e_mids, t_mids = align_series(products)

    # Returns
    e_returns = np.diff(e_mids) / e_mids[:-1]
    t_returns = np.diff(t_mids) / t_mids[:-1]

    # Price changes (absolute)
    e_diffs = np.diff(e_mids)
    t_diffs = np.diff(t_mids)

    fig = plt.figure(figsize=(22, 24))
    fig.suptitle("EDA: EMERALDS vs TOMATOES Relationships", fontsize=16, fontweight="bold")
    gs = gridspec.GridSpec(6, 2, hspace=0.4, wspace=0.3)

    # ── 1. Normalized price overlay ──
    ax = fig.add_subplot(gs[0, :])
    e_norm = (e_mids - e_mids[0]) / e_mids[0] * 100
    t_norm = (t_mids - t_mids[0]) / t_mids[0] * 100
    ax.plot(ts, e_norm, label="EMERALDS (norm %)", color="#00ff88", linewidth=0.8)
    ax.plot(ts, t_norm, label="TOMATOES (norm %)", color="#ff6644", linewidth=0.8)
    ax.set_title("Normalized Price Changes (%)")
    ax.legend()
    ax.grid(alpha=0.3)

    # ── 2. Return correlation (scatter) ──
    ax = fig.add_subplot(gs[1, 0])
    ax.scatter(e_returns, t_returns, alpha=0.1, s=1, color="cyan")
    corr = np.corrcoef(e_returns, t_returns)[0, 1]
    ax.set_title(f"Return Correlation: {corr:.4f}")
    ax.set_xlabel("EMERALDS return")
    ax.set_ylabel("TOMATOES return")
    ax.grid(alpha=0.3)

    # ── 3. Rolling correlation ──
    ax = fig.add_subplot(gs[1, 1])
    window = 200
    rolling_corr = []
    for i in range(window, len(e_returns)):
        c = np.corrcoef(e_returns[i-window:i], t_returns[i-window:i])[0, 1]
        rolling_corr.append(c)
    ax.plot(ts[window+1:], rolling_corr, color="cyan", linewidth=0.8)
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax.set_title(f"Rolling {window}-tick Return Correlation")
    ax.set_ylabel("Correlation")
    ax.grid(alpha=0.3)

    # ── 4. Lead-lag analysis ──
    ax = fig.add_subplot(gs[2, 0])
    max_lag = 20
    lags = range(-max_lag, max_lag + 1)
    cross_corr = []
    for lag in lags:
        if lag >= 0:
            c = np.corrcoef(e_returns[:len(e_returns)-lag], t_returns[lag:])[0, 1]
        else:
            c = np.corrcoef(e_returns[-lag:], t_returns[:len(t_returns)+lag])[0, 1]
        cross_corr.append(c)
    ax.bar(lags, cross_corr, color="cyan", alpha=0.7)
    ax.set_title("Lead-Lag Cross-Correlation (EMERALDS leads at +lag)")
    ax.set_xlabel("Lag (ticks)")
    ax.set_ylabel("Correlation")
    ax.grid(alpha=0.3)
    best_lag = lags[np.argmax(np.abs(cross_corr))]
    ax.axvline(x=best_lag, color="red", linestyle="--", alpha=0.7,
               label=f"Best lag: {best_lag}")
    ax.legend()

    # ── 5. Price ratio / spread analysis ──
    ax = fig.add_subplot(gs[2, 1])
    ratio = t_mids / e_mids
    ratio_mean = np.mean(ratio)
    ratio_std = np.std(ratio)
    ax.plot(ts, ratio, color="#ff6644", linewidth=0.8)
    ax.axhline(y=ratio_mean, color="white", linestyle="-", alpha=0.5,
               label=f"Mean: {ratio_mean:.6f}")
    ax.axhline(y=ratio_mean + 2*ratio_std, color="red", linestyle="--", alpha=0.5,
               label=f"+2σ: {ratio_mean + 2*ratio_std:.6f}")
    ax.axhline(y=ratio_mean - 2*ratio_std, color="green", linestyle="--", alpha=0.5,
               label=f"-2σ: {ratio_mean - 2*ratio_std:.6f}")
    ax.set_title("TOMATOES/EMERALDS Price Ratio")
    ax.set_ylabel("Ratio")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # ── 6. Z-score of the ratio (mean reversion signal) ──
    ax = fig.add_subplot(gs[3, 0])
    roll_window = 100
    ratio_series = ratio
    z_scores = []
    z_ts = []
    for i in range(roll_window, len(ratio_series)):
        window_data = ratio_series[i-roll_window:i]
        z = (ratio_series[i] - np.mean(window_data)) / max(np.std(window_data), 1e-10)
        z_scores.append(z)
        z_ts.append(ts[i])
    ax.plot(z_ts, z_scores, color="cyan", linewidth=0.8)
    ax.axhline(y=2, color="red", linestyle="--", alpha=0.5)
    ax.axhline(y=-2, color="green", linestyle="--", alpha=0.5)
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.3)
    ax.set_title("Z-Score of TOMATOES/EMERALDS Ratio (100-tick rolling)")
    ax.set_ylabel("Z-Score")
    ax.grid(alpha=0.3)

    # ── 7. TOMATOES autocorrelation (mean-reversion test) ──
    ax = fig.add_subplot(gs[3, 1])
    max_ac_lag = 30
    autocorrs = []
    for lag in range(1, max_ac_lag + 1):
        ac = np.corrcoef(t_returns[:-lag], t_returns[lag:])[0, 1]
        autocorrs.append(ac)
    ax.bar(range(1, max_ac_lag + 1), autocorrs, color="#ff6644", alpha=0.7)
    ax.set_title("TOMATOES Return Autocorrelation")
    ax.set_xlabel("Lag")
    ax.set_ylabel("Autocorrelation")
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax.grid(alpha=0.3)

    # ── 8. TOMATOES momentum persistence ──
    ax = fig.add_subplot(gs[4, 0])
    # Check if past N-tick return predicts next N-tick return
    for lookback in [5, 10, 20, 50]:
        past_ret = []
        future_ret = []
        for i in range(lookback, len(t_mids) - lookback):
            past = (t_mids[i] - t_mids[i - lookback]) / t_mids[i - lookback]
            future = (t_mids[i + lookback] - t_mids[i]) / t_mids[i]
            past_ret.append(past)
            future_ret.append(future)
        c = np.corrcoef(past_ret, future_ret)[0, 1]
        ax.bar(lookback, c, width=3, alpha=0.7, label=f"lb={lookback}: {c:.4f}")
    ax.set_title("Momentum Persistence: corr(past_ret, future_ret)")
    ax.set_xlabel("Lookback (ticks)")
    ax.set_ylabel("Correlation")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # ── 9. Spread regime analysis ──
    ax = fig.add_subplot(gs[4, 1])
    t_spreads = [s for s in products["TOMATOES"]["spread"] if s is not None]
    t_spread_ts = [t for t, s in zip(products["TOMATOES"]["ts"], products["TOMATOES"]["spread"]) if s is not None]

    # Spread vs future return
    future_abs_ret = []
    spread_vals = []
    t_mid_dict = {t: m for t, m in zip(products["TOMATOES"]["ts"], products["TOMATOES"]["mid"])}
    t_spread_dict = {t: s for t, s in zip(t_spread_ts, t_spreads)}
    for i, t in enumerate(t_spread_ts[:-10]):
        if t + 1000 in t_mid_dict and t in t_mid_dict:
            future = abs(t_mid_dict[t + 1000] - t_mid_dict[t])
            spread_vals.append(t_spread_dict[t])
            future_abs_ret.append(future)
    if spread_vals:
        ax.scatter(spread_vals, future_abs_ret, alpha=0.05, s=1, color="#ff6644")
        c = np.corrcoef(spread_vals, future_abs_ret)[0, 1]
        ax.set_title(f"Spread vs Future |Move| (10-tick): corr={c:.4f}")
    ax.set_xlabel("Current Spread")
    ax.set_ylabel("Future |Price Move|")
    ax.grid(alpha=0.3)

    # ── 10. Order book imbalance signal ──
    ax = fig.add_subplot(gs[5, 0])
    t_bids = products["TOMATOES"]["bid_vol1"]
    t_asks = products["TOMATOES"]["ask_vol1"]
    imbalance = [(b - a) / max(b + a, 1) for b, a in zip(t_bids, t_asks)]
    # Rolling imbalance
    window = 20
    roll_imb = np.convolve(imbalance, np.ones(window)/window, mode="valid")
    ax.plot(products["TOMATOES"]["ts"][window-1:], roll_imb,
            color="#ff6644", linewidth=0.8)
    ax.set_title("TOMATOES Order Book Imbalance (20-tick avg)")
    ax.set_ylabel("(Bid Vol - Ask Vol) / (Bid + Ask)")
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax.grid(alpha=0.3)

    # ── 11. Imbalance vs future return ──
    ax = fig.add_subplot(gs[5, 1])
    t_mid_arr = np.array(products["TOMATOES"]["mid"])
    imb_arr = np.array(imbalance)
    future_rets_5 = []
    imb_vals = []
    for i in range(len(imb_arr) - 5):
        future_rets_5.append(t_mid_arr[i+5] - t_mid_arr[i])
        imb_vals.append(imb_arr[i])
    if imb_vals:
        ax.scatter(imb_vals, future_rets_5, alpha=0.05, s=1, color="cyan")
        c = np.corrcoef(imb_vals, future_rets_5)[0, 1]
        ax.set_title(f"Imbalance vs Future Move (5-tick): corr={c:.4f}")
    ax.set_xlabel("Order Book Imbalance")
    ax.set_ylabel("Future Price Move")
    ax.grid(alpha=0.3)

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved EDA to {output_path}")

    # ── Print key findings ──
    print("\n=== KEY FINDINGS ===")
    print(f"\n1. Return Correlation (EMERALDS vs TOMATOES): {corr:.4f}")
    print(f"   Best lead-lag: lag={best_lag}, corr={cross_corr[best_lag + max_lag]:.4f}")

    print(f"\n2. TOMATOES/EMERALDS Ratio:")
    print(f"   Mean: {ratio_mean:.6f}, Std: {ratio_std:.6f}")
    print(f"   Range: {ratio.min():.6f} to {ratio.max():.6f}")

    print(f"\n3. TOMATOES Autocorrelation (lag-1): {autocorrs[0]:.4f}")
    mean_rev = "MEAN-REVERTING" if autocorrs[0] < -0.05 else "TRENDING" if autocorrs[0] > 0.05 else "RANDOM"
    print(f"   Regime: {mean_rev}")

    print(f"\n4. Momentum Persistence:")
    for lookback in [5, 10, 20, 50]:
        past_ret = []
        future_ret = []
        for i in range(lookback, len(t_mids) - lookback):
            past = (t_mids[i] - t_mids[i - lookback]) / t_mids[i - lookback]
            future = (t_mids[i + lookback] - t_mids[i]) / t_mids[i]
            past_ret.append(past)
            future_ret.append(future)
        c = np.corrcoef(past_ret, future_ret)[0, 1]
        print(f"   {lookback}-tick: {c:.4f} ({'momentum' if c > 0 else 'reversion'})")

    if imb_vals:
        imb_corr = np.corrcoef(imb_vals, future_rets_5)[0, 1]
        print(f"\n5. Order Book Imbalance -> Future Move: {imb_corr:.4f}")
        print(f"   {'PREDICTIVE' if abs(imb_corr) > 0.03 else 'WEAK'}")


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/98988/98988.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "logs/eda.png"
    run_eda(path, out)
