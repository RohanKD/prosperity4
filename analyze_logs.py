import json

def parse_log(fname):
    with open(fname, "r") as f:
        content = f.read()

    # Extract each tick's lambdaLog by scanning for {"sandboxLog"
    # Structure: "logs":[{"sandboxLog":"","lambdaLog":"...","timestamp":N},...]
    # Each lambdaLog value is a JSON string containing escaped JSON

    # Split on tick boundaries
    tick_sep = '{"sandboxLog"'
    parts = content.split(tick_sep)

    results = []
    for part in parts[1:]:  # skip header
        # Extract the lambdaLog string value
        ll_start = part.find('"lambdaLog":"') + len('"lambdaLog":"')
        if ll_start < len('"lambdaLog":"'):
            continue
        # Find the closing quote - scan char by char
        i = ll_start
        in_escape = False
        ll_chars = []
        while i < len(part):
            ch = part[i]
            if in_escape:
                ll_chars.append(ch)
                in_escape = False
            elif ch == '\\':
                in_escape = True
                ll_chars.append(ch)
            elif ch == '"':
                break
            else:
                ll_chars.append(ch)
            i += 1
        ll_escaped = ''.join(ll_chars)
        # Unescape: \" -> ", \\ -> \
        ll_str = ll_escaped.replace('\\"', '"').replace('\\\\', '\\')
        try:
            tick = json.loads(ll_str)
            results.append(tick)
        except Exception as e:
            pass

    return results

for fname in ["98540.log", "98687.log"]:
    ticks = parse_log(f"C:/Users/kevin/stuff/prosperity4/{fname}")
    print(f"\n=== {fname}: {len(ticks)} ticks ===")

    em_buy = em_sell = tom_buy = tom_sell = 0
    em_pos_list = []
    tom_pos_list = []
    em_fills = tom_fills = 0
    em_fill_qty = tom_fill_qty = 0

    for tick in ticks:
        state = tick[0]
        orders = tick[1]
        positions = state[6]
        own_trades = state[4]

        em_pos_list.append(positions.get("EMERALDS", 0))
        tom_pos_list.append(positions.get("TOMATOES", 0))

        for t in own_trades:
            if t[0] == "EMERALDS":
                em_fills += 1
                em_fill_qty += abs(t[2])
            elif t[0] == "TOMATOES":
                tom_fills += 1
                tom_fill_qty += abs(t[2])

        for sym, sym_orders in orders.items():
            for price, qty in sym_orders:
                if sym == "EMERALDS":
                    if qty > 0: em_buy += qty
                    else: em_sell += abs(qty)
                elif sym == "TOMATOES":
                    if qty > 0: tom_buy += qty
                    else: tom_sell += abs(qty)

    print(f"  EMERALDS:")
    print(f"    orders placed: buy={em_buy:,}  sell={em_sell:,}")
    print(f"    fills: {em_fills} trades, {em_fill_qty} units")
    print(f"    pos: min={min(em_pos_list)}  max={max(em_pos_list)}  final={em_pos_list[-1]}")

    print(f"  TOMATOES:")
    print(f"    orders placed: buy={tom_buy:,}  sell={tom_sell:,}")
    print(f"    fills: {tom_fills} trades, {tom_fill_qty} units")
    print(f"    pos: min={min(tom_pos_list)}  max={max(tom_pos_list)}  final={tom_pos_list[-1]}")

    # First tick quote prices
    if ticks:
        first = ticks[0]
        print(f"  First tick EMERALDS orders: {first[1].get('EMERALDS', [])}")
        print(f"  First tick TOMATOES orders: {first[1].get('TOMATOES', [])}")
