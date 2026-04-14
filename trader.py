import json
import math
from typing import Dict, List, Any
from datamodel import OrderDepth, TradingState, Order


# Position limits per product
POSITION_LIMITS = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

# EMERALDS: stationary asset, fair value anchored at 10,000
EMERALDS_FAIR_VALUE = 10000
EMERALDS_TAKE_WIDTH = 1        # take orders mispriced by >= this many ticks
EMERALDS_CLEAR_WIDTH = 0       # clear inventory at fair_value +/- this
EMERALDS_DISREGARD_EDGE = 2    # ignore book levels within this of fair value for quoting
EMERALDS_JOIN_EDGE = 1         # join existing level if within this of fair value
EMERALDS_DEFAULT_EDGE = 8      # default quote distance from fair value
EMERALDS_SOFT_LIMIT = 20       # start inventory skewing here
EMERALDS_BASE_SIZE = 20        # base order size

# TOMATOES: drifting asset, use adaptive fair value
TOMATOES_EMA_SHORT = 10
TOMATOES_EMA_LONG = 30
TOMATOES_TAKE_WIDTH = 1
TOMATOES_DEFAULT_EDGE = 3
TOMATOES_SOFT_LIMIT = 20
TOMATOES_BASE_SIZE = 15


class Trader:

    def run(self, state: TradingState):
        # Deserialize persisted state
        trader_data = {}
        if state.traderData:
            try:
                trader_data = json.loads(state.traderData)
            except Exception:
                trader_data = {}

        result: Dict[str, List[Order]] = {}

        for product in state.order_depths:
            if product == "EMERALDS":
                orders, trader_data = self.trade_emeralds(state, trader_data)
                result[product] = orders
            elif product == "TOMATOES":
                orders, trader_data = self.trade_tomatoes(state, trader_data)
                result[product] = orders

        conversions = 0
        traderData = json.dumps(trader_data)
        return result, conversions, traderData

    # ──────────────────────────────────────────────
    # EMERALDS: Market-make around known fair value
    # Three-phase: Take -> Clear -> Make
    # ──────────────────────────────────────────────

    def trade_emeralds(self, state: TradingState, trader_data: dict):
        product = "EMERALDS"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        fair = EMERALDS_FAIR_VALUE
        orders: List[Order] = []

        # Track how much we're buying/selling to respect position limits
        buy_volume = 0
        sell_volume = 0

        # ── Phase 1: TAKE mispriced orders ──
        # Buy from asks below fair - take_width
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price > fair - EMERALDS_TAKE_WIDTH:
                break
            ask_vol = -order_depth.sell_orders[ask_price]  # sell_orders have negative qty
            can_buy = limit - (position + buy_volume)
            qty = min(ask_vol, can_buy)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                buy_volume += qty

        # Sell to bids above fair + take_width
        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price < fair + EMERALDS_TAKE_WIDTH:
                break
            bid_vol = order_depth.buy_orders[bid_price]
            can_sell = limit + (position - sell_volume)
            qty = min(bid_vol, can_sell)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                sell_volume += qty

        # ── Phase 2: CLEAR excess inventory ──
        current_pos = position + buy_volume - sell_volume
        if current_pos > EMERALDS_SOFT_LIMIT:
            # Sell to reduce position
            clear_qty = current_pos - EMERALDS_SOFT_LIMIT
            can_sell = limit + (position - sell_volume)
            qty = min(clear_qty, can_sell)
            if qty > 0:
                orders.append(Order(product, fair + EMERALDS_CLEAR_WIDTH, -qty))
                sell_volume += qty
        elif current_pos < -EMERALDS_SOFT_LIMIT:
            # Buy to reduce position
            clear_qty = -current_pos - EMERALDS_SOFT_LIMIT
            can_buy = limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                orders.append(Order(product, fair - EMERALDS_CLEAR_WIDTH, qty))
                buy_volume += qty

        # ── Phase 3: MAKE passive quotes ──
        current_pos = position + buy_volume - sell_volume

        # Inventory skew: shift quotes based on position
        skew = math.floor(current_pos / 10)

        # Determine bid price
        bid_price = fair - EMERALDS_DEFAULT_EDGE - skew
        # Check if we can join/improve an existing level
        for price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if price >= fair - EMERALDS_DISREGARD_EDGE:
                continue  # too close to fair, ignore
            if price >= fair - EMERALDS_JOIN_EDGE:
                bid_price = price  # join this level
            else:
                bid_price = price + 1  # penny in front
            break

        # Determine ask price
        ask_price = fair + EMERALDS_DEFAULT_EDGE - skew
        for price in sorted(order_depth.sell_orders.keys()):
            if price <= fair + EMERALDS_DISREGARD_EDGE:
                continue
            if price <= fair + EMERALDS_JOIN_EDGE:
                ask_price = price
            else:
                ask_price = price - 1
            break

        # Size adjustment based on inventory
        buy_size = EMERALDS_BASE_SIZE - max(0, current_pos) // 5
        sell_size = EMERALDS_BASE_SIZE + min(0, current_pos) // 5
        buy_size = max(5, min(30, buy_size))
        sell_size = max(5, min(30, sell_size))

        # Hard limit adjustments
        if abs(current_pos) >= limit - 5:
            if current_pos > 0:
                buy_size = max(1, buy_size // 2)
                sell_size = min(40, sell_size * 2)
            else:
                sell_size = max(1, sell_size // 2)
                buy_size = min(40, buy_size * 2)

        # Place passive quotes
        can_buy = limit - (position + buy_volume)
        qty = min(buy_size, can_buy)
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        can_sell = limit + (position - sell_volume)
        qty = min(sell_size, can_sell)
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        return orders, trader_data

    # ──────────────────────────────────────────────
    # TOMATOES: Adaptive market-making on a drifting asset
    # Uses EMA-based fair value estimation
    # ──────────────────────────────────────────────

    def trade_tomatoes(self, state: TradingState, trader_data: dict):
        product = "TOMATOES"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        orders: List[Order] = []

        # Compute mid price from order book
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders, trader_data

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        # Volume-filtered mid: ignore small orders (likely noise)
        filtered_bids = {p: v for p, v in order_depth.buy_orders.items() if v >= 15}
        filtered_asks = {p: v for p, v in order_depth.sell_orders.items() if -v >= 15}

        if filtered_bids and filtered_asks:
            fb = max(filtered_bids.keys())
            fa = min(filtered_asks.keys())
            mid = (fb + fa) / 2
        else:
            mid = (best_bid + best_ask) / 2

        # Update EMA history
        tomato_data = trader_data.get("TOMATOES", {})
        ema_short = tomato_data.get("ema_short", mid)
        ema_long = tomato_data.get("ema_long", mid)
        prices = tomato_data.get("prices", [])

        alpha_short = 2 / (TOMATOES_EMA_SHORT + 1)
        alpha_long = 2 / (TOMATOES_EMA_LONG + 1)
        ema_short = alpha_short * mid + (1 - alpha_short) * ema_short
        ema_long = alpha_long * mid + (1 - alpha_long) * ema_long

        prices.append(mid)
        if len(prices) > 50:
            prices = prices[-50:]

        # Fair value: use short EMA as the adaptive fair value
        fair = round(ema_short)

        # Compute volatility for dynamic spread
        if len(prices) >= 10:
            returns = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
            vol = max(1, round(math.sqrt(sum(r * r for r in returns[-10:]) / 10) * 1000))
        else:
            vol = TOMATOES_DEFAULT_EDGE

        spread = max(TOMATOES_DEFAULT_EDGE, vol)

        buy_volume = 0
        sell_volume = 0

        # ── Phase 1: TAKE mispriced orders ──
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price > fair - TOMATOES_TAKE_WIDTH:
                break
            ask_vol = -order_depth.sell_orders[ask_price]
            can_buy = limit - (position + buy_volume)
            qty = min(ask_vol, can_buy)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                buy_volume += qty

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price < fair + TOMATOES_TAKE_WIDTH:
                break
            bid_vol = order_depth.buy_orders[bid_price]
            can_sell = limit + (position - sell_volume)
            qty = min(bid_vol, can_sell)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                sell_volume += qty

        # ── Phase 2: MAKE passive quotes ──
        current_pos = position + buy_volume - sell_volume

        # Inventory skew
        skew = math.floor(current_pos / 10)

        bid_price = fair - spread - skew
        ask_price = fair + spread - skew

        # Size adjustments
        buy_size = TOMATOES_BASE_SIZE - max(0, current_pos) // 5
        sell_size = TOMATOES_BASE_SIZE + min(0, current_pos) // 5
        buy_size = max(5, min(25, buy_size))
        sell_size = max(5, min(25, sell_size))

        can_buy = limit - (position + buy_volume)
        qty = min(buy_size, can_buy)
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        can_sell = limit + (position - sell_volume)
        qty = min(sell_size, can_sell)
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        # Trend signal: if short EMA > long EMA, slightly favor longs
        if len(prices) >= TOMATOES_EMA_LONG and ema_short > ema_long + 1:
            # Bullish: add an extra bid closer to fair
            extra_bid = fair - 1 - skew
            can_buy_extra = limit - (position + buy_volume + qty)
            eq = min(5, can_buy_extra)
            if eq > 0:
                orders.append(Order(product, extra_bid, eq))
        elif len(prices) >= TOMATOES_EMA_LONG and ema_short < ema_long - 1:
            # Bearish: add an extra ask closer to fair
            extra_ask = fair + 1 - skew
            can_sell_extra = limit + (position - sell_volume - qty)
            eq = min(5, can_sell_extra)
            if eq > 0:
                orders.append(Order(product, extra_ask, -eq))

        # Persist state
        trader_data["TOMATOES"] = {
            "ema_short": ema_short,
            "ema_long": ema_long,
            "prices": prices,
        }

        return orders, trader_data
