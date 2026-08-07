"""
Kaggriculture Competitive Agent v3.0 â€” "Melon Baron"
=====================================================
Pure crop-farming strategy. No animals (too complex for marginal gains).

Core strategy:
- Day 0-2:  Buy carrot seeds (fast $35 crop, 2-day harvest)
- Day 0-5:  Also buy melon seeds early (high-value $250 crop, 10-12 day)
- Day 5-15: Plant melons on all available tiles, sell carrots + buy more seeds
- Day 15+:  Harvest & sell melons aggressively, plant wheat for quick turnaround
- Day 27+:  Endgame liquidation â€” sell everything in shed
- Expand land when profitable, hire hands when farm is big enough

Key engine facts verified from source:
- PICKUP/DROP only work on shed access tiles: (4,4),(5,4),(4,5),(5,5)
- Seeds go directly to private["seeds"], not shed
- BUY_SEED goes to seeds, BUY_PRODUCT goes to shed
- HARVEST puts items in farmer inventory â†’ need DROP at shed â†’ then SELL
- End-of-day auto-drops all inventories to shed (if capacity allows)
- Water in bonus window (day >= window_start and day <= max_yield_day) adds yield
- Fertilizer doubles water bonus yield (2 instead of 1)
"""

import math

# ============================================================================
# GAME CONSTANTS (verified from kaggriculture.py engine source)
# ============================================================================

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": 10000, "T": 400, "bf": "sqrt",   "bt": 0.80, "af": "log",    "at": 0.20},
    "CARROT":     {"base":  35, "I0": 10000, "T": 450, "bf": "log",    "bt": 0.20, "af": "sqrt",   "at": 0.70},
    "TOMATO":     {"base":  60, "I0": 10000, "T": 200, "bf": "linear", "bt": 0.40, "af": "sqrt",   "at": 0.60},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "bf": "sqrt",   "bt": 0.70, "af": "linear", "at": 1.60},
    "MELON":      {"base": 250, "I0": 10000, "T": 300, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.60},
    "EGG":        {"base":  50, "I0": 10000, "T": 332, "bf": "linear", "bt": 0.40, "af": "log",    "at": 0.20},
    "MILK":       {"base": 160, "I0": 10000, "T": 122, "bf": "sqrt",   "bt": 0.60, "af": "linear", "at": 1.60},
    "WOOL":       {"base": 200, "I0": 10000, "T": 105, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.20},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "bf": "linear", "bt": 0.40, "af": "linear", "at": 0.40},
}

LAND_PRICES = [1000, 2000, 4000]


def _shape(func, x):
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq":     return x * x
    if func == "sqrt":   return math.sqrt(x)
    if func == "log":    return math.log(1.0 + x)
    return x


def _market_price(item, inventory):
    """Compute exact market price using engine formula."""
    p = MARKET_PARAMS.get(item)
    if not p:
        return 1
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        amp = p["bt"] * base / _shape(p["bf"], T)
        price = base + amp * _shape(p["bf"], I0 - inventory)
    else:
        amp = p["at"] * base / _shape(p["af"], T)
        price = base - amp * _shape(p["af"], inventory - I0)
    return max(1, int(round(price)))
BOARD_SIZE = 10
HALF = 5
TURNS_PER_DAY = 24
TOTAL_DAYS = 30
SHED_TILES = frozenset([(4, 4), (5, 4), (4, 5), (5, 5)])


def _fib(n):
    """Fibonacci sequence for hire costs."""
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_dict(obj):
    if isinstance(obj, dict):
        return obj
    if obj is None:
        return {}
    try:
        return dict(obj)
    except Exception:
        return {}


def _quad(x, y):
    return ("N" if y < HALF else "S") + ("W" if x < HALF else "E")


def _move_toward(pos, target):
    """Single step toward target."""
    x, y = pos
    tx, ty = target
    if x < tx:   return ["EAST"]
    if x > tx:   return ["WEST"]
    if y < ty:   return ["SOUTH"]
    if y > ty:   return ["NORTH"]
    return ["PASS"]


def _nearest_shed(pos):
    best, best_d = (4, 4), 999
    for st in SHED_TILES:
        d = abs(pos[0] - st[0]) + abs(pos[1] - st[1])
        if d < best_d:
            best_d = d
            best = st
    return best


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ============================================================================
# CROP SELECTION
# ============================================================================

