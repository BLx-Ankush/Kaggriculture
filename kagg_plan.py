"""Valuation, sell timing, and the tile blueprint.

The key economic finding driving this file: the town drains market inventory
every single turn and never puts anything back, so if nobody sells, prices
only go UP. Expected no-sell price path (day 0 -> day 29):

    STRAWBERRY 132 -> 313    MILK 172 -> 341    TOMATO 60 -> 100
    WHEAT       26 ->  50    WOOL 209 -> 250    MELON 260 -> 293

Selling a strawberry on day 3 instead of day 27 costs you 58% of its value.
So we hold behind a reserve price and only release volume when the marginal
unit still clears that reserve.

The other half: glut curves differ wildly per product. Units sellable before
the price halves, across BOTH players combined:

    STRAWBERRY 562   TOMATO 476   MILK 470   WOOL 374   MELON 247
    EGG ~6000   WHEAT ~6000   (log curves, they barely react to oversupply)

Premium goods are capacity-limited. Eggs and wheat are the infinite dump.
"""

from kagg_core import (
    ANIMALS, CROPS, I0, MP, PRODUCTS, TGT_COW, TGT_GOOSE, TGT_MELON,
    TGT_SHEEP, TGT_STRAW, _g, price_at, shed_dist,
)


def crop_window(crop):
    """Inclusive age range where watering adds yield, for a one-time crop."""
    cd = CROPS[crop]
    return (cd["myd"] + 1) // 2, cd["myd"]


def crop_remaining_value(tile, crop, day, prices, days_left):
    """Rough dollars still recoverable from a standing plant."""
    cd = CROPS[crop]
    px = prices.get(crop, MP[crop]["base"])
    age = day - (_g(tile, "planted_day", day) or day)
    held = _g(tile, "yield_units", 0) or 0
    if cd["ongoing"]:
        iv = max(1, cd["iv"])
        done = ((age - cd["fy"]) // iv + 1) if age >= cd["fy"] else 0
        rem = max(0, cd["max"] - done)
        rem = min(rem, max(0, (days_left - 1) // iv))
        return (held + rem) * px
    ws, we = crop_window(crop)
    future = max(0, min(we, age + days_left - 1) - max(ws - 1, age))
    return (held + future) * px


def animal_rate(name):
    """Steady-state units per day with FEED + CARE every day.

    CARE banks +1 for each fed-and-cared day and pays the whole bank out on
    the next scheduled production, so a cow yields 1 + 2 = 3 milk every two
    days (1.50/day), a sheep 1 + 3 = 4 wool every three (1.33/day), and a
    goose 1 + 1 = 2 eggs daily. That bonus is why animals beat every crop.
    """
    a = ANIMALS[name]
    return min(a["held"], 1 + a["iv"]) / float(a["iv"])


def seed_value(crop, days_left, prices):
    cd = CROPS[crop]
    px = prices.get(crop, MP[crop]["base"])
    if cd["ongoing"]:
        n = min(cd["max"], max(0, (days_left - cd["fy"]) // max(1, cd["iv"]) + 1))
    else:
        ws, we = crop_window(crop)
        n = min(cd["max"], 1 + max(0, min(we, days_left - 1) - ws + 1))
    return max(0.0, n * px - cd["seed"]) * 0.5


def reserve_fraction(day, days_left):
    """Fraction of base price below which we refuse to sell."""
    if days_left <= 1:
        return 0.0
    if days_left <= 2:
        return 0.30
    if days_left <= 4:
        return 0.55
    if days_left <= 7:
        return 0.68
    if day < 8:
        return 0.92
    return 0.80


def plan_sales(shed, minv, prices, day, days_left,
               wheat_reserve, fert_reserve, pressure):
    """Walk each product's price curve one unit at a time and stop when the
    marginal unit drops below the reserve.

    `pressure` is how many shed slots we must free this turn. Shed overflow is
    silently discarded at end of day, so losing a harvest is strictly worse
    than selling into a soft price; pressure overrides the reserve.
    """
    frac = reserve_fraction(day, days_left)
    orders = []
    freed = 0
    ranked = sorted([p for p in PRODUCTS if shed.get(p, 0) > 0],
                    key=lambda p: -prices.get(p, MP[p]["base"]))
    for item in ranked:
        qty = shed.get(item, 0)
        if item == "WHEAT":
            qty -= wheat_reserve
        if item == "FERTILIZER":
            qty -= fert_reserve
        if qty <= 0:
            continue
        floor = MP[item]["base"] * frac
        inv = minv.get(item, I0)
        n = 0
        while n < qty:
            px = price_at(item, inv)
            if px < floor:
                break
            n += 1
            if px > 1:
                inv += 1
        if n < qty and pressure > freed:
            n += min(qty - n, pressure - freed)
        if n > 0:
            orders.append(["SELL", item, n])
            freed += n
    return orders


def detect_dumping(m, minv):
    """Market inventory rising means the opponent is selling into the shared
    book. Their volume moves our price, so front-run them on those goods."""
    prev = m.get("prev_inv") or {}
    hot = set()
    for item in PRODUCTS:
        cur = minv.get(item, I0)
        old = prev.get(item)
        if old is not None and cur > old + 2:
            hot.add(item)
    m["prev_inv"] = dict(minv)
    return hot


def blueprint(empties, counts, crop_counts, days_left, money, structs, seeds):
    """Decide what each empty tile becomes.

    Animals need ~2.5 actions per day (feed, care, harvest) versus ~1 for a
    crop, and walking is the real tax on the action budget, so structures go
    on the tiles closest to the shed and crops get pushed outward. We only
    commit to as many structures as we can actually afford to stock.
    """
    out = {}
    if not empties:
        return out
    ordered = sorted(empties, key=lambda p: (shed_dist(p), p[1], p[0]))

    pend_pasture = 0
    pend_coop = 0
    for s in structs:
        kind = s[2].get("kind")
        if kind == "PASTURE":
            pend_pasture += 1
        elif kind == "COOP":
            pend_coop += 1

    afford = int(max(0, money - 300) // 450)

    want_cow = max(0, TGT_COW - counts["COW"]) if days_left >= 11 else 0
    want_sheep = max(0, TGT_SHEEP - counts["SHEEP"]) if days_left >= 9 else 0
    want_pasture = max(0, min(want_cow + want_sheep - pend_pasture, afford + 1, 8))

    want_goose = max(0, TGT_GOOSE - counts["GOOSE"]) if days_left >= 7 else 0
    want_coop = max(0, min(want_goose - pend_coop,
                           max(0, afford - want_pasture) + 1, 8))

    want_melon = max(0, TGT_MELON - crop_counts.get("MELON", 0)) if days_left >= 12 else 0
    want_straw = max(0, TGT_STRAW - crop_counts.get("STRAWBERRY", 0)) if days_left >= 13 else 0

    for pos in ordered:
        if want_pasture > 0:
            out[pos] = "PASTURE"
            want_pasture -= 1
        elif want_coop > 0:
            out[pos] = "COOP"
            want_coop -= 1
        elif want_melon > 0 and seeds.get("MELON", 0) > 0:
            out[pos] = "MELON"
            want_melon -= 1
        elif want_straw > 0 and seeds.get("STRAWBERRY", 0) > 0:
            out[pos] = "STRAWBERRY"
            want_straw -= 1
        elif days_left >= 12 and seeds.get("MELON", 0) > 0:
            out[pos] = "MELON"
        elif days_left >= 3 and seeds.get("WHEAT", 0) > 0:
            out[pos] = "WHEAT"
    return out
