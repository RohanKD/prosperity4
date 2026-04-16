import json
import math
from typing import Dict, List, Any
from datamodel import OrderDepth, TradingState, Order, ProsperityEncoder


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state, orders, conversions, trader_data) -> None:
        base = [self.compress_state(state, ""), self.compress_orders(orders),
                conversions, trader_data, self.logs]
        print(json.dumps(base, cls=ProsperityEncoder, separators=(",", ":")))
        self.logs = ""

    def compress_state(self, state, trader_data) -> list:
        return [state.timestamp, trader_data, self.compress_listings(state.listings),
                self.compress_order_depths(state.order_depths), self.compress_trades(state.own_trades),
                self.compress_trades(state.market_trades), state.position,
                self.compress_observations(state.observations)]

    def compress_listings(self, listings) -> list:
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]

    def compress_order_depths(self, order_depths) -> dict:
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}

    def compress_trades(self, trades) -> list:
        return [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                for tl in trades.values() for t in tl]

    def compress_orders(self, orders) -> dict:
        return {s: [[o.price, o.quantity] for o in ol] for s, ol in orders.items()}

    def compress_observations(self, obs) -> list:
        conv = {}
        for product, co in obs.conversionObservations.items():
            conv[product] = [co.bidPrice, co.askPrice, co.transportFees,
                             co.exportTariff, co.importTariff, co.sunlight, co.humidity]
        return [obs.plainValueObservations, conv]


logger = Logger()

POSITION_LIMITS = {
    "INTARIAN_PEPPER_ROOT": 80,
    "ASH_COATED_OSMIUM": 80,
}

# ── INTARIAN_PEPPER_ROOT ──────────────────────────────────────────────────────
# The price drifts upward at exactly 0.001 per timestamp unit (≈1000 per day).
# Data: Day -2: 10000→11000, Day -1: 11000→12000, Day 0: 12000→13000
# STRATEGY: accumulate maximum long position (80 units × +3000 total = +240k).
#   - buy aggressively (even slightly above trend fair value)
#   - never voluntarily reduce long position
#   - clear shorts immediately (being short in an uptrend destroys value)
PEPPER_SLOPE = 0.001            # price increase per timestamp unit
PEPPER_TAKE_PREMIUM = 8         # buy asks up to 8 ticks ABOVE trend fair (worth it)
PEPPER_SELL_FLOOR = 15          # only fill sell side if bid is 15+ ticks above fair
PEPPER_BID_EDGE = 2             # passive bid at fair - 2 (aggressive, fills often)
PEPPER_ASK_EDGE = 20            # passive ask at fair + 20 (very wide, rarely fills)
PEPPER_BASE_BID_SIZE = 30       # large bids to accumulate fast
PEPPER_BASE_ASK_SIZE = 5        # small asks, we don't want to sell

# ── ASH_COATED_OSMIUM ─────────────────────────────────────────────────────────
# Stationary mean-reversion around 10000. Mean=10000.2, std=5.4 across all days.
# Bot spread: bids at 9992, asks at 10008 (8 ticks each side).
# STRATEGY: quote inside the bot spread to capture their spread as our edge.
#   - bid at 9995, ask at 10005 (5 ticks from fair, inside bot range)
#   - take any orders that cross fair by 1+ ticks
OSMIUM_FAIR_VALUE = 10000
OSMIUM_TAKE_WIDTH = 1           # take asks ≤ 9999, bids ≥ 10001
OSMIUM_CLEAR_WIDTH = 0          # clear excess inventory at exactly 10000
OSMIUM_DISREGARD_EDGE = 2       # ignore levels within 2 of fair for passive quoting
OSMIUM_DEFAULT_EDGE = 3        # was 5 � tighter spread
OSMIUM_SOFT_LIMIT = 20          # start skewing at ±20 inventory
OSMIUM_BASE_SIZE = 20


