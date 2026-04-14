import json
import math
from typing import Dict, List, Any
from datamodel import OrderDepth, TradingState, Order, ProsperityEncoder


class Logger:
    def __init__(self) -> None:
        self.logs = ""

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: Dict[str, List[Order]],
              conversions: int, trader_data: str) -> None:
        base = [
            self.compress_state(state),
            self.compress_orders(orders),
            conversions, trader_data, self.logs,
        ]
        print(json.dumps(base, cls=ProsperityEncoder, separators=(",", ":")))
        self.logs = ""

    def compress_state(self, state: TradingState) -> list:
        return [
            state.timestamp, "",
            [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
            {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
            [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
             for tl in state.own_trades.values() for t in tl],
            [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
             for tl in state.market_trades.values() for t in tl],
            state.position,
            [state.observations.plainValueObservations,
             {p: [c.bidPrice, c.askPrice, c.transportFees, c.exportTariff,
                  c.importTariff, c.sunlight, c.humidity]
              for p, c in state.observations.conversionObservations.items()}],
        ]

    def compress_orders(self, orders) -> dict:
        return {s: [[o.price, o.quantity] for o in ol] for s, ol in orders.items()}


logger = Logger()

# ════════════════════════════════════════════════════════════
# Configuration per product
# ════════════════════════════════════════════════════════════

PRODUCTS = {
    # ── Stationary products: market-make around known fair value ──
    "EMERALDS": {
        "type": "stationary",
        "fair_value": 10000,
        "position_limit": 80,
        "take_width": 1,
        "clear_width": 0,
        "disregard_edge": 1,
        "join_edge": 2,
        "default_edge": 4,
        "soft_limit": 50,
        "base_size": 40,
        "skew_per": 10,
    },
    "ASH_COATED_OSMIUM": {
        "type": "stationary",
        "fair_value": 10000,
        "position_limit": 80,
        "take_width": 1,
        "clear_width": 0,
        "disregard_edge": 1,
        "join_edge": 2,
        "default_edge": 4,
        "soft_limit": 50,
        "base_size": 40,
        "skew_per": 10,
    },
    # ── Drifting products: adaptive fair value from order book ──
    "TOMATOES": {
        "type": "drifter",
        "position_limit": 80,
        "take_width": 1,
        "default_edge": 3,
        "soft_limit": 20,
        "hard_limit": 40,
        "base_size": 15,
        "skew_per": 5,
        "vol_filter": 15,     # min volume to count as market-maker quote
    },
    "INTARIAN_PEPPER_ROOT": {
        "type": "ipr",
        "position_limit": 80,
        "take_width": 1,
        "default_edge": 5,
        "soft_limit": 25,
        "hard_limit": 55,
        "base_size": 15,
        "skew_per": 5,
        "vol_filter": 15,
        "obi_weight": 2.0,        # directional OBI: heavy bids → price RISE (+0.27 corr)
        "reversion_coeff": 0.4,   # mean reversion: autocorr(1) = -0.50
    },
}


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
            if product not in PRODUCTS:
                continue
            cfg = PRODUCTS[product]
            if cfg["type"] == "stationary":
                orders = self.trade_stationary(product, state, cfg)
            elif cfg["type"] == "ipr":
                orders, trader_data = self.trade_ipr(product, state, cfg, trader_data)
            else:
                orders, trader_data = self.trade_drifter(product, state, cfg, trader_data)
            result[product] = orders

        conversions = 0
        traderData = json.dumps(trader_data)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    # ════════════════════════════════════════════════════════
    # Stationary: EMERALDS, ASH_COATED_OSMIUM
    # Three-phase: Take -> Clear -> Make around known fair value
    # ════════════════════════════════════════════════════════

    def trade_stationary(self, product: str, state: TradingState, cfg: dict) -> List[Order]:
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = cfg["position_limit"]
        fair = cfg["fair_value"]
        orders: List[Order] = []
        bv = 0  # buy volume tracker
        sv = 0  # sell volume tracker

        # ── TAKE: buy cheap asks, sell expensive bids ──
        for price in sorted(od.sell_orders.keys()):
            if price > fair - cfg["take_width"]:
                break
            vol = -od.sell_orders[price]
            qty = min(vol, limit - (pos + bv))
            if qty > 0:
                orders.append(Order(product, price, qty))
                bv += qty

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price < fair + cfg["take_width"]:
                break
            vol = od.buy_orders[price]
            qty = min(vol, limit + (pos - sv))
            if qty > 0:
                orders.append(Order(product, price, -qty))
                sv += qty

        # ── CLEAR: reduce excess inventory ──
        cur = pos + bv - sv
        if cur > cfg["soft_limit"]:
            qty = min(cur - cfg["soft_limit"], limit + (pos - sv))
            if qty > 0:
                orders.append(Order(product, fair + cfg["clear_width"], -qty))
                sv += qty
        elif cur < -cfg["soft_limit"]:
            qty = min(-cur - cfg["soft_limit"], limit - (pos + bv))
            if qty > 0:
                orders.append(Order(product, fair - cfg["clear_width"], qty))
                bv += qty

        # ── MAKE: passive quotes with inventory skew ──
        cur = pos + bv - sv
        skew = math.floor(cur / cfg["skew_per"])

        # Determine bid price: join/improve existing level or use default
        bid_price = fair - cfg["default_edge"] - skew
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fair - cfg["disregard_edge"]:
                continue
            if price >= fair - cfg["join_edge"]:
                bid_price = price
            else:
                bid_price = price + 1
            break

        ask_price = fair + cfg["default_edge"] - skew
        for price in sorted(od.sell_orders.keys()):
            if price <= fair + cfg["disregard_edge"]:
                continue
            if price <= fair + cfg["join_edge"]:
                ask_price = price
            else:
                ask_price = price - 1
            break

        # Inventory-aware sizing
        buy_size = cfg["base_size"] - max(0, cur) // 5
        sell_size = cfg["base_size"] + min(0, cur) // 5
        buy_size = max(5, min(40, buy_size))
        sell_size = max(5, min(40, sell_size))

        if abs(cur) >= limit - 5:
            if cur > 0:
                buy_size = max(1, buy_size // 2)
                sell_size = min(50, sell_size * 2)
            else:
                sell_size = max(1, sell_size // 2)
                buy_size = min(50, buy_size * 2)

        qty = min(buy_size, limit - (pos + bv))
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        qty = min(sell_size, limit + (pos - sv))
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        return orders

    # ════════════════════════════════════════════════════════
    # Drifter: TOMATOES, INTARIAN_PEPPER_ROOT
    # Adaptive fair value from volume-filtered mid
    # ════════════════════════════════════════════════════════

    def trade_drifter(self, product: str, state: TradingState,
                      cfg: dict, trader_data: dict) -> tuple:
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        hard = cfg["hard_limit"]
        orders: List[Order] = []

        if not od.buy_orders or not od.sell_orders:
            return orders, trader_data

        best_bid = max(od.buy_orders.keys())
        best_ask = min(od.sell_orders.keys())

        # Volume-filtered mid: only use market-maker quotes
        vf = cfg["vol_filter"]
        fb = {p: v for p, v in od.buy_orders.items() if v >= vf}
        fa = {p: v for p, v in od.sell_orders.items() if -v >= vf}

        if fb and fa:
            mid = (max(fb.keys()) + min(fa.keys())) / 2
        else:
            mid = (best_bid + best_ask) / 2

        fair = round(mid)

        bv = 0  # buy volume
        sv = 0  # sell volume

        # ── TAKE ──
        for price in sorted(od.sell_orders.keys()):
            if price > fair - cfg["take_width"]:
                break
            vol = -od.sell_orders[price]
            qty = min(vol, hard - (pos + bv))
            if qty > 0:
                orders.append(Order(product, price, qty))
                bv += qty

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price < fair + cfg["take_width"]:
                break
            vol = od.buy_orders[price]
            qty = min(vol, hard + (pos - sv))
            if qty > 0:
                orders.append(Order(product, price, -qty))
                sv += qty

        # ── CLEAR ──
        cur = pos + bv - sv
        if cur > cfg["soft_limit"]:
            qty = min(cur - cfg["soft_limit"], hard + (pos - sv))
            if qty > 0:
                orders.append(Order(product, fair, -qty))
                sv += qty
        elif cur < -cfg["soft_limit"]:
            qty = min(-cur - cfg["soft_limit"], hard - (pos + bv))
            if qty > 0:
                orders.append(Order(product, fair, qty))
                bv += qty

        # ── MAKE ──
        cur = pos + bv - sv
        skew = math.floor(cur / cfg["skew_per"])

        bid_price = fair - cfg["default_edge"] - skew
        ask_price = fair + cfg["default_edge"] - skew

        buy_size = cfg["base_size"] - max(0, cur) // 3
        sell_size = cfg["base_size"] + min(0, cur) // 3
        buy_size = max(3, min(20, buy_size))
        sell_size = max(3, min(20, sell_size))

        qty = min(buy_size, hard - (pos + bv))
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        qty = min(sell_size, hard + (pos - sv))
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        return orders, trader_data

    # ════════════════════════════════════════════════════════
    # IPR: INTARIAN_PEPPER_ROOT — signal-enhanced drifter
    # OBI is DIRECTIONAL (+0.27): heavy bids → price RISE
    # Mean reversion: autocorr(1) = -0.50
    # ════════════════════════════════════════════════════════

    def trade_ipr(self, product: str, state: TradingState,
                  cfg: dict, trader_data: dict) -> tuple:
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        hard = cfg["hard_limit"]
        orders: List[Order] = []

        if not od.buy_orders or not od.sell_orders:
            return orders, trader_data

        best_bid = max(od.buy_orders.keys())
        best_ask = min(od.sell_orders.keys())

        # Volume-filtered mid
        vf = cfg["vol_filter"]
        fb = {p: v for p, v in od.buy_orders.items() if v >= vf}
        fa = {p: v for p, v in od.sell_orders.items() if -v >= vf}

        if fb and fa:
            mid = (max(fb.keys()) + min(fa.keys())) / 2
        else:
            mid = (best_bid + best_ask) / 2

        # ── Retrieve persisted state ──
        ipr_data = trader_data.get(product, {})
        prev_mid = ipr_data.get("prev_mid", mid)

        # ── SIGNAL 1: Directional OBI ──
        # IPR: heavy bids predict price RISE (corr +0.27)
        total_bid_vol = sum(od.buy_orders.values())
        total_ask_vol = sum(-v for v in od.sell_orders.values())
        obi = (total_bid_vol - total_ask_vol) / max(total_bid_vol + total_ask_vol, 1)
        obi_shift = obi * cfg["obi_weight"]

        # ── SIGNAL 2: Mean Reversion ──
        # autocorr(1) = -0.50: last tick's move partially reverses
        last_move = mid - prev_mid
        reversion_shift = -last_move * cfg["reversion_coeff"]

        # ── Fair value with signal adjustments ──
        fair = round(mid + obi_shift + reversion_shift)

        bv = 0
        sv = 0

        # ── TAKE ──
        for price in sorted(od.sell_orders.keys()):
            if price > fair - cfg["take_width"]:
                break
            vol = -od.sell_orders[price]
            qty = min(vol, hard - (pos + bv))
            if qty > 0:
                orders.append(Order(product, price, qty))
                bv += qty

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price < fair + cfg["take_width"]:
                break
            vol = od.buy_orders[price]
            qty = min(vol, hard + (pos - sv))
            if qty > 0:
                orders.append(Order(product, price, -qty))
                sv += qty

        # ── CLEAR ──
        cur = pos + bv - sv
        if cur > cfg["soft_limit"]:
            qty = min(cur - cfg["soft_limit"], hard + (pos - sv))
            if qty > 0:
                orders.append(Order(product, fair, -qty))
                sv += qty
        elif cur < -cfg["soft_limit"]:
            qty = min(-cur - cfg["soft_limit"], hard - (pos + bv))
            if qty > 0:
                orders.append(Order(product, fair, qty))
                bv += qty

        # ── MAKE ──
        cur = pos + bv - sv
        skew = math.floor(cur / cfg["skew_per"])

        bid_price = fair - cfg["default_edge"] - skew
        ask_price = fair + cfg["default_edge"] - skew

        buy_size = cfg["base_size"] - max(0, cur) // 3
        sell_size = cfg["base_size"] + min(0, cur) // 3
        buy_size = max(3, min(20, buy_size))
        sell_size = max(3, min(20, sell_size))

        # OBI-informed sizing: lean into the directional signal
        if obi > 0.15:
            # Heavy bids → expect rise → buy more, sell less
            buy_size = min(25, buy_size + 3)
            sell_size = max(2, sell_size - 3)
        elif obi < -0.15:
            # Heavy asks → expect drop → sell more, buy less
            sell_size = min(25, sell_size + 3)
            buy_size = max(2, buy_size - 3)

        qty = min(buy_size, hard - (pos + bv))
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        qty = min(sell_size, hard + (pos - sv))
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        # Persist state
        trader_data[product] = {"prev_mid": mid}

        return orders, trader_data


