"""Market order construction: hiring, land, feed, livestock, seeds.

The first benchmark exposed a fatal gating bug: the old expansion condition
required `n_empty <= 14`, but the starting farm has 25 empty tiles. That meant
BUY_LAND never fired on the first quadrant, so the agent could not scale into
the production footprint used by the strong references.
"""

from kagg_core import (
    ANIMALS, CROPS, I0, LAND_PRICES, MP, TGT_COW, TGT_MELON, TGT_SHEEP,
    TGT_STRAW, fib, price_at,
)
from kagg_plan import plan_sales


def build_orders(money, shed, seeds, prices, minv, day, hour, days_left,
                 endgame, unlocked, hires_today, n_hands, counts, crop_counts,
                 structs, n_animals, wheat_have, n_empty, shed_room, hot,
                 n_plants):
    orders = []
    cash = money

    # Sell only when the marginal unit clears the reserve. Near-term shed
    # pressure can override this because overflow is worse than a soft price.
    wheat_reserve = min(60, n_animals * 2)
    premium_crops = crop_counts.get("STRAWBERRY", 0) + crop_counts.get("MELON", 0)
    fert_reserve = 6 if premium_crops > 0 else 0
    pressure = max(0, 26 - shed_room)
    sales = plan_sales(shed, minv, prices, day, days_left,
                       wheat_reserve, fert_reserve, pressure)
    if hot:
        sales.sort(key=lambda o: (o[1] not in hot, -prices.get(o[1], 0)))
    for o in sales[:5]:
        orders.append(o)
        # Conservative cash estimate for subsequent orders. The engine prices
        # each unit marginally, so never assume the whole batch sells at spot.
        cash += sum(prices.get(o[1], MP[o[1]]["base"]) * 0.65
                    for _ in range(o[2]))

    if endgame:
        return orders[:10]

    # Hire enough hands to exploit the unlocked footprint. The daily Fibonacci
    # cost is tiny relative to mature production, but stop during the opening
    # if cash is genuinely scarce.
    if hour <= 1:
        workload = n_plants + n_animals * 2.5 + len(structs) + min(n_empty, 24)
        target = int(min(14, max(6, workload / 9.0 + 3)))
        if day == 0:
            target = 8
        if days_left <= 3:
            target = min(target, 8)
        while n_hands < target and len(orders) < 9:
            cost = fib(hires_today)
            if cost > max(40, cash * 0.06):
                break
            orders.append(["HIRE"])
            cash -= cost
            hires_today += 1
            n_hands += 1

    # Expansion is an investment, not a reward for already filling the farm.
    # The previous `n_empty <= 14` gate was impossible on the starting 25-tile
    # quadrant, so it permanently trapped the policy in NW. Buy each quadrant
    # as soon as cash leaves a reasonable operating buffer, with a small delay
    # only to avoid starving the opening seed/animal purchases.
    n_extra = len(unlocked) - 1
    if n_extra < len(LAND_PRICES) and days_left > 10 and len(orders) < 10:
        cost = LAND_PRICES[n_extra]
        buffer = 1100 if n_extra == 0 else (1500 if n_extra == 1 else 2200)
        expansion_ready = (day <= 2 and n_extra == 0) or n_empty <= 18
        if expansion_ready and cash >= cost + buffer:
            orders.append(["BUY_LAND"])
            cash -= cost

    # Buy wheat for feed. Growing wheat spends farm actions; buying feed does
    # not, and keeps high-value animals producing.
    if n_animals > 0 and len(orders) < 10:
        want = min(n_animals * 3, 55) - wheat_have
        want = min(want, max(0, shed_room - 8))
        if want > 0 and cash > 400:
            px = price_at("WHEAT", minv.get("WHEAT", I0) - 1)
            qty = int(min(want, cash * 0.25 / max(1, px)))
            if qty > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", qty])
                cash -= qty * px

    # Fill empty structures with livestock in small batches.
    empty_pasture = sum(1 for s in structs if s[2].get("kind") == "PASTURE")
    empty_coop = sum(1 for s in structs if s[2].get("kind") == "COOP")
    held_animals = sum(shed.get(a, 0) for a in ANIMALS)
    room = min(4, shed_room - 2)
    if room > 0 and len(orders) < 10:
        wish = []
        need_p = max(0, empty_pasture - held_animals)
        if need_p > 0 and days_left >= 11 and counts["COW"] < TGT_COW:
            wish.append(("COW", min(need_p, TGT_COW - counts["COW"])))
        elif need_p > 0 and days_left >= 9 and counts["SHEEP"] < TGT_SHEEP:
            wish.append(("SHEEP", min(need_p, TGT_SHEEP - counts["SHEEP"])))
        if empty_coop > 0 and days_left >= 7:
            wish.append(("GOOSE", empty_coop))
        for name, n in wish:
            if len(orders) >= 10 or room <= 0:
                break
            cost = ANIMALS[name]["cost"]
            n = int(min(n, room, max(0, (cash - 500) // cost)))
            if n > 0:
                orders.append(["BUY_ANIMAL", name, n])
                cash -= n * cost
                room -= n

    # Seeds only for crops with enough time left to finish.
    if len(orders) < 10 and n_empty > 0:
        seeds_held = sum(v for v in seeds.values() if v > 0)
        for crop, gate, cap in (("MELON", 12, TGT_MELON),
                                ("STRAWBERRY", 13, TGT_STRAW),
                                ("WHEAT", 3, 999)):
            if days_left < gate or len(orders) >= 10:
                continue
            have = seeds.get(crop, 0) + crop_counts.get(crop, 0)
            want = min(cap - have, n_empty - seeds_held)
            if crop == "WHEAT":
                want = min(want, 6)
            if want <= 0:
                continue
            cost = CROPS[crop]["seed"]
            qty = int(min(want, max(0, (cash - 800) * 0.5 // cost), 12))
            if qty > 0:
                orders.append(["BUY_SEED", crop, qty])
                cash -= qty * cost
                seeds_held += qty

    # Fertilizer is reserved for premium crops.
    if (len(orders) < 10 and cash > 2500 and days_left > 6
            and premium_crops > 0 and shed.get("FERTILIZER", 0) < 4
            and shed_room > 10):
        orders.append(["BUY_PRODUCT", "FERTILIZER", 3])

    return orders[:10]
