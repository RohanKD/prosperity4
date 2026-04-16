"""
Manual Auction Optimizer for IMC Prosperity 4 Round 1.

Auction mechanics:
- One order per product (buy OR sell, at a price and volume)
- Auction clears at a single price with price-time priority
- Dryland Flax: acquired units auto-sell at 30 XIRECs (no fee)
- Ember Mushroom: acquired units auto-sell at 20 XIRECs
  Trading fees: 0.05/unit buy + 0.05/unit sell = 0.10/unit round-trip

BUY profit  = (auto_sell - clearing_price - fees) * filled
SELL profit = (clearing_price - auto_sell - fees) * filled
  (selling = you provide supply, get clearing price, but forgo the auto-sell value)
"""


def compute_clearing(bids, asks):
    """
    Find auction clearing price: the price that maximizes matched volume.
    At each price, demand = sum of bids >= price, supply = sum of asks <= price.
    """
    all_prices = sorted(set(p for p, _ in bids + asks))
    best_price = None
    best_volume = 0
    for price in all_prices:
        demand = sum(v for p, v in bids if p >= price)
        supply = sum(v for p, v in asks if p <= price)
        matched = min(demand, supply)
        if matched >= best_volume:
            best_volume = matched
            best_price = price
    return best_price, best_volume


def simulate(bids, asks, side, my_price, my_volume):
    """
    Add my order, find clearing price, estimate my fill.
    Returns (clearing_price, my_filled_volume).
    """
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
        # Fill priority: highest bids first. At same price, pro-rata.
        demand_above = sum(v for p, v in bids if p > my_price)
        others_same = sum(v for p, v in bids if p == my_price)
        remaining = max(0, matched - demand_above)
        total_at_level = others_same + my_volume
        if my_price > cp:
            # I'm above clearing — fill all bids at my level before lower
            demand_strictly_above = sum(v for p, v in bids if p > my_price)
            remaining = max(0, matched - demand_strictly_above)
            total_at_level = others_same + my_volume
        if total_at_level > 0:
            my_fill = min(my_volume, int(remaining * my_volume / total_at_level))
        else:
            my_fill = min(my_volume, remaining)
        return cp, my_fill
    else:
        if my_price > cp:
            return cp, 0
        supply_below = sum(v for p, v in asks if p < my_price)
        others_same = sum(v for p, v in asks if p == my_price)
        remaining = max(0, matched - supply_below)
        total_at_level = others_same + my_volume
        if my_price < cp:
            supply_strictly_below = sum(v for p, v in asks if p < my_price)
            remaining = max(0, matched - supply_strictly_below)
            total_at_level = others_same + my_volume
        if total_at_level > 0:
            my_fill = min(my_volume, int(remaining * my_volume / total_at_level))
        else:
            my_fill = min(my_volume, remaining)
        return cp, my_fill


