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
                self.compress_trades(state.market_trades), state.position, self.compress_observations(state.observations)]

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

POSITION_LIMITS = {"EMERALDS": 80, "TOMATOES": 80}

EMERALDS_FAIR_VALUE = 10000
EMERALDS_TAKE_WIDTH = 1
EMERALDS_CLEAR_WIDTH = 0
EMERALDS_DISREGARD_EDGE = 2
EMERALDS_JOIN_EDGE = 1
EMERALDS_DEFAULT_EDGE = 8
EMERALDS_SOFT_LIMIT = 20
EMERALDS_BASE_SIZE = 20

TOMATOES_EMA_FAST = 5
TOMATOES_EMA_SLOW = 20
TOMATOES_TAKE_WIDTH = 1
TOMATOES_DEFAULT_EDGE = 2
TOMATOES_SOFT_LIMIT = 15
TOMATOES_HARD_LIMIT = 40
TOMATOES_BASE_SIZE = 12
TOMATOES_TREND_THRESHOLD = 2
TOMATOES_MOMENTUM_WINDOW = 10
# T3 variant: order book skew signal (YBansal / awatatani P3)
# book_skew = ln(best_bid_vol / best_ask_vol)
# when |skew| > threshold, lean quotes in that direction
TOMATOES_SKEW_THRESHOLD = 1.0   # ln(bid_vol/ask_vol) threshold


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
            if product == "EMERALDS":
                orders, trader_data = self.trade_emeralds(state, trader_data)
                result[product] = orders
            elif product == "TOMATOES":
                orders, trader_data = self.trade_tomatoes(state, trader_data)
                result[product] = orders

        conversions = 0
        traderData = json.dumps(trader_data)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def trade_emeralds(self, state: TradingState, trader_data: dict):
        product = "EMERALDS"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        fair = EMERALDS_FAIR_VALUE
        orders: List[Order] = []

        emerald_data = trader_data.get("EMERALDS", {})
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else fair
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else fair
        daily_low = min(emerald_data.get("daily_low", best_ask), best_ask)
        daily_high = max(emerald_data.get("daily_high", best_bid), best_bid)
        trader_data["EMERALDS"] = {"daily_low": daily_low, "daily_high": daily_high}

        buy_volume = 0
        sell_volume = 0

        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price > fair - EMERALDS_TAKE_WIDTH:
                break
            ask_vol = -order_depth.sell_orders[ask_price]
            can_buy = limit - (position + buy_volume)
            qty = min(ask_vol, can_buy)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                buy_volume += qty

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price < fair + EMERALDS_TAKE_WIDTH:
                break
            bid_vol = order_depth.buy_orders[bid_price]
            can_sell = limit + (position - sell_volume)
            qty = min(bid_vol, can_sell)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                sell_volume += qty

        current_pos = position + buy_volume - sell_volume
        if current_pos > EMERALDS_SOFT_LIMIT:
            clear_qty = current_pos - EMERALDS_SOFT_LIMIT
            can_sell = limit + (position - sell_volume)
            qty = min(clear_qty, can_sell)
            if qty > 0:
                orders.append(Order(product, fair + EMERALDS_CLEAR_WIDTH, -qty))
                sell_volume += qty
        elif current_pos < -EMERALDS_SOFT_LIMIT:
            clear_qty = -current_pos - EMERALDS_SOFT_LIMIT
            can_buy = limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                orders.append(Order(product, fair - EMERALDS_CLEAR_WIDTH, qty))
                buy_volume += qty

        current_pos = position + buy_volume - sell_volume
        skew = math.floor(current_pos / 10)

        bid_price = fair - EMERALDS_DEFAULT_EDGE - skew
        for price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if price >= fair - EMERALDS_DISREGARD_EDGE:
                continue
            if price >= fair - EMERALDS_JOIN_EDGE:
                bid_price = price
            else:
                bid_price = price + 1
            break

        ask_price = fair + EMERALDS_DEFAULT_EDGE - skew
        for price in sorted(order_depth.sell_orders.keys()):
            if price <= fair + EMERALDS_DISREGARD_EDGE:
                continue
            if price <= fair + EMERALDS_JOIN_EDGE:
                ask_price = price
            else:
                ask_price = price - 1
            break

        buy_size = EMERALDS_BASE_SIZE - max(0, current_pos) // 5
        sell_size = EMERALDS_BASE_SIZE + min(0, current_pos) // 5
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

    def trade_tomatoes(self, state: TradingState, trader_data: dict):
        product = "TOMATOES"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        orders: List[Order] = []

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders, trader_data

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        filtered_bids = {p: v for p, v in order_depth.buy_orders.items() if v >= 15}
        filtered_asks = {p: v for p, v in order_depth.sell_orders.items() if -v >= 15}

        if filtered_bids and filtered_asks:
            fb = max(filtered_bids.keys())
            fa = min(filtered_asks.keys())
            mid = (fb + fa) / 2
        else:
            mid = (best_bid + best_ask) / 2

        tomato_data = trader_data.get("TOMATOES", {})
        ema_fast = tomato_data.get("ema_fast", mid)
        ema_slow = tomato_data.get("ema_slow", mid)
        prices = tomato_data.get("prices", [])

        alpha_fast = 2 / (TOMATOES_EMA_FAST + 1)
        alpha_slow = 2 / (TOMATOES_EMA_SLOW + 1)
        ema_fast = alpha_fast * mid + (1 - alpha_fast) * ema_fast
        ema_slow = alpha_slow * mid + (1 - alpha_slow) * ema_slow

        prices.append(mid)
        if len(prices) > 50:
            prices = prices[-50:]

        fair = round(0.5 * mid + 0.5 * ema_fast)

        # T3: compute order book skew from best bid/ask volumes
        bid_vol_1 = order_depth.buy_orders.get(best_bid, 0)
        ask_vol_1 = -order_depth.sell_orders.get(best_ask, 0)

        book_skew = 0.0
        if bid_vol_1 > 0 and ask_vol_1 > 0:
            book_skew = math.log(bid_vol_1 / ask_vol_1)

        # book_skew > 0 means more bid pressure (bullish), shift quotes up
        # book_skew < 0 means more ask pressure (bearish), shift quotes down
        skew_shift = 0
        if book_skew > TOMATOES_SKEW_THRESHOLD:
            skew_shift = 1   # bullish signal
        elif book_skew < -TOMATOES_SKEW_THRESHOLD:
            skew_shift = -1  # bearish signal

        trend = ema_fast - ema_slow
        trending_up = trend > TOMATOES_TREND_THRESHOLD
        trending_down = trend < -TOMATOES_TREND_THRESHOLD

        eff_long_limit = TOMATOES_HARD_LIMIT
        eff_short_limit = TOMATOES_HARD_LIMIT
        if trending_down:
            eff_long_limit = TOMATOES_SOFT_LIMIT
        if trending_up:
            eff_short_limit = TOMATOES_SOFT_LIMIT

        buy_volume = 0
        sell_volume = 0

        for ask_price in sorted(order_depth.sell_orders.keys()):
            if ask_price > fair - TOMATOES_TAKE_WIDTH:
                break
            ask_vol = -order_depth.sell_orders[ask_price]
            can_buy = eff_long_limit - (position + buy_volume)
            qty = min(ask_vol, can_buy)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                buy_volume += qty

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if bid_price < fair + TOMATOES_TAKE_WIDTH:
                break
            bid_vol = order_depth.buy_orders[bid_price]
            can_sell = eff_short_limit + (position - sell_volume)
            qty = min(bid_vol, can_sell)
            if qty > 0:
                orders.append(Order(product, bid_price, -qty))
                sell_volume += qty

        current_pos = position + buy_volume - sell_volume

        if current_pos > 0 and trending_down:
            clear_qty = min(current_pos, max(5, abs(current_pos) // 2))
            can_sell = eff_short_limit + (position - sell_volume)
            qty = min(clear_qty, can_sell)
            if qty > 0:
                orders.append(Order(product, fair, -qty))
                sell_volume += qty
        elif current_pos < 0 and trending_up:
            clear_qty = min(-current_pos, max(5, abs(current_pos) // 2))
            can_buy = eff_long_limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                orders.append(Order(product, fair, qty))
                buy_volume += qty

        current_pos = position + buy_volume - sell_volume
        if current_pos > TOMATOES_SOFT_LIMIT and not trending_up:
            clear_qty = current_pos - TOMATOES_SOFT_LIMIT
            can_sell = eff_short_limit + (position - sell_volume)
            qty = min(clear_qty, can_sell)
            if qty > 0:
                orders.append(Order(product, fair + 1, -qty))
                sell_volume += qty
        elif current_pos < -TOMATOES_SOFT_LIMIT and not trending_down:
            clear_qty = -current_pos - TOMATOES_SOFT_LIMIT
            can_buy = eff_long_limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                orders.append(Order(product, fair - 1, qty))
                buy_volume += qty

        current_pos = position + buy_volume - sell_volume
        inv_skew = math.floor(current_pos / 5)

        spread = TOMATOES_DEFAULT_EDGE
        if trending_up or trending_down:
            spread += 2

        trend_shift = 0
        if trending_up:
            trend_shift = 1
        elif trending_down:
            trend_shift = -1

        # Apply both inventory skew and book skew shift
        bid_price = fair - spread - inv_skew + trend_shift + skew_shift
        ask_price = fair + spread - inv_skew + trend_shift + skew_shift

        buy_size = TOMATOES_BASE_SIZE
        sell_size = TOMATOES_BASE_SIZE
        buy_size -= max(0, current_pos) // 3
        sell_size += min(0, current_pos) // 3
        buy_size = max(3, min(20, buy_size))
        sell_size = max(3, min(20, sell_size))

        if trending_down:
            buy_size = max(2, buy_size // 2)
            sell_size = min(25, sell_size + 3)
        elif trending_up:
            sell_size = max(2, sell_size // 2)
            buy_size = min(25, buy_size + 3)

        can_buy = eff_long_limit - (position + buy_volume)
        qty = min(buy_size, can_buy)
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        can_sell = eff_short_limit + (position - sell_volume)
        qty = min(sell_size, can_sell)
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        trader_data["TOMATOES"] = {"ema_fast": ema_fast, "ema_slow": ema_slow, "prices": prices}
        return orders, trader_data
