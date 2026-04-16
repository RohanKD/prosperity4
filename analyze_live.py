"""Analyze a live Prosperity submission log to diagnose what went wrong."""
import json, math
from collections import defaultdict

BACKSLASH = chr(92)

def parse_ticks(fname):
    with open(fname, "r") as f:
        content = f.read()
    parts = content.split('{"sandboxLog"')
    results = []
    for part in parts[1:]:
        ll_start = part.find('"lambdaLog":"') + len('"lambdaLog":"')
        i = ll_start
        in_escape = False
        ll_chars = []
        while i < len(part):
            ch = part[i]
            if in_escape:
                ll_chars.append(ch)
                in_escape = False
            elif ch == BACKSLASH:
                in_escape = True
                ll_chars.append(ch)
            elif ch == '"':
                break
            else:
                ll_chars.append(ch)
            i += 1
        ll_str = ''.join(ll_chars).replace('\\"', '"').replace(BACKSLASH * 2, BACKSLASH)
        try:
            results.append(json.loads(ll_str))
        except:
            pass
    return results


def analyze(fname, label):
    ticks = parse_ticks(fname)
    print(f"\n{'='*60}")
    print(f"  {label}  ({len(ticks)} ticks)")
    print(f"{'='*60}")

    # Per-tick data
    spike_ticks = []
    wall_hits = 0
    wall_misses = 0
    em_positions = []
    tom_positions = []
    em_fills_qty = 0
    tom_fills_qty = 0
    tom_fair_values = []

    for tick in ticks:
        state = tick[0]
        orders = tick[1]
        ts = state[0]
        positions = state[6]
        own_trades = state[4]
        od = state[3]

        em_pos = positions.get("EMERALDS", 0)
        tom_pos = positions.get("TOMATOES", 0)
        em_positions.append(em_pos)
        tom_positions.append(tom_pos)

        for t in own_trades:
            if t[0] == "EMERALDS": em_fills_qty += abs(t[2])
            elif t[0] == "TOMATOES": tom_fills_qty += abs(t[2])

        # Detect spike ticks: TOMATOES has exactly 1 order (spike response)
        tom_orders = orders.get("TOMATOES", [])
        if len(tom_orders) == 1:
            qty = tom_orders[0][1]
            price = tom_orders[0][0]
            spike_ticks.append((ts, price, qty))

        # Detect wall-based mid usage
        if "TOMATOES" in od:
            tom_od = od["TOMATOES"]
            bids = tom_od[0]
            asks = tom_od[1]
            big_bids = {p: v for p, v in bids.items() if v >= 20}
            big_asks = {p: v for p, v in asks.items() if -v >= 20}
            if big_bids and big_asks:
                wall_hits += 1
            else:
                wall_misses += 1

        # Recover fair value from trader_data
        try:
            td = json.loads(tick[3]) if len(tick) > 3 else {}
            tom_td = td.get("TOMATOES", {})
            if "ema_short" in tom_td:
                tom_fair_values.append(round(tom_td["ema_short"]))
        except:
            pass

    print(f"\nFill volume:")
    print(f"  EMERALDS: {em_fills_qty:,} units filled")
    print(f"  TOMATOES: {tom_fills_qty:,} units filled")

    print(f"\nPosition ranges:")
    if em_positions:
        print(f"  EMERALDS: min={min(em_positions)}  max={max(em_positions)}  final={em_positions[-1]}")
    if tom_positions:
        print(f"  TOMATOES: min={min(tom_positions)}  max={max(tom_positions)}  final={tom_positions[-1]}")

    print(f"\nTOMATOES fair value (EMA-short):")
    if tom_fair_values:
        print(f"  min={min(tom_fair_values)}  max={max(tom_fair_values)}")
        print(f"  start={tom_fair_values[0]}  end={tom_fair_values[-1]}")

    print(f"\nWall-based mid: used {wall_hits} ticks / missed {wall_misses} ticks")
    print(f"  Wall usage rate: {wall_hits/(wall_hits+wall_misses)*100:.1f}%")

    print(f"\nSpike detection triggered: {len(spike_ticks)} ticks")
    if spike_ticks:
        print(f"  Sample spikes:")
        for ts, price, qty in spike_ticks[:10]:
            direction = "SELL" if qty < 0 else "BUY"
            print(f"    ts={ts}: {direction} qty={qty} at {price}")

    # Compute realized cash flow from own trades
    seen = set()
    em_cash = tom_cash = 0
    for tick in ticks:
        state = tick[0]
        for t in state[4]:
            key = (t[0], t[1], t[2], t[5])
            if key in seen: continue
            seen.add(key)
            sym, price, qty, buyer, seller = t[0], t[1], t[2], t[3], t[4]
            delta = price * qty if buyer != "SUBMISSION" else -price * qty
            if sym == "EMERALDS": em_cash += delta
            elif sym == "TOMATOES": tom_cash += delta

    final_em = em_positions[-1] if em_positions else 0
    final_tom = tom_positions[-1] if tom_positions else 0

    # Estimate fair value at end
    em_fair = 10000
    tom_fair_end = tom_fair_values[-1] if tom_fair_values else 5000

    em_pnl = em_cash + final_em * em_fair
    tom_pnl = tom_cash + final_tom * tom_fair_end

    print(f"\nEstimated PnL (cash + position * fair):")
    print(f"  EMERALDS: cash={em_cash:,.0f}  pos={final_em}  PnL≈{em_pnl:,.0f}")
    print(f"  TOMATOES: cash={tom_cash:,.0f}  pos={final_tom}  PnL≈{tom_pnl:,.0f}")
    print(f"  TOTAL≈{em_pnl+tom_pnl:,.0f}")


analyze("C:/Users/kevin/stuff/prosperity4/99207.log", "99207 (live)")
analyze("C:/Users/kevin/stuff/prosperity4/98540.log", "98540 original (live)")