def _best_crop_to_buy(day, days_remaining, prices):
    """Decide which crop seeds to purchase."""
    if days_remaining <= 4:
        return "WHEAT"  # fastest harvest (2 days)
    if days_remaining <= 7:
        return "CARROT"  # better ROI than wheat for medium term

    # Compare ROI per day
    wheat_profit = prices.get("WHEAT", 25) * 4 - 10  # ~4 units, $10 seed
    wheat_days = 5  # plant-to-harvest cycle
    wheat_roi = wheat_profit / wheat_days  # ~18/day

    carrot_profit = prices.get("CARROT", 35) * 3 - 20  # ~3 units, $20 seed
    carrot_days = 4
    carrot_roi = carrot_profit / carrot_days  # ~21/day

    melon_profit = prices.get("MELON", 250) * 5 - 80  # ~5 units avg, $80 seed
    melon_days = 13
    melon_roi = melon_profit / melon_days if days_remaining > 13 else -1  # ~91/day!

    best = max(
        (wheat_roi, "WHEAT"),
        (carrot_roi, "CARROT"),
        (melon_roi, "MELON"),
    )
    return best[1]


def _pick_crop_to_plant(day, days_remaining, available_seeds, prices):
    """Pick which crop to plant from available seeds."""
    candidates = []

    for crop, qty in available_seeds.items():
        if qty <= 0:
            continue
        cd = CROPS.get(crop)
        if not cd:
            continue

        # Can this crop finish in time?
        if cd["ongoing"]:
            if days_remaining < cd["first_yield_day"] + cd["interval"]:
                continue
            avail = days_remaining - cd["first_yield_day"]
            n_yields = min(cd["max_yield"], avail // cd["interval"] + 1)
            price = prices.get(crop, MARKET_PARAMS.get(crop, {}).get("base", 50))
            revenue = n_yields * price
            profit = revenue - cd["seed"]
            days_occ = cd["first_yield_day"] + max(0, (n_yields - 1) * cd["interval"])
        else:
            if days_remaining < cd["first_yield_day"]:
                continue
            # Estimate yield based on watering bonus window
            ws = (cd["max_yield_day"] + 1) // 2
            if days_remaining >= cd["max_yield_day"]:
                bonus = cd["max_yield_day"] - ws + 1
            else:
                bonus = max(0, days_remaining - ws)
            expected_units = min(cd["max_yield"], 1 + bonus)
            price = prices.get(crop, MARKET_PARAMS.get(crop, {}).get("base", 25))
            revenue = expected_units * price
            profit = revenue - cd["seed"]
            days_occ = min(cd["max_yield_day"] + 1, days_remaining)

        if profit > 0:
            roi = profit / max(1, days_occ)
            candidates.append((roi, crop))

    if not candidates:
        for c in ["WHEAT", "CARROT", "MELON"]:
            if available_seeds.get(c, 0) > 0:
                return c
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


# ============================================================================
# MAIN AGENT
# ============================================================================

def agent(obs):
    try:
        return _agent_logic(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}


def _agent_logic(obs):
    # ---- Parse observation ----
    player = _get(obs, "player", 0)
    day = _get(obs, "day", 0)
    hour = _get(obs, "hour", 0)
    farms = _get(obs, "farms", [])
    market_obj = _get(obs, "market", {})
    private = _get(obs, "private", {})

    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    money = _get(farm, "money", 0)
    farmer_pos = tuple(_get(farm, "farmer", [4, 4]))
    hands_list = _get(farm, "hands", [])
    hands_pos = [tuple(h) for h in hands_list]
    unlocked = set(_get(farm, "unlocked_quadrants", ["NW"]))
    tiles = _get(farm, "tiles", [])
    hires_today = _get(farm, "hires_today", 0)

    shed = _to_dict(_get(private, "shed", {}))
    seeds = _to_dict(_get(private, "seeds", {}))
    inventories = _get(private, "inventories", [{}])
    farmer_inv = _to_dict(inventories[0] if inventories else {})

    prices = _to_dict(_get(market_obj, "prices", {}))

    days_remaining = TOTAL_DAYS - day
    n_unlocked = len(unlocked)

    # ---- Scan farm ----
    empty_tiles = []
    plant_tiles = []
    weed_tiles = []

    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if _quad(x, y) not in unlocked:
                continue
            tile = tiles[y][x] if y < len(tiles) and x < len(tiles[y]) else "LOCKED"
            if tile is None:
                empty_tiles.append((x, y))
            elif isinstance(tile, dict):
                kind = _get(tile, "kind", "")
                if kind == "PLANT":
                    plant_tiles.append((x, y, tile))
                elif kind == "WEED":
                    weed_tiles.append((x, y))

    n_plants = len(plant_tiles)
    n_empty = len(empty_tiles)

    # ---- Build priority job queue ----
    # Format: (priority, x, y, action)
    jobs = []

    # WATER â€” critical priority (unwatered 2 consecutive days = death)
    for x, y, tile in plant_tiles:
        if not _get(tile, "watered_today", False):
            consec = _get(tile, "consecutive_unwatered", 0)
            pri = 200 if consec >= 1 else 100
            jobs.append((pri, x, y, ["WATER"]))

    # HARVEST â€” high priority
    for x, y, tile in plant_tiles:
        if _get(tile, "yield_units", 0) > 0:
            crop = _get(tile, "crop", "")
            cd = CROPS.get(crop, {})
            age = day - _get(tile, "planted_day", 0)
            if age >= cd.get("first_yield_day", 2):
                jobs.append((90, x, y, ["HARVEST"]))

    # PLANT â€” medium priority
    available_seeds = {c: seeds.get(c, 0) for c in CROPS if seeds.get(c, 0) > 0}
    total_seeds = sum(available_seeds.values())
    if total_seeds > 0 and days_remaining > 2:
        for x, y in empty_tiles:
            crop = _pick_crop_to_plant(day, days_remaining, available_seeds, prices)
            if crop and available_seeds.get(crop, 0) > 0:
                jobs.append((70, x, y, ["PLANT", crop]))
                available_seeds[crop] -= 1

    # DIG WEEDS â€” low priority
    for x, y in weed_tiles:
        jobs.append((20, x, y, ["DIG"]))

    # Sort highest priority first
    jobs.sort(key=lambda j: -j[0])

    # ---- Assign units to jobs ----
    # Build unit list
    all_units = [(0, farmer_pos)]
    for i, hp in enumerate(hands_pos):
        all_units.append((i + 1, hp))

    unit_actions = {}

    # PRE-CHECK: If a unit has items in inventory, it needs to drop them at shed
    # (end-of-day auto-drops, but manual DROP is faster for continuous flow)
    for uid, upos in all_units:
        inv_idx = uid
        unit_inv = _to_dict(inventories[inv_idx] if inv_idx < len(inventories) else {})
        if unit_inv and any(v > 0 for v in unit_inv.values()):
            if upos in SHED_TILES:
                unit_actions[uid] = ["DROP"]
            else:
                unit_actions[uid] = _move_toward(upos, _nearest_shed(upos))

    # Assign remaining available units to jobs using greedy nearest-best
    taken_positions = set()
    for uid, upos in all_units:
        if uid in unit_actions:
            continue

        best = None
        best_score = -1
        for j_idx, (pri, jx, jy, action) in enumerate(jobs):
            if (jx, jy) in taken_positions:
                continue
            dist = _dist(upos, (jx, jy))
            score = pri / (dist + 1)
            if score > best_score:
                best_score = score
                best = (j_idx, jx, jy, action, dist)

        if best:
            j_idx, jx, jy, action, dist = best
            taken_positions.add((jx, jy))
            if dist == 0:
                unit_actions[uid] = action
            else:
                unit_actions[uid] = _move_toward(upos, (jx, jy))

    farmer_action = unit_actions.get(0, ["PASS"])
    hands_actions = [unit_actions.get(i + 1, ["PASS"]) for i in range(len(hands_pos))]

    # ---- Market orders ----
    market_orders = _market_orders(
        money, shed, seeds, prices, day, hour, days_remaining,
        n_unlocked, hires_today, len(hands_pos), n_plants, n_empty
    )

    return {
        "farmer": farmer_action,
        "hands": hands_actions,
        "market": market_orders,
    }


# ============================================================================
# MARKET ORDERS
# ============================================================================

def _market_orders(money, shed, seeds, prices, day, hour, days_remaining,
                   n_unlocked, hires_today, n_hands, n_plants, n_empty):
    orders = []
    budget = money
    endgame = days_remaining <= 3  # day 27, 28, 29
    near_endgame = days_remaining <= 5  # day 25-29
    shed_total = sum(shed.values())

    # ====== SELLING ======
    for product in PRODUCTS:
        qty = shed.get(product, 0)
        if qty <= 0:
            continue

        if endgame:
            orders.append(["SELL", product, qty])
            continue

        base = MARKET_PARAMS.get(product, {}).get("base", 25)
        price = prices.get(product, base)

        # Near endgame: sell more aggressively
        if near_endgame:
            orders.append(["SELL", product, qty])
            continue

        # Use market-price-aware selling: sell enough to stay above 50% base
        if product in ("MELON", "WOOL"):
            # Quadratic above-target: prices crash fast with oversupply
            # Sell small batches, but sell more if days are running out
            urgency = min(qty, max(2, qty * days_remaining // 30))
            batch = min(qty, max(3, urgency))
            if price >= max(1, base * 0.1):
                orders.append(["SELL", product, batch])
        elif product in ("STRAWBERRY", "MILK"):
            # Linear above-target: moderate price sensitivity
            batch = min(qty, max(3, qty * 2 // 3))
            if price >= max(1, base * 0.1):
                orders.append(["SELL", product, batch])
        else:
            # Non-premium (wheat, carrot, egg, fertilizer, tomato): sell freely
            orders.append(["SELL", product, qty])

    # ====== BUYING SEEDS ======
    total_seeds = sum(seeds.get(c, 0) for c in CROPS)
    need = max(0, n_empty - total_seeds)

    # Cap seeds to what we can actually plant per day with current workers
    workers = 1 + n_hands
    plantable_per_day = workers * 10
    sensible_need = min(need, plantable_per_day * max(1, days_remaining // 3))

    # Don't buy seeds in endgame or near-endgame
    if sensible_need > 0 and days_remaining > 4 and shed_total < 80:
        crop = _best_crop_to_buy(day, days_remaining, prices)
        cost = CROPS[crop]["seed"]

        # Spend aggressively early, conservatively late
        ratio = 0.6 if day < 2 else (0.4 if day < 8 else 0.2)
        max_spend = budget * ratio
        qty = min(sensible_need, int(max_spend / max(1, cost)))
        qty = min(qty, 15)  # cap per turn

        if qty > 0:
            orders.append(["BUY_SEED", crop, qty])
            budget -= qty * cost

        # Buy secondary crop if early enough
        if days_remaining > 15 and budget > 600 and crop != "MELON":
            sec_qty = min(5, int(budget * 0.15 / 80))  # melon = $80/seed
            if sec_qty > 0:
                orders.append(["BUY_SEED", "MELON", sec_qty])
                budget -= sec_qty * 80
        elif days_remaining > 10 and budget > 400 and crop != "CARROT":
            sec_qty = min(5, int(budget * 0.15 / 20))  # carrot = $20/seed
            if sec_qty > 0:
                orders.append(["BUY_SEED", "CARROT", sec_qty])
                budget -= sec_qty * 20

    # ====== HIRING ======
    if hour == 0 and days_remaining > 4:
        workload = n_plants + min(n_empty, total_seeds)
        target_hands = max(0, (workload - 10) // 8)
        target_hands = min(target_hands, 3)

        while n_hands < target_hands and hires_today < 4:
            cost = _fib(hires_today)
            if cost <= 5 and budget >= cost + 500:
                orders.append(["HIRE"])
                budget -= cost
                hires_today += 1
                n_hands += 1
            else:
                break

    # ====== LAND EXPANSION ======
    if hour == 0 and days_remaining > 12:
        n_extra = n_unlocked - 1
        if n_extra < len(LAND_PRICES):
            land_cost = LAND_PRICES[n_extra]
            # Expand when we're using >50% of land and can afford it
            usage = n_plants / max(1, n_plants + n_empty)
            if usage > 0.4 and budget >= land_cost * 1.3 and budget > 2000:
                orders.append(["BUY_LAND"])
                budget -= land_cost

    return orders[:10]
