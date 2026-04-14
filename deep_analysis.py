#!/usr/bin/env python3
"""
Deep analysis of IMC Prosperity 4 trading log, focusing on TOMATOES drawdown
and cross-product risk/reward comparison.
"""

import json
import numpy as np
from collections import defaultdict

LOG_PATH = "/Users/rohan/prosperity4/logs/100091/100091.json"

def parse_activities(csv_text):
    """Parse the activitiesLog CSV (semicolon-delimited) into a list of dicts."""
    lines = csv_text.strip().split("\n")
    header = lines[0].split(";")
    records = []
    for line in lines[1:]:
        parts = line.split(";")
        if len(parts) < len(header):
            continue
        row = {}
        for i, col in enumerate(header):
            val = parts[i].strip() if i < len(parts) else ""
            row[col] = val
        records.append(row)
    return records


def to_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def main():
    print("=" * 80)
    print("DEEP ANALYSIS OF TRADING LOG 100091")
    print("=" * 80)

    with open(LOG_PATH) as f:
        data = json.load(f)

    print(f"\nOverall profit: {data.get('profit')}")
    print(f"Final positions: {data.get('positions')}")

    records = parse_activities(data["activitiesLog"])
    print(f"Total activity rows: {len(records)}")

    # Separate by product
    by_product = defaultdict(list)
    for r in records:
        by_product[r["product"]].append(r)

    products = sorted(by_product.keys())
    print(f"Products: {products}")

    # =========================================================================
    # HELPER: extract numeric fields for a product's records
    # =========================================================================
    def extract_series(recs):
        """Return arrays of timestamp, mid_price, pnl, bid/ask vols, spread."""
        ts = []
        mid = []
        pnl = []
        obi = []
        spread = []
        for r in recs:
            t = to_float(r.get("timestamp", 0))
            m = to_float(r.get("mid_price", 0))
            p = to_float(r.get("profit_and_loss", 0))

            bid_vol = 0.0
            ask_vol = 0.0
            best_bid = None
            best_ask = None
            for lvl in range(1, 4):
                bv = to_float(r.get(f"bid_volume_{lvl}", 0))
                av = to_float(r.get(f"ask_volume_{lvl}", 0))
                bid_vol += abs(bv)
                ask_vol += abs(av)
                if lvl == 1:
                    best_bid = to_float(r.get(f"bid_price_{lvl}", 0))
                    best_ask = to_float(r.get(f"ask_price_{lvl}", 0))

            total_vol = bid_vol + ask_vol
            obi_val = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0.0
            sp = best_ask - best_bid if (best_ask and best_bid) else 0.0

            ts.append(t)
            mid.append(m)
            pnl.append(p)
            obi.append(obi_val)
            spread.append(sp)

        return (np.array(ts), np.array(mid), np.array(pnl),
                np.array(obi), np.array(spread))

    # =========================================================================
    # 1. TOMATOES ANALYSIS
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 1: TOMATOES — FULL TIMELINE STATISTICS")
    print("=" * 80)

    tom_recs = by_product.get("TOMATOES", [])
    if not tom_recs:
        # Try other name variants
        for k in by_product:
            if "TOMATO" in k.upper():
                tom_recs = by_product[k]
                print(f"  (Using product key: {k})")
                break
    if not tom_recs:
        print("  WARNING: No TOMATOES data found! Available products:", products)
    else:
        ts, mid, pnl, obi, spread = extract_series(tom_recs)
        print(f"  Total ticks: {len(ts)}")
        print(f"  Timestamp range: {ts.min():.0f} — {ts.max():.0f}")
        print(f"  Mid-price: min={mid.min():.2f}, max={mid.max():.2f}, "
              f"range={mid.max()-mid.min():.2f}, std={mid.std():.4f}, mean={mid.mean():.2f}")
        print(f"  Final PnL: {pnl[-1]:.2f}")
        print(f"  Peak PnL: {pnl.max():.2f} at t={ts[np.argmax(pnl)]:.0f}")
        print(f"  Trough PnL: {pnl.min():.2f} at t={ts[np.argmin(pnl)]:.0f}")
        print(f"  Max drawdown from peak: {pnl.max() - pnl.min():.2f}")

        # Tick-by-tick PnL changes
        dpnl = np.diff(pnl)
        print(f"\n  Tick-by-tick PnL change distribution:")
        print(f"    mean={dpnl.mean():.4f}, std={dpnl.std():.4f}")
        print(f"    min={dpnl.min():.2f}, max={dpnl.max():.2f}")
        print(f"    median={np.median(dpnl):.4f}")
        pcts = [1, 5, 10, 25, 75, 90, 95, 99]
        for p in pcts:
            print(f"    {p}th percentile: {np.percentile(dpnl, p):.4f}")

        # Big outlier losses
        threshold_neg = np.percentile(dpnl, 1)
        big_losses = [(ts[i+1], dpnl[i]) for i in range(len(dpnl)) if dpnl[i] < threshold_neg]
        print(f"\n  Worst 1% tick losses (threshold < {threshold_neg:.2f}):")
        big_losses_sorted = sorted(big_losses, key=lambda x: x[1])[:10]
        for t_val, d in big_losses_sorted:
            print(f"    t={t_val:.0f}  dPnL={d:.2f}")

        # Second half PnL contribution
        half_mask = ts > 100000
        if half_mask.any():
            pnl_at_100k_idx = np.searchsorted(ts, 100000)
            pnl_at_100k = pnl[pnl_at_100k_idx] if pnl_at_100k_idx < len(pnl) else pnl[-1]
            pnl_second_half = pnl[-1] - pnl_at_100k
            print(f"\n  PnL at t=100000: {pnl_at_100k:.2f}")
            print(f"  PnL from second half (t>100000): {pnl_second_half:.2f}")
            print(f"  PnL from first half (t<=100000): {pnl_at_100k:.2f}")
        else:
            print("\n  No data beyond t=100000")

        # Sharpe-like ratio
        sharpe = dpnl.mean() / dpnl.std() if dpnl.std() > 0 else 0
        print(f"\n  Sharpe-like ratio (mean dPnL / std dPnL): {sharpe:.6f}")

        # =====================================================================
        # 2. DRAWDOWN WINDOW t=10000-50000
        # =====================================================================
        print("\n" + "=" * 80)
        print("SECTION 2: TOMATOES — DRAWDOWN WINDOW (t=10,000 — 50,000)")
        print("=" * 80)

        mask = (ts >= 10000) & (ts <= 50000)
        if mask.sum() == 0:
            print("  No data in this window!")
        else:
            dd_ts = ts[mask]
            dd_mid = mid[mask]
            dd_pnl = pnl[mask]
            dd_obi = obi[mask]
            dd_spread = spread[mask]

            print(f"  Ticks in window: {mask.sum()}")
            print(f"  PnL at start: {dd_pnl[0]:.2f}")
            print(f"  PnL at end: {dd_pnl[-1]:.2f}")
            print(f"  PnL change in window: {dd_pnl[-1] - dd_pnl[0]:.2f}")
            print(f"  PnL peak in window: {dd_pnl.max():.2f} at t={dd_ts[np.argmax(dd_pnl)]:.0f}")
            print(f"  PnL trough in window: {dd_pnl.min():.2f} at t={dd_ts[np.argmin(dd_pnl)]:.0f}")

            # Mid-price trajectory
            print(f"\n  Mid-price at start: {dd_mid[0]:.2f}")
            print(f"  Mid-price at end: {dd_mid[-1]:.2f}")
            print(f"  Mid-price min: {dd_mid.min():.2f} at t={dd_ts[np.argmin(dd_mid)]:.0f}")
            print(f"  Mid-price max: {dd_mid.max():.2f} at t={dd_ts[np.argmax(dd_mid)]:.0f}")
            print(f"  Mid-price total move: {dd_mid[-1] - dd_mid[0]:.2f}")
            print(f"  Mid-price std in window: {dd_mid.std():.4f}")

            # PnL drop speed — find steepest drop
            dd_dpnl = np.diff(dd_pnl)
            dd_dts = np.diff(dd_ts)
            print(f"\n  Steepest single-tick PnL drop: {dd_dpnl.min():.2f} "
                  f"at t={dd_ts[np.argmin(dd_dpnl)+1]:.0f}")

            # Rolling 10-tick PnL change
            if len(dd_pnl) >= 10:
                roll_10 = dd_pnl[10:] - dd_pnl[:-10]
                worst_10_idx = np.argmin(roll_10)
                print(f"  Worst 10-tick rolling PnL drop: {roll_10.min():.2f} "
                      f"(t={dd_ts[worst_10_idx]:.0f} to t={dd_ts[worst_10_idx+10]:.0f})")

            # Rolling 50-tick PnL change
            if len(dd_pnl) >= 50:
                roll_50 = dd_pnl[50:] - dd_pnl[:-50]
                worst_50_idx = np.argmin(roll_50)
                print(f"  Worst 50-tick rolling PnL drop: {roll_50.min():.2f} "
                      f"(t={dd_ts[worst_50_idx]:.0f} to t={dd_ts[worst_50_idx+50]:.0f})")

            # OBI analysis
            print(f"\n  OBI (Order Book Imbalance) stats in drawdown:")
            print(f"    mean={dd_obi.mean():.4f}, std={dd_obi.std():.4f}")
            print(f"    min={dd_obi.min():.4f}, max={dd_obi.max():.4f}")

            # Does OBI predict the drawdown?
            # Find the tick where PnL starts dropping significantly
            pnl_peak_idx = np.argmax(dd_pnl)
            pnl_trough_idx = np.argmin(dd_pnl)
            print(f"\n  PnL peak at index {pnl_peak_idx} (t={dd_ts[pnl_peak_idx]:.0f})")
            print(f"  PnL trough at index {pnl_trough_idx} (t={dd_ts[pnl_trough_idx]:.0f})")

            if pnl_peak_idx < pnl_trough_idx and pnl_peak_idx > 0:
                # OBI before peak
                lookback = min(20, pnl_peak_idx)
                obi_before = dd_obi[pnl_peak_idx - lookback:pnl_peak_idx]
                obi_during = dd_obi[pnl_peak_idx:pnl_trough_idx+1]
                print(f"  OBI in {lookback} ticks BEFORE peak: mean={obi_before.mean():.4f}")
                print(f"  OBI DURING drop (peak->trough): mean={obi_during.mean():.4f}")

                # Did OBI flip negative before price dropped?
                neg_obi_before = np.sum(obi_before < 0)
                print(f"  Negative OBI ticks before peak: {neg_obi_before}/{len(obi_before)}")
                if obi_during.size > 0:
                    neg_obi_during = np.sum(obi_during < 0)
                    print(f"  Negative OBI ticks during drop: {neg_obi_during}/{len(obi_during)}")
            else:
                print("  (Peak is not before trough or at start — unusual pattern)")

            # Print OBI timeline around key events (every ~5 ticks)
            print(f"\n  OBI + Mid + PnL timeline (sampled every 5 ticks):")
            print(f"  {'t':>8} {'mid':>10} {'PnL':>10} {'OBI':>8} {'spread':>8}")
            step = max(1, len(dd_ts) // 40)
            for i in range(0, len(dd_ts), step):
                print(f"  {dd_ts[i]:>8.0f} {dd_mid[i]:>10.2f} {dd_pnl[i]:>10.2f} "
                      f"{dd_obi[i]:>8.4f} {dd_spread[i]:>8.2f}")

            # Spread changes
            print(f"\n  Spread stats in drawdown:")
            print(f"    mean={dd_spread.mean():.4f}, std={dd_spread.std():.4f}")
            print(f"    min={dd_spread.min():.2f}, max={dd_spread.max():.2f}")

            # Correlation: OBI vs next-tick mid-price change
            if len(dd_mid) > 1:
                dmid = np.diff(dd_mid)
                corr_obi_mid = np.corrcoef(dd_obi[:-1], dmid)[0, 1]
                print(f"\n  Correlation(OBI, next-tick mid change): {corr_obi_mid:.4f}")
                corr_obi_dpnl = np.corrcoef(dd_obi[:-1], dd_dpnl)[0, 1]
                print(f"  Correlation(OBI, next-tick PnL change): {corr_obi_dpnl:.4f}")

    # =========================================================================
    # 3. WHAT IF WE DIDN'T TRADE TOMATOES?
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 3: COUNTERFACTUAL — WITHOUT TOMATOES")
    print("=" * 80)

    total_pnl_by_product = {}
    for prod in products:
        recs = by_product[prod]
        _, _, p, _, _ = extract_series(recs)
        if len(p) > 0:
            total_pnl_by_product[prod] = p[-1]
            print(f"  {prod}: final PnL = {p[-1]:.2f}")

    tom_pnl = total_pnl_by_product.get("TOMATOES", 0)
    total = sum(total_pnl_by_product.values())
    print(f"\n  Total PnL across all products: {total:.2f}")
    print(f"  TOMATOES contribution: {tom_pnl:.2f} ({100*tom_pnl/total:.1f}% of total)" if total != 0 else "")
    print(f"  PnL WITHOUT TOMATOES: {total - tom_pnl:.2f}")

    # =========================================================================
    # 3b. WHAT IF POSITION CAPPED AT +/-10?
    # =========================================================================
    print("\n" + "-" * 40)
    print("  COUNTERFACTUAL: TOMATOES position capped at +/-10")
    print("-" * 40)
    if tom_recs:
        # We can't directly see position from activitiesLog, but we can approximate:
        # PnL = sum of (mid_price changes * position). Without trade data we estimate
        # by looking at PnL changes relative to mid changes.
        ts_t, mid_t, pnl_t, _, _ = extract_series(tom_recs)
        dpnl_t = np.diff(pnl_t)
        dmid_t = np.diff(mid_t)

        # Estimate position: dpnl ≈ position * dmid (for mark-to-market PnL)
        # position ≈ dpnl / dmid where dmid != 0
        valid = np.abs(dmid_t) > 1e-6
        if valid.sum() > 0:
            est_pos = np.zeros(len(dpnl_t))
            est_pos[valid] = dpnl_t[valid] / dmid_t[valid]
            # Forward-fill where dmid=0
            last_pos = 0
            for i in range(len(est_pos)):
                if valid[i]:
                    last_pos = est_pos[i]
                else:
                    est_pos[i] = last_pos

            print(f"  Estimated position: min={est_pos.min():.1f}, max={est_pos.max():.1f}, "
                  f"mean={est_pos.mean():.1f}")

            # If we cap at +/-10
            capped_pos = np.clip(est_pos, -10, 10)
            capped_dpnl = capped_pos * dmid_t
            capped_pnl = np.cumsum(capped_dpnl)

            print(f"  Capped PnL estimate (position +/-10): {capped_pnl[-1]:.2f}")
            print(f"  Uncapped PnL: {pnl_t[-1]:.2f}")
            print(f"  Difference: {capped_pnl[-1] - pnl_t[-1]:.2f}")
            print(f"  Capped max drawdown: {capped_pnl.max() - capped_pnl.min():.2f}")

            # Show position distribution
            pos_abs = np.abs(est_pos)
            print(f"\n  Estimated |position| distribution:")
            for thresh in [5, 10, 15, 20, 25, 30, 40, 50]:
                pct = 100 * np.mean(pos_abs > thresh)
                if pct > 0:
                    print(f"    |pos| > {thresh}: {pct:.1f}% of ticks")
        else:
            print("  Could not estimate positions (mid price never changes)")

    # =========================================================================
    # 4. EMERALDS ANALYSIS
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 4: EMERALDS ANALYSIS")
    print("=" * 80)

    em_recs = by_product.get("EMERALDS", [])
    if not em_recs:
        for k in by_product:
            if "EMERALD" in k.upper():
                em_recs = by_product[k]
                print(f"  (Using product key: {k})")
                break
    if not em_recs:
        print("  WARNING: No EMERALDS data found! Available products:", products)
    else:
        ts_e, mid_e, pnl_e, obi_e, spread_e = extract_series(em_recs)
        print(f"  Total ticks: {len(ts_e)}")
        print(f"  Final PnL: {pnl_e[-1]:.2f}")
        print(f"  Peak PnL: {pnl_e.max():.2f}")
        print(f"  Trough PnL: {pnl_e.min():.2f}")

        # Does it ever lose money?
        ever_negative = np.any(pnl_e < 0)
        min_pnl = pnl_e.min()
        print(f"\n  Does EMERALDS ever have negative PnL? {'YES' if ever_negative else 'NO'}")
        print(f"  Minimum PnL: {min_pnl:.2f}")
        negative_ticks = np.sum(pnl_e < 0)
        print(f"  Ticks with negative PnL: {negative_ticks}/{len(pnl_e)} "
              f"({100*negative_ticks/len(pnl_e):.1f}%)")

        dpnl_e = np.diff(pnl_e)
        print(f"\n  Tick PnL change: mean={dpnl_e.mean():.4f}, std={dpnl_e.std():.4f}")
        print(f"  Tick PnL change: min={dpnl_e.min():.2f}, max={dpnl_e.max():.2f}")

        # Average PnL per "trade cycle" — approximate as PnL gain per N ticks
        # or per segment where PnL changes
        nonzero_changes = dpnl_e[np.abs(dpnl_e) > 0.01]
        if len(nonzero_changes) > 0:
            gains = nonzero_changes[nonzero_changes > 0]
            losses = nonzero_changes[nonzero_changes < 0]
            print(f"\n  Non-zero PnL change ticks: {len(nonzero_changes)}")
            print(f"  Gain ticks: {len(gains)}, avg gain: {gains.mean():.4f}")
            if len(losses) > 0:
                print(f"  Loss ticks: {len(losses)}, avg loss: {losses.mean():.4f}")
            else:
                print(f"  Loss ticks: 0")
            print(f"  Net per active tick: {nonzero_changes.mean():.4f}")

        # Spread analysis — could we increase volume?
        print(f"\n  Spread stats:")
        print(f"    mean={spread_e.mean():.4f}, std={spread_e.std():.4f}")
        print(f"    min={spread_e.min():.2f}, max={spread_e.max():.2f}")

        print(f"\n  Mid-price: mean={mid_e.mean():.2f}, std={mid_e.std():.4f}, "
              f"range={mid_e.max()-mid_e.min():.2f}")

        # Sharpe
        sharpe_e = dpnl_e.mean() / dpnl_e.std() if dpnl_e.std() > 0 else 0
        print(f"\n  Sharpe-like ratio: {sharpe_e:.6f}")

    # =========================================================================
    # 5. CROSS-PRODUCT SHARPE COMPARISON
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 5: SHARPE-LIKE RATIO COMPARISON (ALL PRODUCTS)")
    print("=" * 80)

    print(f"\n  {'Product':<20} {'Final PnL':>12} {'Mean dPnL':>12} {'Std dPnL':>12} "
          f"{'Sharpe':>10} {'Max DD':>10} {'Ticks':>8}")
    print("  " + "-" * 94)

    for prod in sorted(products):
        recs = by_product[prod]
        ts_p, mid_p, pnl_p, _, _ = extract_series(recs)
        if len(pnl_p) < 2:
            continue
        dp = np.diff(pnl_p)
        sh = dp.mean() / dp.std() if dp.std() > 0 else 0
        max_dd = 0
        peak = pnl_p[0]
        for v in pnl_p:
            if v > peak:
                peak = v
            dd = peak - v
            if dd > max_dd:
                max_dd = dd
        print(f"  {prod:<20} {pnl_p[-1]:>12.2f} {dp.mean():>12.6f} {dp.std():>12.4f} "
              f"{sh:>10.6f} {max_dd:>10.2f} {len(pnl_p):>8}")

    # =========================================================================
    # 6. FINAL VERDICT
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 6: FINAL VERDICT — IS TOMATOES WORTH TRADING?")
    print("=" * 80)

    if tom_recs:
        ts_t, mid_t, pnl_t, _, _ = extract_series(tom_recs)
        dp_t = np.diff(pnl_t)
        sharpe_t = dp_t.mean() / dp_t.std() if dp_t.std() > 0 else 0

        # Running max drawdown
        peak = pnl_t[0]
        max_dd_t = 0
        for v in pnl_t:
            if v > peak:
                peak = v
            dd = peak - v
            if dd > max_dd_t:
                max_dd_t = dd

        # Calmar-like: final PnL / max drawdown
        calmar = pnl_t[-1] / max_dd_t if max_dd_t > 0 else float('inf')

        print(f"  TOMATOES final PnL: {pnl_t[-1]:.2f}")
        print(f"  TOMATOES max drawdown: {max_dd_t:.2f}")
        print(f"  TOMATOES Sharpe-like: {sharpe_t:.6f}")
        print(f"  TOMATOES Calmar-like (PnL/MaxDD): {calmar:.4f}")
        print(f"  TOMATOES contribution to total: {tom_pnl:.2f} / {total:.2f} = {100*tom_pnl/total:.1f}%")

        if calmar < 0.5:
            print("\n  ASSESSMENT: TOMATOES has a poor risk/reward ratio (Calmar < 0.5).")
            print("  The drawdown is disproportionately large relative to final PnL.")
        elif calmar < 1.0:
            print("\n  ASSESSMENT: TOMATOES has mediocre risk/reward (Calmar 0.5-1.0).")
            print("  It contributes PnL but with significant drawdown risk.")
        else:
            print("\n  ASSESSMENT: TOMATOES has acceptable risk/reward (Calmar > 1.0).")

        if sharpe_t < 0:
            print("  WARNING: Negative Sharpe — TOMATOES is actively destroying value on average!")
        elif sharpe_t < 0.01:
            print("  WARNING: Very low Sharpe — edge is thin and dominated by noise.")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
