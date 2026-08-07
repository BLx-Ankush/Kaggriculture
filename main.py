"""Kaggriculture agent - "Dairy Cartel" v4.

Kaggle looks for main.py at the root of the submission with an `agent`
function, so this is the entry point. Submit the whole thing with:

    tar -czf submission.tar.gz main.py kagg_core.py kagg_plan.py \\
        kagg_market.py kagg_tasks.py
    kaggle competitions submit kaggriculture -f submission.tar.gz -m "v4"

What changed from the crop-only v3, ranked by expected value:

  1. LABOR. v3 capped at 3 farm hands behind a `cost <= 5` gate: 96 actions a
     day. Hire cost is fib(n), so 12 hands is $376/day and 14 is $986/day
     against a farm earning six figures. We scale to 12-14.

  2. ANIMALS. v3 had none. CARE banks +1 yield per fed-and-cared day and pays
     the bank out on the next production, making a cow 1.5 milk/day at ~$162
     per action spent. The best crop, melon, is $111. Wheat is $27.

  3. SELL TIMING. v3 dumped everything at base price. The town drains market
     inventory every turn and never restocks, so prices climb all season
     (strawberry $132 -> $313, milk $172 -> $341). We hold behind a reserve
     price and liquidate on a ramp over the final days.

See kagg_plan.py and kagg_market.py for the numbers behind each decision.
"""

from kagg_core import (
    ANIMALS, BOARD, CROPS, DAYS, I0, MP, PRODUCTS, SHED_CAP, SHED_TILES, TPD,
    _dd, _g, mdist, mem, nearest_shed, quad, shed_dist, step_to,
)
from kagg_market import build_orders
from kagg_plan import blueprint, detect_dumping
from kagg_tasks import generate

IDLE = {"farmer": ["PASS"], "hands": [], "market": []}


def agent(obs):
    try:
        return _think(obs)
    except Exception:
        # Never crash out of an episode. A passing turn costs one action; an
        # exception costs the whole game.
        return dict(IDLE)


