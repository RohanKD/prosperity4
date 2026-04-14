import json
import math
from typing import Dict, List, Any
from datamodel import OrderDepth, TradingState, Order, ProsperityEncoder


class Logger:
    """Compressed JSON logger compatible with jmerle's Prosperity 3 Visualizer.
    See: https://jmerle.github.io/imc-prosperity-3-visualizer/
    """

    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(
        self,
        state: TradingState,
        orders: Dict[str, List[Order]],
        conversions: int,
        trader_data: str,
    ) -> None:
        base = [
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions,
            trader_data,
            self.logs,
        ]
        print(json.dumps(base, cls=ProsperityEncoder, separators=(",", ":")))
        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings) -> list:
        compressed = []
        for listing in listings.values():
            compressed.append(
                [listing.symbol, listing.product, listing.denomination]
            )
        return compressed

    def compress_order_depths(self, order_depths) -> dict:
        compressed = {}
        for symbol, od in order_depths.items():
            compressed[symbol] = [od.buy_orders, od.sell_orders]
        return compressed

    def compress_trades(self, trades) -> list:
        compressed = []
        for symbol, trade_list in trades.items():
            for t in trade_list:
                compressed.append(
                    [t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                )
        return compressed

    def compress_orders(self, orders) -> dict:
        compressed = {}
        for symbol, order_list in orders.items():
            compressed[symbol] = [[o.price, o.quantity] for o in order_list]
        return compressed

    def compress_observations(self, obs) -> list:
        conv = {}
        for product, co in obs.conversionObservations.items():
            conv[product] = [
                co.bidPrice,
                co.askPrice,
                co.transportFees,
                co.exportTariff,
                co.importTariff,
                co.sunlight,
                co.humidity,
            ]
        return [obs.plainValueObservations, conv]


logger = Logger()


# Position limits per product
POSITION_LIMITS = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

# EMERALDS: stationary asset, fair value anchored at 10,000
EMERALDS_FAIR_VALUE = 10000
EMERALDS_TAKE_WIDTH = 1        # take orders mispriced by >= this many ticks
EMERALDS_CLEAR_WIDTH = 0       # clear inventory at fair_value +/- this
EMERALDS_DISREGARD_EDGE = 1    # ignore book levels within this of fair value (was 2)
EMERALDS_JOIN_EDGE = 2         # join existing level if within this of fair value (was 1)
EMERALDS_DEFAULT_EDGE = 4      # default quote distance (was 8 - tighter to get more fills)
EMERALDS_SOFT_LIMIT = 30       # start inventory skewing here (was 20 - allow more)
EMERALDS_BASE_SIZE = 30        # base order size (was 20 - bigger to capture more)

# TOMATOES: mean-reverting drifter with OBI signal
# EDA findings: autocorr(1) = -0.44, OBI->future = +0.19, momentum = reverting at all scales
TOMATOES_EMA_FAST = 3          # very fast EMA for fair value
TOMATOES_EMA_SLOW = 15         # slow EMA for trend context
TOMATOES_TAKE_WIDTH = 1
TOMATOES_DEFAULT_EDGE = 2
TOMATOES_SOFT_LIMIT = 20       # moderate limit
TOMATOES_HARD_LIMIT = 50       # allow more exposure since we have better signals
TOMATOES_BASE_SIZE = 15
TOMATOES_MEAN_REV_WINDOW = 5   # lookback for mean-reversion signal
TOMATOES_OBI_WEIGHT = 2        # ticks to shift fair value per OBI unit
TOMATOES_REVERSION_WEIGHT = 0.5  # ticks to shift for mean-reversion signal


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

        logger.flush(state, result, conversions, traderData)
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
    # TOMATOES: Signal-driven market-making
    # Signals: mean-reversion (autocorr -0.44), OBI (+0.19), lead-lag from EMERALDS
    # ──────────────────────────────────────────────

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

        # Volume-weighted mid from large orders (market-maker quotes)
        filtered_bids = {p: v for p, v in order_depth.buy_orders.items() if v >= 15}
        filtered_asks = {p: v for p, v in order_depth.sell_orders.items() if -v >= 15}

        if filtered_bids and filtered_asks:
            fb = max(filtered_bids.keys())
            fa = min(filtered_asks.keys())
            mid = (fb + fa) / 2
        else:
            mid = (best_bid + best_ask) / 2

        # ── Update state ──
        tomato_data = trader_data.get("TOMATOES", {})
        ema_fast = tomato_data.get("ema_fast", mid)
        ema_slow = tomato_data.get("ema_slow", mid)
        prices = tomato_data.get("prices", [])
        prev_emerald_mid = tomato_data.get("prev_emerald_mid", None)

        alpha_fast = 2 / (TOMATOES_EMA_FAST + 1)
        alpha_slow = 2 / (TOMATOES_EMA_SLOW + 1)
        ema_fast = alpha_fast * mid + (1 - alpha_fast) * ema_fast
        ema_slow = alpha_slow * mid + (1 - alpha_slow) * ema_slow

        prices.append(mid)
        if len(prices) > 50:
            prices = prices[-50:]

        # ── SIGNAL 1: Order Book Imbalance (OBI) ──
        # EDA: corr(OBI, future_move_5tick) = +0.19 — strongest signal
        total_bid_vol = sum(order_depth.buy_orders.values())
        total_ask_vol = sum(-v for v in order_depth.sell_orders.values())
        obi = (total_bid_vol - total_ask_vol) / max(total_bid_vol + total_ask_vol, 1)
        # OBI > 0 means more bids → price likely going up
        obi_shift = obi * TOMATOES_OBI_WEIGHT  # shift fair value

        # ── SIGNAL 2: Mean Reversion ──
        # EDA: autocorr(1) = -0.44 — after a move, expect reversal
        mean_rev_shift = 0
        if len(prices) >= TOMATOES_MEAN_REV_WINDOW + 1:
            recent_move = prices[-1] - prices[-TOMATOES_MEAN_REV_WINDOW - 1]
            # If price moved up recently, expect reversion down → lower fair value
            mean_rev_shift = -recent_move * 0.08 * TOMATOES_REVERSION_WEIGHT

        # ── SIGNAL 3: Lead-Lag from EMERALDS ──
        # EDA: EMERALDS leads TOMATOES at lag -2 with corr 0.07
        lead_lag_shift = 0
        if "EMERALDS" in state.order_depths:
            e_od = state.order_depths["EMERALDS"]
            if e_od.buy_orders and e_od.sell_orders:
                e_mid = (max(e_od.buy_orders.keys()) + min(e_od.sell_orders.keys())) / 2
                if prev_emerald_mid is not None:
                    e_change = e_mid - prev_emerald_mid
                    # EMERALDS move predicts TOMATOES will follow (weakly)
                    lead_lag_shift = e_change * 0.03
                prev_emerald_mid = e_mid

        # ── Combined fair value ──
        # Base: heavily weight raw mid (reduce lag), plus signal adjustments
        raw_fair = 0.7 * mid + 0.3 * ema_fast
        adjusted_fair = raw_fair + obi_shift + mean_rev_shift + lead_lag_shift
        fair = round(adjusted_fair)

        # ── Position management ──
        eff_long_limit = TOMATOES_HARD_LIMIT
        eff_short_limit = TOMATOES_HARD_LIMIT

        buy_volume = 0
        sell_volume = 0

        # ── Phase 1: TAKE mispriced orders ──
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

        # ── Phase 2: CLEAR excess inventory ──
        current_pos = position + buy_volume - sell_volume

        # Aggressive clearing above soft limit
        if current_pos > TOMATOES_SOFT_LIMIT:
            clear_qty = current_pos - TOMATOES_SOFT_LIMIT
            can_sell = eff_short_limit + (position - sell_volume)
            qty = min(clear_qty, can_sell)
            if qty > 0:
                orders.append(Order(product, fair, -qty))
                sell_volume += qty
        elif current_pos < -TOMATOES_SOFT_LIMIT:
            clear_qty = -current_pos - TOMATOES_SOFT_LIMIT
            can_buy = eff_long_limit - (position + buy_volume)
            qty = min(clear_qty, can_buy)
            if qty > 0:
                orders.append(Order(product, fair, qty))
                buy_volume += qty

        # ── Phase 3: MAKE passive quotes ──
        current_pos = position + buy_volume - sell_volume

        # Inventory skew: 1 tick per 5 units
        skew = math.floor(current_pos / 5)

        spread = TOMATOES_DEFAULT_EDGE

        bid_price = fair - spread - skew
        ask_price = fair + spread - skew

        # Inventory-aware sizing
        buy_size = TOMATOES_BASE_SIZE - max(0, current_pos) // 3
        sell_size = TOMATOES_BASE_SIZE + min(0, current_pos) // 3
        buy_size = max(3, min(25, buy_size))
        sell_size = max(3, min(25, sell_size))

        # OBI-informed sizing: if OBI says price going up, buy more aggressively
        if obi > 0.2:
            buy_size = min(25, buy_size + 3)
            sell_size = max(3, sell_size - 2)
        elif obi < -0.2:
            sell_size = min(25, sell_size + 3)
            buy_size = max(3, buy_size - 2)

        can_buy = eff_long_limit - (position + buy_volume)
        qty = min(buy_size, can_buy)
        if qty > 0:
            orders.append(Order(product, bid_price, qty))

        can_sell = eff_short_limit + (position - sell_volume)
        qty = min(sell_size, can_sell)
        if qty > 0:
            orders.append(Order(product, ask_price, -qty))

        # Persist state
        trader_data["TOMATOES"] = {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "prices": prices,
            "prev_emerald_mid": prev_emerald_mid,
        }

        return orders, trader_data