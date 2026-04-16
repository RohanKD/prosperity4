import json

BACKSLASH = chr(92)

def parse_log(fname):
    with open(fname, "r") as f:
        content = f.read()
    tick_sep = '{"sandboxLog"'
    parts = content.split(tick_sep)
    results = []
    for part in parts[1:]:
        ll_start = part.find('"lambdaLog":"') + len('"lambdaLog":"')
        if ll_start < len('"lambdaLog":"'):
            continue
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
        ll_escaped = ''.join(ll_chars)
        ll_str = ll_escaped.replace('\\"', '"').replace(BACKSLASH * 2, BACKSLASH)
        try:
            tick = json.loads(ll_str)
            results.append(tick)
        except:
            pass
    return results

ticks_old = parse_log("C:/Users/kevin/stuff/prosperity4/98540.log")
ticks_new = parse_log("C:/Users/kevin/stuff/prosperity4/98687.log")

print(f"Old ticks: {len(ticks_old)}, New ticks: {len(ticks_new)}")

# Compare TOMATOES behavior
diff_ticks = 0
spike_skip_ticks = 0
shown = 0

for i, (old, new) in enumerate(zip(ticks_old, ticks_new)):
    ts = old[0][0]
    old_tom = old[1].get("TOMATOES", [])
    new_tom = new[1].get("TOMATOES", [])

    if old_tom != new_tom:
        diff_ticks += 1
        if len(new_tom) < len(old_tom):
            spike_skip_ticks += 1
        if shown < 20:
            print(f"ts={ts}: OLD={old_tom} -> NEW={new_tom}")
            shown += 1

print(f"\nTotal ticks with different TOMATOES orders: {diff_ticks}")
print(f"  Ticks where new has fewer orders (spike skip): {spike_skip_ticks}")
print(f"  Ticks where new has different (not fewer) orders: {diff_ticks - spike_skip_ticks}")

# EMERALDS diff
diff_em = 0
shown_em = 0
for old, new in zip(ticks_old, ticks_new):
    ts = old[0][0]
    old_em = old[1].get("EMERALDS", [])
    new_em = new[1].get("EMERALDS", [])
    if old_em != new_em:
        diff_em += 1
        if shown_em < 10:
            print(f"EMERALDS ts={ts}: OLD={old_em} -> NEW={new_em}")
            shown_em += 1

print(f"\nTotal ticks with different EMERALDS orders: {diff_em}")

# Check actual realized PnL from trades
# own_trades format: [sym, price, qty, buyer, seller, ts]
# buyer=SUBMISSION means we bought, seller=SUBMISSION means we sold
old_pnl_em = old_pnl_tom = 0
new_pnl_em = new_pnl_tom = 0

seen_old = set()
seen_new = set()

for tick in ticks_old:
    state = tick[0]
    for t in state[4]:  # own_trades
        key = (t[0], t[1], t[2], t[5])
        if key in seen_old:
            continue
        seen_old.add(key)
        sym, price, qty, buyer, seller = t[0], t[1], t[2], t[3], t[4]
        if buyer == "SUBMISSION":
            pnl_delta = -price * qty
        else:
            pnl_delta = price * qty
        if sym == "EMERALDS":
            old_pnl_em += pnl_delta
        elif sym == "TOMATOES":
            old_pnl_tom += pnl_delta

for tick in ticks_new:
    state = tick[0]
    for t in state[4]:
        key = (t[0], t[1], t[2], t[5])
        if key in seen_new:
            continue
        seen_new.add(key)
        sym, price, qty, buyer, seller = t[0], t[1], t[2], t[3], t[4]
        if buyer == "SUBMISSION":
            pnl_delta = -price * qty
        else:
            pnl_delta = price * qty
        if sym == "EMERALDS":
            new_pnl_em += pnl_delta
        elif sym == "TOMATOES":
            new_pnl_tom += pnl_delta

print(f"\nCash flow from trades (not accounting for final inventory):")
print(f"  OLD: EMERALDS={old_pnl_em:,}  TOMATOES={old_pnl_tom:,}  TOTAL={old_pnl_em+old_pnl_tom:,}")
print(f"  NEW: EMERALDS={new_pnl_em:,}  TOMATOES={new_pnl_tom:,}  TOTAL={new_pnl_em+new_pnl_tom:,}")
print(f"  DIFF: EMERALDS={new_pnl_em-old_pnl_em:,}  TOMATOES={new_pnl_tom-old_pnl_tom:,}  TOTAL={new_pnl_em+new_pnl_tom-old_pnl_em-old_pnl_tom:,}")

# Final positions
old_final = ticks_old[-1][0][6]
new_final = ticks_new[-1][0][6]
print(f"\nFinal positions: OLD={old_final}  NEW={new_final}")