class Trader:

    def run(self, state: TradingState):
        trader_data = {}
        if state.traderData:
            try:
                trader_data = json.loads(state.traderData)
            except Exception:
                trader_data = {}

        result: Dict[str, List[Order]] = {}
        for product in state.order_depths:
            if product == "INTARIAN_PEPPER_ROOT":
                orders, trader_data = self.trade_pepper_root(state, trader_data)
                result[product] = orders
            elif product == "ASH_COATED_OSMIUM":
                orders, trader_data = self.trade_osmium(state, trader_data)
                result[product] = orders

        conversions = 0
        traderData = json.dumps(trader_data)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    # ─────────────────────────────────────────────────────────────────────────
    # INTARIAN_PEPPER_ROOT  —  buy and hold maximum long position
    # Fair value = day_start_price + timestamp * SLOPE
    # We want position = +80 as soon as possible and held as long as possible.
    # ─────────────────────────────────────────────────────────────────────────

    def trade_pepper_root(self, state: TradingState, trader_data: dict):
        product = "INTARIAN_PEPPER_ROOT"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        orders: List[Order] = []
        ts = state.timestamp

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders, trader_data

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        # Raw mid (use max-vol prices for stability)
        max_bid = max(order_depth.buy_orders.keys(),
                      key=lambda p: order_depth.buy_orders[p])
        max_ask = min(order_depth.sell_orders.keys(),
                      key=lambda p: -order_depth.sell_orders[p])
        raw_mid = (max_bid + max_ask) / 2

        # Detect new day: timestamp resets to 0. Update day_start_price.
        pepper_data = trader_data.get("INTARIAN_PEPPER_ROOT", {})
        last_ts = pepper_data.get("last_ts", ts)
        day_start_price = pepper_data.get("day_start_price", raw_mid)

        if ts < last_ts:
            # New day started — record the starting mid
            day_start_price = raw_mid

        # Trend-adjusted fair value
        fair = round(day_start_price + ts * PEPPER_SLOPE)

        trader_data["INTARIAN_PEPPER_ROOT"] = {
            "last_ts": ts,
            "day_start_price": day_start_price,
        }

        buy_volume = 0
        sell_volume = 0

        # ── TAKE: buy asks aggressively — even above trend fair ──
        # Any ask ≤ fair + PREMIUM is worth buying: the trend will cover the premium
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price > fair + PEPPER_TAKE_PREMIUM:
                break
            ask_vol = -order_depth.sell_orders[ask_price]
            can_buy = limit - (position + buy_volume)
            qty = min(ask_vol, can_buy)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                buy_volume += qty

        # Only sell if bids are very far above fair (someone is paying a big premium)
        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price < fair + PEPPER_SELL_FLOOR:
                break
            bid_vol = order_depth.buy_orders[bid_price]
            can_sell = limit + (position - sell_volume)
            qty = min(bid_vol, can_sell)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                sell_volume += qty

        # ── CLEAR: aggressively unwind shorts (being short in uptrend is bad) ──
        current_pos = position + buy_volume - sell_volume
        if current_pos < -5:
            clear_qty = min(-current_pos, 30)
            can_buy = limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                # Cross the spread to buy back immediately
                orders.append(Order(product, best_ask + 1, qty))
                buy_volume += qty

        # ── MAKE: aggressive bid to accumulate, very passive ask ──
        current_pos = position + buy_volume - sell_volume

        # Skew: if very long, slightly reduce bid aggressiveness (don't over-pile)
        long_excess = max(0, current_pos - 60)
        bid_edge = PEPPER_BID_EDGE + long_excess // 10

        bid_price = fair - bid_edge
        can_buy = limit - (position + buy_volume)
        bid_qty = min(PEPPER_BASE_BID_SIZE, can_buy)
        if bid_qty > 0:
            orders.append(Order(product, bid_price, bid_qty))

        # Ask: very wide — we don't want to sell unless price is far above fair
        ask_price = fair + PEPPER_ASK_EDGE
        can_sell = limit + (position - sell_volume)
        ask_qty = min(PEPPER_BASE_ASK_SIZE, can_sell)
        if ask_qty > 0:
            orders.append(Order(product, ask_price, -ask_qty))

        return orders, trader_data

    # ─────────────────────────────────────────────────────────────────────────
    # ASH_COATED_OSMIUM  —  market-make around fixed fair value of 10000
    # Bot spread: 9992 / 10008. We quote inside: 9995 / 10005.
    # Standard Take → Clear → Make with tight edge.
    # ─────────────────────────────────────────────────────────────────────────

    def trade_osmium(self, state: TradingState, trader_data: dict):
        product = "ASH_COATED_OSMIUM"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        fair = OSMIUM_FAIR_VALUE
        orders: List[Order] = []

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders, trader_data

        buy_volume = 0
        sell_volume = 0

        # ── TAKE: buy asks ≤ 9999, sell bids ≥ 10001 ──
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price > fair - OSMIUM_TAKE_WIDTH:
                break
            ask_vol = -order_depth.sell_orders[ask_price]
            can_buy = limit - (position + buy_volume)
            qty = min(ask_vol, can_buy)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                buy_volume += qty

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price < fair + OSMIUM_TAKE_WIDTH:
                break
            bid_vol = order_depth.buy_orders[bid_price]
            can_sell = limit + (position - sell_volume)
            qty = min(bid_vol, can_sell)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                sell_volume += qty

        # ── CLEAR: reduce inventory toward zero at fair ──
        current_pos = position + buy_volume - sell_volume
        if current_pos > OSMIUM_SOFT_LIMIT:
            clear_qty = current_pos - OSMIUM_SOFT_LIMIT
            can_sell = limit + (position - sell_volume)
            qty = min(clear_qty, can_sell)
            if qty > 0:
                orders.append(Order(product, fair + OSMIUM_CLEAR_WIDTH, -qty))
                sell_volume += qty
        elif current_pos < -OSMIUM_SOFT_LIMIT:
            clear_qty = -current_pos - OSMIUM_SOFT_LIMIT
            can_buy = limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                orders.append(Order(product, fair - OSMIUM_CLEAR_WIDTH, qty))
                buy_volume += qty

        # ── MAKE: quote inside the bot spread ──
        current_pos = position + buy_volume - sell_volume
        skew = math.floor(current_pos / 10)

        # Find best quote inside the bot range (ignore levels within DISREGARD_EDGE of fair)
        bid_price = fair - OSMIUM_DEFAULT_EDGE - skew
        for price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if price >= fair - OSMIUM_DISREGARD_EDGE:
                continue
            bid_price = price + 1   # penny in front of existing bid
            break

        ask_price = fair + OSMIUM_DEFAULT_EDGE - skew
        for price in sorted(order_depth.sell_orders.keys()):
            if price <= fair + OSMIUM_DISREGARD_EDGE:
                continue
            ask_price = price - 1   # penny in front of existing ask
            break

        # Clamp: never quote through fair
        bid_price = min(bid_price, fair - 1)
        ask_price = max(ask_price, fair + 1)

        # Inventory-adjusted sizing
        buy_size = OSMIUM_BASE_SIZE - max(0, current_pos) // 5
        sell_size = OSMIUM_BASE_SIZE + min(0, current_pos) // 5
        buy_size = max(5, min(30, buy_size))
        sell_size = max(5, min(30, sell_size))

        if abs(current_pos) >= limit - 5:
            if current_pos > 0:
                buy_size = max(1, buy_size // 2)
                sell_size = min(40, sell_size * 2)
            else:
                sell_size = max(1, sell_size // 2)
                buy_size = min(40, buy_size * 2)

        can_buy = limit - (position + buy_volume)
        qty = min(buy_size, can_buy)
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        can_sell = limit + (position - sell_volume)
        qty = min(sell_size, can_sell)
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        return orders, trader_data
