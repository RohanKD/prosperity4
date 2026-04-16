"""
Exhaustive manual auction optimizer with visualization.
Scans ALL price/volume combos for both BUY and SELL.
"""
import numpy as np
import matplotlib.pyplot as plt


def compute_clearing(bids, asks):
    all_prices = sorted(set(p for p, _ in bids + asks))
    best_price, best_volume = None, 0
    for price in all_prices:
        demand = sum(v for p, v in bids if p >= price)
        supply = sum(v for p, v in asks if p <= price)
        matched = min(demand, supply)
        if matched >= best_volume:
            best_volume = matched
            best_price = price
    return best_price, best_volume


def simulate(bids, asks, side, my_price, my_volume):
    if side == 'buy':
        all_bids = bids + [(my_price, my_volume)]
        all_asks = list(asks)
    else:
        all_bids = list(bids)
        all_asks = asks + [(my_price, my_volume)]

    cp, matched = compute_clearing(all_bids, all_asks)
    if cp is None or matched == 0:
        return None, 0

    if side == 'buy':
        if my_price < cp:
            return cp, 0
        demand_above = sum(v for p, v in bids if p > my_price)
        others_same = sum(v for p, v in bids if p == my_price)
        remaining = max(0, matched - demand_above)
        total_at_level = others_same + my_volume
        my_fill = min(my_volume, int(remaining * my_volume / total_at_level)) if total_at_level > 0 else min(my_volume, remaining)
        return cp, my_fill
    else:
        if my_price > cp:
            return cp, 0
        supply_below = sum(v for p, v in asks if p < my_price)
        others_same = sum(v for p, v in asks if p == my_price)
        remaining = max(0, matched - supply_below)
        total_at_level = others_same + my_volume
        my_fill = min(my_volume, int(remaining * my_volume / total_at_level)) if total_at_level > 0 else min(my_volume, remaining)
        return cp, my_fill


def full_scan(name, bids, asks, auto_sell, fee, max_vol, price_range):
    prices = list(range(price_range[0], price_range[1] + 1))
    volumes = list(range(1000, max_vol + 1, 1000))

    # Arrays for heatmaps
    buy_profit = np.zeros((len(prices), len(volumes)))
    sell_profit = np.zeros((len(prices), len(volumes)))
    buy_clearing = np.zeros((len(prices), len(volumes)))
    sell_clearing = np.zeros((len(prices), len(volumes)))
    buy_filled = np.zeros((len(prices), len(volumes)))
    sell_filled = np.zeros((len(prices), len(volumes)))

    best_overall = (0, None)

    for i, price in enumerate(prices):
        for j, vol in enumerate(volumes):
            # BUY
            cp, filled = simulate(bids, asks, 'buy', price, vol)
            if cp is not None and filled > 0:
                ppu = auto_sell - cp - fee
                total = filled * ppu
                buy_profit[i, j] = total
                buy_clearing[i, j] = cp
                buy_filled[i, j] = filled
                if total > best_overall[0]:
                    best_overall = (total, ('BUY', price, vol, cp, filled, ppu, total))

            # SELL
            cp, filled = simulate(bids, asks, 'sell', price, vol)
            if cp is not None and filled > 0:
                ppu = cp - auto_sell - fee
                total = filled * ppu
                sell_profit[i, j] = total
                sell_clearing[i, j] = cp
                sell_filled[i, j] = filled
                if total > best_overall[0]:
                    best_overall = (total, ('SELL', price, vol, cp, filled, ppu, total))

    return prices, volumes, buy_profit, sell_profit, buy_clearing, sell_clearing, buy_filled, sell_filled, best_overall


def plot_product(axs, row, name, prices, volumes, buy_profit, sell_profit,
                 buy_clearing, buy_filled, sell_filled, best):
    vol_k = [v / 1000 for v in volumes]

    # 1. Buy profit heatmap
    ax = axs[row, 0]
    im = ax.imshow(buy_profit, aspect='auto', origin='lower',
                   extent=[vol_k[0], vol_k[-1], prices[0], prices[-1]],
                   cmap='RdYlGn', interpolation='nearest')
    plt.colorbar(im, ax=ax, label='Profit')
    ax.set_title(f'{name} - BUY Profit')
    ax.set_xlabel('Volume (k)')
    ax.set_ylabel('Price')
    if best and best[1][0] == 'BUY':
        _, bp, bv, _, _, _, _ = best[1]
        ax.plot(bv / 1000, bp, 'r*', markersize=15, label=f'Best: {best[0]:,.0f}')
        ax.legend(fontsize=8)

    # 2. Sell profit heatmap
    ax = axs[row, 1]
    im = ax.imshow(sell_profit, aspect='auto', origin='lower',
                   extent=[vol_k[0], vol_k[-1], prices[0], prices[-1]],
                   cmap='RdYlGn', interpolation='nearest')
    plt.colorbar(im, ax=ax, label='Profit')
    ax.set_title(f'{name} - SELL Profit')
    ax.set_xlabel('Volume (k)')
    ax.set_ylabel('Price')
    if best and best[1][0] == 'SELL':
        _, bp, bv, _, _, _, _ = best[1]
        ax.plot(bv / 1000, bp, 'r*', markersize=15, label=f'Best: {best[0]:,.0f}')
        ax.legend(fontsize=8)

    # 3. Profit vs volume at each price (line chart)
    ax = axs[row, 2]
    for i, price in enumerate(prices):
        buy_vals = buy_profit[i, :]
        if np.any(buy_vals > 0):
            ax.plot(vol_k, buy_vals, label=f'BUY@{price}', linewidth=1.5)
    for i, price in enumerate(prices):
        sell_vals = sell_profit[i, :]
        if np.any(sell_vals > 0):
            ax.plot(vol_k, sell_vals, '--', label=f'SELL@{price}', linewidth=1.5)
    ax.set_title(f'{name} - Profit vs Volume')
    ax.set_xlabel('Volume (k)')
    ax.set_ylabel('Profit')
    ax.legend(fontsize=6, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linewidth=0.5)

    # 4. Filled volume + clearing price
    ax2 = axs[row, 3]
    for i, price in enumerate(prices):
        filled_vals = buy_filled[i, :]
        if np.any(filled_vals > 0):
            ax2.plot(vol_k, filled_vals / 1000, label=f'BUY@{price}', linewidth=1.5)
    ax2.set_title(f'{name} - Filled Volume (k)')
    ax2.set_xlabel('Volume (k)')
    ax2.set_ylabel('Filled (k)')
    ax2.legend(fontsize=6, ncol=2)
    ax2.grid(True, alpha=0.3)


