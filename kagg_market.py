"""Market policy v3: capital-first opening.

The prior patch made BUY_LAND fire, but it put eight HIRE orders ahead of seeds,
animals, and feed. Kaggriculture silently caps market orders at ten per turn,
so day 0 became: 8 hires + land + almost no production. That is why the farm
expanded to two quadrants while ending with only a handful of animals.

This version treats the first four days as a capital ramp:
- reserve slots for seeds/animals/feed;
- hire gradually, reaching 12 hands by day 4;
- buy the first land only after the opening production orders are protected;
- never spend the entire bank on land plus infrastructure.
"""

from kagg_core import (
    ANIMALS, CROPS, I0, LAND_PRICES, MP, TGT_COW, TGT_MELON, TGT_SHEEP,
    TGT_STRAW, fib, price_at,
)
from kagg_plan import plan_sales


def _hire_target(day, workload, n_hands):
    # Market queue capacity is more valuable than early marginal labor.
    # Reach the strong-policy footprint without crowding out production buys.
    ramp = {0: 2, 1: 5, 2: 8, 3: 11, 4: 12}
    target = ramp.get(day, 12)
    if workload < 20:
        target = min(target, 6)
    return max(n_hands, min(12, target))


def build_orders(money, shed, seeds, prices, minv, day, hour, days_left,
                 endgame, unlocked, hires_today, n_hands, counts, crop_counts,
                 structs, n_animals, wheat_have, n_empty, shed_room, hot,
                 n_plants):
    orders = []
    cash = float(money)

    # Sell pressure only. Never rely on this for opening cash: the initial bank
    # must fund the first production cycle.
    wheat_reserve = min(60, n_animals * 2)
    premium = crop_counts.get("STRAWBERRY", 0) + crop_counts.get("MELON", 0)
    fert_reserve = 6 if premium else 0
    pressure = max(0, 26 - shed_room)
    sales = plan_sales(shed, minv, prices, day, days_left,
                       wheat_reserve, fert_reserve, pressure)
    if hot:
        sales.sort(key=lambda o: (o[1] not in hot, -prices.get(o[1], 0)))
    for o in sales[:4]:
        orders.append(o)
        cash += o[2] * prices.get(o[1], MP[o[1]]["base"]) * 0.65

    if endgame:
        return orders[:10]

    # Opening production is deliberately before hiring. The previous policy
    # consumed 8 of 10 queue slots on day 0 and starved itself.
    n_extra = len(unlocked) - 1
    land_cost = LAND_PRICES[n_extra] if n_extra < len(LAND_PRICES) else 999999

    # Reserve a realistic operating bank: land + feed + seeds/animals.
    # The first quadrant is delayed until day 1/2 unless cash is abundant.
    operating_reserve = 900 if day <= 2 else 650
    land_ready = (n_extra < len(LAND_PRICES) and days_left > 10
                  and cash >= land_cost + operating_reserve
                  and (day >= 1 or n_empty <= 18))

    # Seeds first. Melons are the opening cash engine; wheat is bought only as
    # feed later. Keep enough money to buy at least one animal batch.
    if len(orders) < 10 and n_empty > 0:
        seeds_held = sum(v for v in seeds.values() if v > 0)
        if days_left >= 12:
            have = seeds.get("MELON", 0) + crop_counts.get("MELON", 0)
            want = min(max(0, TGT_MELON - have), max(0, n_empty - seeds_held), 8)
            qty = int(min(want, max(0, (cash - operating_reserve - 650) // 80)))
            if qty > 0:
                orders.append(["BUY_SEED", "MELON", qty])
                cash -= qty * 80
                seeds_held += qty
        if len(orders) < 10 and days_left >= 3:
            have = seeds.get("WHEAT", 0) + crop_counts.get("WHEAT", 0)
            want = min(max(0, 8 - have), max(0, n_empty - seeds_held), 8)
            qty = int(min(want, max(0, (cash - operating_reserve - 500) // 10)))
            if qty > 0:
                orders.append(["BUY_SEED", "WHEAT", qty])
                cash -= qty * 10
                seeds_held += qty

    # Land comes after seeds, but before labor. It is a multiplier only when
    # production cash has been protected.
    if land_ready and len(orders) < 10:
        orders.append(["BUY_LAND"])
        cash -= land_cost
        n_extra += 1

    # Hire gradually, with a hard per-day queue budget. This reaches 12 hands
    # quickly while leaving room for BUY_PRODUCT and BUY_ANIMAL.
    if hour <= 1 and len(orders) < 10:
        workload = n_plants + n_animals * 2.5 + len(structs) + min(n_empty, 24)
        target = _hire_target(day, workload, n_hands)
        hire_budget = 2 if day == 0 else (3 if day <= 2 else 5)
        while (n_hands < target and hires_today < target
               and hires_today < n_hands + hire_budget and len(orders) < 10):
            cost = fib(hires_today)
            if cost > max(40, cash * 0.08):
                break
            orders.append(["HIRE"])
            cash -= cost
            hires_today += 1
            n_hands += 1

    # Feed is mandatory. Buy enough for the next several days, but keep shed
    # room and cash for livestock. The old version bought feed after expansion
    # and frequently ran out of money.
    if n_animals > 0 and len(orders) < 10:
        want = min(max(n_animals * 4, 8), 55) - wheat_have
        want = min(want, max(0, shed_room - 10))
        if want > 0 and cash > 250:
            px = price_at("WHEAT", minv.get("WHEAT", I0) - 1)
            qty = int(min(want, max(0, (cash - 250) * 0.4 / max(1, px))))
            if qty > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", qty])
                cash -= qty * px

    # Buy livestock only after empty structures exist. Cows are first, sheep
    # second, and geese only after the profitable pasture lane is supplied.
    empty_pasture = sum(1 for s in structs if s[2].get("kind") == "PASTURE")
    empty_coop = sum(1 for s in structs if s[2].get("kind") == "COOP")
    held_animals = sum(shed.get(a, 0) for a in ANIMALS)
    room = min(5, shed_room - 2)
    if room > 0 and len(orders) < 10:
        wish = []
        need_p = max(0, empty_pasture - held_animals)
        if need_p and days_left >= 11 and counts["COW"] < TGT_COW:
            wish.append(("COW", min(need_p, TGT_COW - counts["COW"], 5)))
        elif need_p and days_left >= 9 and counts["SHEEP"] < TGT_SHEEP:
            wish.append(("SHEEP", min(need_p, TGT_SHEEP - counts["SHEEP"], 5)))
        if empty_coop and days_left >= 7 and counts["COW"] >= 3:
            wish.append(("GOOSE", min(empty_coop, 3)))
        for name, n in wish:
            if len(orders) >= 10 or room <= 0:
                break
            cost = ANIMALS[name]["cost"]
            n = int(min(n, room, max(0, (cash - 500) // cost)))
            if n > 0:
                orders.append(["BUY_ANIMAL", name, n])
                cash -= n * cost
                room -= n

    # Fertilizer only after actual premium crops and animals are funded.
    if (len(orders) < 10 and cash > 1800 and days_left > 6
            and premium > 0 and shed.get("FERTILIZER", 0) < 4
            and shed_room > 10):
        orders.append(["BUY_PRODUCT", "FERTILIZER", 2])

    return orders[:10]
