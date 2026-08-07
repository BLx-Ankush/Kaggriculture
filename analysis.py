"""Standalone economics model. Run it: python analysis.py

This is the reasoning behind every constant in the agent. Re-run it after any
rule change so the build targets stay honest.

Three questions it answers:
  1. How much of each product can the market absorb before the price craters?
  2. What does the price do over 30 days if you just... wait?
  3. What is a farm action actually worth on each crop and animal?
"""

import random

from kagg_core import ANIMALS, CROPS, I0, MP, PRODUCTS, fib, price_at

SHOPS = {
    "BAKERY": ["EGG", "WHEAT"],
    "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}


def daily_town_drain(trials=400, seed=0):
    """Expected units the town removes per day. Shops unlock every 3 days in
    random order, so average over many orders."""
    rng = random.Random(seed)
    names = list(SHOPS)
    daily = [dict((p, 0.0) for p in PRODUCTS) for _ in range(30)]
    for _ in range(trials):
        order = names[:]
        rng.shuffle(order)
        live = []
        for d in range(30):
            if d > 0 and d % 3 == 0 and len(live) < len(order):
                live.append(order[len(live)])
            # Town center: 24/12 = 2 ticks a day, 2x after day 10, 4x after 20.
            tc = 2 * (1 if d <= 10 else (2 if d <= 20 else 4))
            for p in PRODUCTS:
                v = 0.0 if p == "FERTILIZER" else float(tc)
                for s in live:
                    if p in SHOPS[s]:
                        # 24/4 = 6 ticks a day, single-product shops pull 2x.
                        v += 12.0 if len(SHOPS[s]) == 1 else 6.0
                daily[d][p] += v / trials
    return daily


def absorption(drain):
    print("\n=== MARKET ABSORPTION (both players share this) ===")
    print("%-12s %7s %8s %9s %9s %8s" % (
        "item", "drain", "p@day29", "n@50%base", "revenue", "avg$"))
    for item in PRODUCTS:
        d = drain[item]
        base = MP[item]["base"]
        inv = I0 - d
        n = tot = 0
        n50 = rev50 = 0
        while n < 6000:
            px = price_at(item, inv)
            if px <= 1:
                break
            tot += px
            n += 1
            inv += 1
            if px >= base * 0.5:
                n50, rev50 = n, tot
        print("%-12s %7.0f %8d %9d %9d %8.0f" % (
            item, d, price_at(item, I0 - d), n50, rev50,
            rev50 / max(1, n50)))


def drift(daily):
    print("\n=== PRICE IF NOBODY SELLS (why dumping early is a mistake) ===")
    cols = [0, 5, 10, 15, 20, 25, 29]
    print("%-12s" % "item" + "".join("%7s" % ("d%d" % d) for d in cols))
    for p in PRODUCTS:
        cum, path = 0.0, []
        for d in range(30):
            cum += daily[d][p]
            path.append(cum)
        print("%-12s" % p + "".join(
            "%7d" % price_at(p, I0 - path[d]) for d in cols))


def roi():
    print("\n=== DOLLARS PER FARM ACTION (the real currency) ===")
    late = {"WHEAT": 50, "CARROT": 42, "TOMATO": 100, "STRAWBERRY": 280,
            "MELON": 290, "EGG": 42, "MILK": 270, "WOOL": 235}
    rows = []
    for name, a in ANIMALS.items():
        # CARE banks +1 per fed-and-cared day, paid out at next production.
        per = min(a["held"], 1 + a["iv"])
        rate = per / float(a["iv"])
        acts = 2.0 + 1.0 / a["iv"]  # feed + care daily, harvest each cycle
        rev = rate * late[a["prod"]]
        rows.append((rev / acts, name, "%.2f %s/day" % (rate, a["prod"]),
                     "$%.0f/day/tile" % rev))
    for name, cd in CROPS.items():
        if cd["ongoing"]:
            units, occ = cd["max"], cd["myd"] + 1
            acts = 1 + occ + cd["max"]
        else:
            ws = (cd["myd"] + 1) // 2
            units = min(cd["max"], 1 + (cd["myd"] - ws + 1))
            occ = cd["myd"] + 1
            acts = 1 + occ + 1
        rev = units * late[name] - cd["seed"]
        rows.append((rev / acts, name, "%d units / %d tile-days" % (units, occ),
                     "$%.0f/tile-day" % (rev / occ)))
    rows.sort(reverse=True)
    for score, name, a, b in rows:
        print("  %-11s $%6.0f per action   %-24s %s" % (name, score, a, b))


def labor():
    print("\n=== LABOR (hire cost is fib(n), it is basically free) ===")
    total = 0
    for h in range(1, 17):
        total += fib(h - 1)
        if h in (3, 6, 8, 10, 12, 14, 16):
            print("  %2d hands  $%6d/day  %4d actions/day  $%7d over 25 days"
                  % (h, total, 24 * (1 + h), total * 25))


if __name__ == "__main__":
    daily = daily_town_drain()
    total = dict((p, sum(daily[d][p] for d in range(30))) for p in PRODUCTS)
    absorption(total)
    drift(daily)
    roi()
    labor()
    print("\nTakeaway: premium goods (strawberry, milk, wool, melon) are")
    print("capacity-limited, eggs and wheat are the infinite dump, animals")
    print("beat every crop per action, and waiting to sell is worth ~2x.")