def _think(obs):
    player = _g(obs, "player", 0)
    day = _g(obs, "day", 0)
    hour = _g(obs, "hour", 0)
    farms = _g(obs, "farms", []) or []
    market = _g(obs, "market", {}) or {}
    private = _g(obs, "private", {}) or {}
    if player >= len(farms):
        return dict(IDLE)

    m = mem(player, day, hour)
    farm = farms[player]
    money = _g(farm, "money", 0) or 0
    tiles = _g(farm, "tiles", []) or []
    unlocked = set(_g(farm, "unlocked_quadrants", ["NW"]) or ["NW"])
    hires_today = _g(farm, "hires_today", 0) or 0
    farmer_pos = tuple(_g(farm, "farmer", [4, 4]))
    hands_pos = [tuple(h) for h in (_g(farm, "hands", []) or [])]

    shed = _dd(_g(private, "shed", {}))
    seeds = _dd(_g(private, "seeds", {}))
    invs = _g(private, "inventories", [{}]) or [{}]

    prices = dict(_dd(_g(market, "prices", {})))
    minv = dict(_dd(_g(market, "inventory", {})))
    for it in PRODUCTS:
        prices.setdefault(it, MP[it]["base"])
        minv.setdefault(it, I0)

    days_left = DAYS - day
    hours_left = TPD - hour
    endgame = days_left <= 2
    hot = detect_dumping(m, minv)

    units = [(0, farmer_pos)]
    for i, p in enumerate(hands_pos):
        units.append((i + 1, p))
    unit_inv = {}
    for uid, _p in units:
        unit_inv[uid] = dict(_dd(invs[uid] if uid < len(invs) else {}))

    # ---- scan the board -------------------------------------------------
    empties, plants, livestock, structs, weeds = [], [], [], [], []
    counts = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    crop_counts = dict((c, 0) for c in CROPS)
    for y in range(min(BOARD, len(tiles))):
        row = tiles[y]
        for x in range(min(BOARD, len(row))):
            if quad(x, y) not in unlocked:
                continue
            t = row[x]
            if t is None:
                empties.append((x, y))
            elif isinstance(t, dict):
                kind = t.get("kind")
                if kind == "PLANT":
                    plants.append((x, y, t))
                    c = t.get("crop", "WHEAT")
                    crop_counts[c] = crop_counts.get(c, 0) + 1
                elif kind == "WEED":
                    weeds.append((x, y))
                elif kind in ("COOP", "PASTURE"):
                    if "animal" in t:
                        livestock.append((x, y, t))
                        a = t.get("animal")
                        if a in counts:
                            counts[a] += 1
                    else:
                        structs.append((x, y, t))

    shed_used = sum(v for v in shed.values() if v > 0)
    shed_room = max(0, SHED_CAP - shed_used)
    n_unfed = sum(1 for _x, _y, t in livestock if not t.get("fed_today", False))
    wheat_have = shed.get("WHEAT", 0) + sum(
        unit_inv[u].get("WHEAT", 0) for u, _p in units)

    on_hand = {}
    for k in ANIMALS:
        on_hand[k] = shed.get(k, 0) + sum(
            unit_inv[u].get(k, 0) for u, _p in units)

    plan = blueprint(empties, counts, crop_counts, days_left, money,
                     structs, seeds)
    tasks = generate(plants, livestock, structs, weeds, plan, seeds, prices,
                     day, hour, days_left, endgame, on_hand, crop_counts)

    # ---- logistics pre-pass ---------------------------------------------
    # Units full of produce head for the shed; units that need wheat, animals
    # or fertilizer to do their jobs go fetch it. Everything the shed holds is
    # capped at 100 items and overflow is destroyed at end of day.
    actions = {}
    free = dict(units)

    for uid, pos in units:
        carrying = sum(v for v in unit_inv[uid].values() if v > 0)
        must_dump = (carrying >= 12
                     or (endgame and carrying >= 5)
                     or (hour >= TPD - 3 and carrying > shed_room > 0))
        if not must_dump:
            continue
        actions[uid] = (["DROP"] if tuple(pos) in SHED_TILES
                        else step_to(pos, nearest_shed(pos)))
        free.pop(uid, None)

    fert_targets = crop_counts.get("STRAWBERRY", 0) + crop_counts.get("MELON", 0)
    fetch = []
    if n_unfed > 0 and shed.get("WHEAT", 0) > 0:
        fetch.append(("WHEAT", min(14, n_unfed, shed.get("WHEAT", 0))))
    for a_name in ("COW", "SHEEP", "GOOSE"):
        in_shed = shed.get(a_name, 0)
        if in_shed <= 0:
            continue
        slots = sum(1 for s in structs
                    if s[2].get("kind") == ANIMALS[a_name]["struct"])
        if slots > 0:
            fetch.append((a_name, min(in_shed, slots, 3)))
    if fert_targets > 0 and shed.get("FERTILIZER", 0) > 0 and not endgame:
        fetch.append(("FERTILIZER", min(4, shed.get("FERTILIZER", 0))))

    for uid, pos in sorted(free.items(), key=lambda kv: shed_dist(kv[1])):
        if not fetch:
            break
        if shed_dist(pos) > 6:
            continue
        item, qty = fetch[0]
        if unit_inv[uid].get(item, 0) > 0:
            fetch.pop(0)
            continue
        if tuple(pos) in SHED_TILES:
            actions[uid] = ["PICKUP", item, qty]
        else:
            actions[uid] = step_to(pos, nearest_shed(pos))
        unit_inv[uid][item] = unit_inv[uid].get(item, 0) + qty
        fetch.pop(0)
        free.pop(uid, None)

    # ---- assign the rest, richest job first, nearest capable unit --------
    tasks.sort(key=lambda t: -t[0])
    for _val, tx, ty, act, req in tasks:
        if not free:
            break
        best_uid, best_d = None, 999
        for uid, pos in free.items():
            if req is not None and unit_inv[uid].get(req, 0) <= 0:
                continue
            d = mdist(pos, (tx, ty))
            if d > hours_left:
                continue  # cannot arrive before the day ends
            if d < best_d:
                best_d, best_uid = d, uid
        if best_uid is None:
            continue
        pos = free.pop(best_uid)
        if best_d == 0:
            actions[best_uid] = act
            if req is not None:
                unit_inv[best_uid][req] = unit_inv[best_uid].get(req, 0) - 1
            if act[0] == "PLANT":
                seeds[act[1]] = seeds.get(act[1], 0) - 1
        else:
            actions[best_uid] = step_to(pos, (tx, ty))

    # Idle units drift back to the shed so tomorrow starts well positioned.
    for uid, pos in free.items():
        carrying = sum(v for v in unit_inv[uid].values() if v > 0)
        if carrying > 0:
            actions[uid] = (["DROP"] if tuple(pos) in SHED_TILES
                            else step_to(pos, nearest_shed(pos)))
        else:
            actions[uid] = ["PASS"]

    orders = build_orders(
        money, shed, seeds, prices, minv, day, hour, days_left, endgame,
        unlocked, hires_today, len(hands_pos), counts, crop_counts, structs,
        len(livestock), wheat_have, len(empties), shed_room, hot, len(plants))

    return {
        "farmer": actions.get(0, ["PASS"]),
        "hands": [actions.get(i + 1, ["PASS"]) for i in range(len(hands_pos))],
        "market": orders[:10],
    }
