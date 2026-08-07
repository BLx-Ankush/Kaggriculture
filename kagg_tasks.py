"""Turns board state into a queue of dollar-valued jobs.

Every candidate action is priced in expected dollars so the scheduler can
compare a watering against a milking against a coop build on one scale. The
scheduler then picks the nearest capable unit, because with 12-14 hands on a
10x10 board, walking is the dominant cost.

Dollars per action spent, from the engine tables:
    COW $162  SHEEP $134  MELON $111  STRAWBERRY $46  GOOSE $28
    WHEAT $27  CARROT $18  TOMATO $18
"""

from kagg_core import ANIMALS, CROPS, MP, TPD
from kagg_plan import animal_rate, crop_remaining_value, crop_window, seed_value


def generate(plants, livestock, structs, weeds, plan, seeds, prices, day,
             hour, days_left, endgame, on_hand, crop_counts):
    """Return [(value, x, y, action, required_inventory_item), ...]."""
    tasks = []
    # Watering and feeding must land before the end-of-day refresh, so the
    # later it gets the more a missed chore is worth.
    late = 1.0 + 2.5 * (hour / float(TPD)) ** 2
    fert_targets = crop_counts.get("STRAWBERRY", 0) + crop_counts.get("MELON", 0)

    for x, y, t in plants:
        crop = t.get("crop", "WHEAT")
        cd = CROPS.get(crop)
        if cd is None:
            continue
        px = prices.get(crop, MP[crop]["base"])
        age = day - (t.get("planted_day", day) or day)
        held = t.get("yield_units", 0) or 0
        rem = crop_remaining_value(t, crop, day, prices, days_left)

        if not t.get("watered_today", False):
            if (t.get("consecutive_unwatered", 0) or 0) >= 1:
                # Two consecutive dry days and this is a weed by morning.
                tasks.append((rem * late + 500.0, x, y, ["WATER"], None))
            else:
                gain = 0.0
                if not cd["ongoing"]:
                    ws, we = crop_window(crop)
                    if ws <= age <= we and held < cd["max"]:
                        fertilized = (t.get("fertilized_until_day", -1) or -1) >= day
                        gain = px * (2.0 if fertilized else 1.0)
                else:
                    sched = (age >= cd["fy"]
                             and (age - cd["fy"]) % max(1, cd["iv"]) == 0)
                    if sched and (t.get("fertilized_until_day", -1) or -1) >= day:
                        gain = px
                keep_alive = rem * 0.25
                tasks.append((max(gain, keep_alive) * late, x, y, ["WATER"], None))

        if held > 0 and age >= cd["fy"]:
            if endgame or (not cd["ongoing"] and age > cd["myd"]):
                # Past max lifespan the tile bleeds one unit every other turn.
                tasks.append((held * px * 1.3, x, y, ["HARVEST"], None))
            elif not cd["ongoing"] and held >= cd["max"]:
                # Otherwise produce is safest banked on the tile: the shed
                # only holds 100 items and overflow is destroyed.
                mult = 0.7 if days_left > 6 else 1.1
                tasks.append((held * px * mult, x, y, ["HARVEST"], None))
            else:
                tasks.append((held * px * 0.35, x, y, ["HARVEST"], None))

        if (crop in ("STRAWBERRY", "MELON") and days_left > 3
                and (t.get("fertilized_until_day", -1) or -1) < day
                and age + 3 >= cd["fy"]):
            tasks.append((px * 1.8, x, y, ["FERTILIZE"], "FERTILIZER"))

    for x, y, t in livestock:
        name = t.get("animal", "GOOSE")
        a = ANIMALS.get(name, ANIMALS["GOOSE"])
        px = prices.get(a["prod"], MP[a["prod"]]["base"])
        rate = animal_rate(name)
        held = t.get("yield_units", 0) or 0

        if not t.get("fed_today", False):
            if (t.get("consecutive_unfed", 0) or 0) >= 1:
                # Second missed day and the animal escapes, unrecoverable.
                val = a["cost"] + rate * px * days_left
            else:
                val = px * rate * 2.0
            tasks.append((val * late, x, y, ["FEED"], "WHEAT"))

        # CARE banks +1 unit onto the next scheduled production. One action,
        # one extra unit of product. On a cow that is worth ~$270.
        if not t.get("cared_today", False):
            tasks.append((px * late * 0.9, x, y, ["CARE"], None))

        if held > 0:
            # max_held caps unharvested product; past that, production is lost.
            overflow = held >= a["held"] - 1
            mult = 1.4 if (overflow or endgame) else 0.4
            tasks.append((held * px * mult, x, y, ["HARVEST"], None))

        if t.get("fertilizer_available", False) and not endgame:
            tasks.append((90.0 if fert_targets > 0 else 45.0,
                          x, y, ["COLLECT_FERTILIZER"], None))

    # Empty structures, for units already carrying the matching livestock.
    for x, y, t in structs:
        kind = t.get("kind")
        for a_name, a in ANIMALS.items():
            if a["struct"] == kind and on_hand.get(a_name, 0) > 0:
                tasks.append((a["cost"] * 2.0, x, y, ["PLACE", a_name], a_name))
                break

    for x, y in weeds:
        tasks.append((40.0 if days_left > 4 else 5.0, x, y, ["DIG"], None))

    for pos, what in plan.items():
        x, y = pos
        if what in ("COOP", "PASTURE"):
            tasks.append((260.0, x, y, ["BUILD_" + what], None))
        elif what in CROPS and seeds.get(what, 0) > 0:
            tasks.append((seed_value(what, days_left, prices),
                          x, y, ["PLANT", what], None))

    return tasks