# ── Order books ──
flax_bids = [(30, 30000), (29, 5000), (28, 12000), (27, 28000)]
flax_asks = [(28, 40000), (31, 20000), (32, 20000), (33, 30000)]

mush_bids = [(20, 43000), (19, 17000), (18, 6000), (17, 5000),
             (16, 10000), (15, 5000), (14, 10000), (13, 7000)]
mush_asks = [(12, 20000), (13, 25000), (14, 35000), (15, 6000),
             (16, 5000), (18, 10000), (19, 12000)]

print("Scanning Dryland Flax (50k max)...")
f_prices, f_vols, f_bp, f_sp, f_bc, f_sc, f_bf, f_sf, f_best = \
    full_scan("Dryland Flax", flax_bids, flax_asks, 30, 0, 50000, (25, 35))

print("Scanning Ember Mushroom (75k max)...")
m_prices, m_vols, m_bp, m_sp, m_bc, m_sc, m_bf, m_sf, m_best = \
    full_scan("Ember Mushroom", mush_bids, mush_asks, 20, 0.10, 75000, (10, 25))

# Print results
print("\n" + "=" * 70)
print("DRYLAND FLAX")
if f_best[1]:
    s, p, v, cp, f, ppu, t = f_best[1]
    print(f"  OPTIMAL: {s} price={p}, volume={v:,}")
    print(f"  Clearing={cp}, Filled={f:,}, Profit/unit={ppu:.2f}, TOTAL={t:,.0f}")

print("\nEMBER MUSHROOM")
if m_best[1]:
    s, p, v, cp, f, ppu, t = m_best[1]
    print(f"  OPTIMAL: {s} price={p}, volume={v:,}")
    print(f"  Clearing={cp}, Filled={f:,}, Profit/unit={ppu:.2f}, TOTAL={t:,.0f}")

# Top 10 for each
print("\n--- FLAX Top 10 ---")
results = []
for i, price in enumerate(f_prices):
    for j, vol in enumerate(f_vols):
        if f_bp[i, j] > 0:
            results.append(('BUY', price, vol, f_bp[i, j]))
        if f_sp[i, j] > 0:
            results.append(('SELL', price, vol, f_sp[i, j]))
results.sort(key=lambda x: -x[3])
for side, price, vol, profit in results[:10]:
    print(f"  {side:>4} price={price}, vol={vol:>6,} -> profit={profit:>10,.0f}")

print("\n--- MUSHROOM Top 10 ---")
results = []
for i, price in enumerate(m_prices):
    for j, vol in enumerate(m_vols):
        if m_bp[i, j] > 0:
            results.append(('BUY', price, vol, m_bp[i, j]))
        if m_sp[i, j] > 0:
            results.append(('SELL', price, vol, m_sp[i, j]))
results.sort(key=lambda x: -x[3])
for side, price, vol, profit in results[:10]:
    print(f"  {side:>4} price={price}, vol={vol:>6,} -> profit={profit:>10,.0f}")

# Plot
fig, axs = plt.subplots(2, 4, figsize=(24, 10))
plot_product(axs, 0, "Dryland Flax", f_prices, f_vols, f_bp, f_sp, f_bc, f_bf, f_sf, f_best)
plot_product(axs, 1, "Ember Mushroom", m_prices, m_vols, m_bp, m_sp, m_bc, m_bf, m_sf, m_best)
plt.suptitle("Manual Auction Optimization - Full Scan", fontsize=16, fontweight='bold')
plt.tight_layout()
plt.savefig("/Users/rohan/prosperity4/manual_auction_analysis.png", dpi=150)
print("\nPlot saved to manual_auction_analysis.png")