def optimize_product(name, bids, asks, auto_sell, fee_per_unit, max_volume=75000):
    print("=" * 70)
    print(f"{name} OPTIMIZATION")
    print(f"Auto-sell price: {auto_sell}  |  Fee/unit: {fee_per_unit}")
    print("=" * 70)

    # Show order book
    cp0, cv0 = compute_clearing(bids, asks)
    print(f"\nOrder book clearing (without me): price={cp0}, volume={cv0:,}")

    # Show supply/demand table
    all_prices = sorted(set(p for p, _ in bids + asks))
    print(f"\n{'Price':>6} {'Demand':>10} {'Supply':>10} {'Matched':>10}")
    for price in all_prices:
        d = sum(v for p, v in bids if p >= price)
        s = sum(v for p, v in asks if p <= price)
        m = min(d, s)
        marker = " ***" if price == cp0 else ""
        print(f"{price:>6} {d:>10,} {s:>10,} {m:>10,}{marker}")

    # Scan BUY strategies
    print(f"\n--- BUY strategies (buy at clearing, auto-sell at {auto_sell}) ---")
    print(f"  Profit/unit = {auto_sell} - clearing - {fee_per_unit}")
    print(f"{'Price':>6} {'Volume':>10} {'Clearing':>8} {'Filled':>10} {'$/unit':>8} {'Total Profit':>14}")

    best_buy = (0, None)
    volumes = [v for v in [1000, 5000, 10000, 20000, 30000, 40000, 50000, 60000, 75000] if v <= max_volume]
    for price in range(min(all_prices) - 2, max(all_prices) + 3):
        for vol in volumes:
            cp, filled = simulate(bids, asks, 'buy', price, vol)
            if cp is None or filled == 0:
                continue
            ppu = auto_sell - cp - fee_per_unit
            total = filled * ppu
            if total > best_buy[0]:
                best_buy = (total, ('BUY', price, vol, cp, filled, ppu, total))
            if total > 0:
                print(f"{price:>6} {vol:>10,} {cp:>8} {filled:>10,} {ppu:>8.2f} {total:>14,.0f}")

    # Scan SELL strategies
    print(f"\n--- SELL strategies (sell at clearing, forgo auto-sell at {auto_sell}) ---")
    print(f"  Profit/unit = clearing - {auto_sell} - {fee_per_unit}")
    print(f"{'Price':>6} {'Volume':>10} {'Clearing':>8} {'Filled':>10} {'$/unit':>8} {'Total Profit':>14}")

    best_sell = (0, None)
    for price in range(min(all_prices) - 2, max(all_prices) + 3):
        for vol in volumes:
            cp, filled = simulate(bids, asks, 'sell', price, vol)
            if cp is None or filled == 0:
                continue
            ppu = cp - auto_sell - fee_per_unit
            total = filled * ppu
            if total > best_sell[0]:
                best_sell = (total, ('SELL', price, vol, cp, filled, ppu, total))
            if total > 0:
                print(f"{price:>6} {vol:>10,} {cp:>8} {filled:>10,} {ppu:>8.2f} {total:>14,.0f}")

    # Summary
    print(f"\n{'='*70}")
    if best_buy[1]:
        s, p, v, cp, f, ppu, t = best_buy[1]
        print(f"  BEST BUY:  price={p}, vol={v:,} -> clearing={cp}, filled={f:,}, profit/unit={ppu:.2f}, TOTAL={t:,.0f}")
    else:
        print("  No profitable BUY found.")

    if best_sell[1]:
        s, p, v, cp, f, ppu, t = best_sell[1]
        print(f"  BEST SELL: price={p}, vol={v:,} -> clearing={cp}, filled={f:,}, profit/unit={ppu:.2f}, TOTAL={t:,.0f}")
    else:
        print("  No profitable SELL found.")

    winner = max(best_buy, best_sell, key=lambda x: x[0])
    if winner[1]:
        s, p, v, cp, f, ppu, t = winner[1]
        print(f"\n  >>> OPTIMAL: {s} at price {p}, volume {v:,}")
        print(f"      Expected profit: {t:,.0f} XIRECs")
    print()


if __name__ == "__main__":
    # DRYLAND FLAX
    flax_bids = [(30, 30000), (29, 5000), (28, 12000), (27, 28000)]
    flax_asks = [(28, 40000), (31, 20000), (32, 20000), (33, 30000)]
    optimize_product("DRYLAND FLAX", flax_bids, flax_asks,
                     auto_sell=30, fee_per_unit=0, max_volume=50000)

    # EMBER MUSHROOM
    mush_bids = [(20, 43000), (19, 17000), (18, 6000), (17, 5000),
                 (16, 10000), (15, 5000), (14, 10000), (13, 7000)]
    mush_asks = [(12, 20000), (13, 25000), (14, 35000), (15, 6000),
                 (16, 5000), (18, 10000), (19, 12000)]
    # Note: 17 has 0 volume, excluded
    optimize_product("EMBER MUSHROOM", mush_bids, mush_asks,
                     auto_sell=20, fee_per_unit=0.10, max_volume=75000)
