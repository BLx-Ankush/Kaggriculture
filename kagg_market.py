"""Market order construction: hiring, land, feed, livestock, seeds.

The headline fix in here is LABOR. Hire cost is fib(n) for the n-th hand of
the day, so cumulative cost per day is:

     3 hands -> $4      96 actions/day
     6 hands -> $20    168 actions/day
     8 hands -> $54    216 actions/day
    12 hands -> $376   312 actions/day
    14 hands -> $986   360 actions/day

The old agent capped at 3 hands with a hard `cost <= 5` gate. That is 96
actions/day, enough to service roughly 45 tiles, on a board that goes to 100.
Running 12-14 hands costs under 1% of what a mature farm earns per day and
roughly quadruples throughput. It is the single highest-leverage line here.

Second fix: buy wheat, do not grow it. Growing wheat returns ~$27 per action
spent. A cow eats one wheat a day and returns ~$405 a day. Spending farm
actions on feed production is burning the scarcest resource in the game.
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

    # 1. SELL FIRST. Market orders resolve in list order, so this cash is
    #    available to the buys below and the shed frees up for the day's
    #    harvests before anything can overflow.
    wheat_reserve = min(60, n_animals * 2)
    premium_crops = crop_counts.get("STRAWBERRY", 0) + crop_counts.get("MELON", 0)
    fert_reserve = 6 if premium_crops > 0 else 0
    pressure = max(0, 26 - shed_room)
    sales = plan_sales(shed, minv, prices, day, days_left,
                       wheat_reserve, fert_reserve, pressure)
    if hot:
        # Shared order book. If they are dumping, get out in front of it.
        sales.sort(key=lambda o: (o[1] not in hot, -prices.get(o[1], 0)))
    for o in sales[:5]:
        orders.append(o)
        cash += o[2] * prices.get(o[1], MP[o[1]]["base"]) * 0.85

    if endgame:
        # Nothing left worth investing in. Free shed space and liquidate.
        return orders[:10]

    # 2. LABOR. Cheapest multiplier in the game by an order of magnitude.
    if hour <= 1:
        workload = n_plants + n_animals * 2.5 + len(structs) + min(n_empty, 12)
        target = int(min(14, max(4, workload / 11.0 + 3)))
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

    # 3. LAND. $7k total for four times the tiles. Buy it the moment we are
    #    actually running out of ground, not before.
    n_extra = len(unlocked) - 1
    if n_extra < len(LAND_PRICES) and days_left > 10 and len(orders) < 10:
        cost = LAND_PRICES[n_extra]
        buffer = 600 if n_extra == 0 else 1200
        if cash >= cost + buffer and n_empty <= 14:
            orders.append(["BUY_LAND"])
            cash -= cost

    # 4. WHEAT for feed. Zero farm actions, and it keeps the herd alive.
    if n_animals > 0 and len(orders) < 10:
        want = min(n_animals * 3, 55) - wheat_have
        want = min(want, max(0, shed_room - 8))
        if want > 0 and cash > 400:
            px = price_at("WHEAT", minv.get("WHEAT", I0) - 1)
            qty = int(min(want, cash * 0.25 / max(1, px)))
            if qty > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", qty])
                cash -= qty * px

    # 5. LIVESTOCK for empty structures. Small batches only: bought animals
    #    land in the shed and the shed caps at 100 items.
    empty_pasture = 0
    empty_coop = 0
    for s in structs:
        kind = s[2].get("kind")
        if kind == "PASTURE":
            empty_pasture += 1
        elif kind == "COOP":
            empty_coop += 1
    held_animals = 0
    for a in ANIMALS:
        held_animals += shed.get(a, 0)
    room = min(4, shed_room - 2)
    if room > 0 and len(orders) < 10:
        wish = []
        need_p = max(0, empty_pasture - held_animals)
        # Cows first: best dollars per action in the game, but an eight day
        # lead time to first milk, so they have to be bought early.
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

    # 6. SEEDS, only for crops that can still finish before the season ends.
    if len(orders) < 10 and n_empty > 0:
        seeds_held = 0
        for v in seeds.values():
            if v > 0:
                seeds_held += v
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

    # 7. Fertilizer for the strawberries. Fertilized-and-watered doubles every
    #    scheduled yield, so $100 of input buys about $1000 of berries.
    if (len(orders) < 10 and cash > 2500 and days_left > 6
            and crop_counts.get("STRAWBERRY", 0) > 0
            and shed.get("FERTILIZER", 0) < 4 and shed_room > 10):
        orders.append(["BUY_PRODUCT", "FERTILIZER", 3])

    return orders[:10]
