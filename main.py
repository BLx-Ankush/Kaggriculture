"""Kaggriculture agent entry point with benchmark telemetry."""
from kagg_core import (
    ANIMALS, BOARD, CROPS, DAYS, I0, MP, PRODUCTS, SHED_CAP, TPD,
    _dd, _g, mdist, mem, nearest_shed, quad, shed_dist, step_to,
)
from kagg_market import build_orders
from kagg_plan import blueprint, detect_dumping
from kagg_tasks import generate
from telemetry import call, action as record_action, error as record_error

IDLE = {"farmer": ["PASS"], "hands": [], "market": []}


def agent(obs):
    player = _g(obs, "player", 0)
    day = _g(obs, "day", 0)
    hour = _g(obs, "hour", 0)
    call(player)
    try:
        result = _think(obs)
        record_action(player, result)
        return result
    except Exception as exc:
        record_error(player, exc, day, hour)
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
    units = [(0, farmer_pos)] + [(i + 1, tuple(p)) for i, p in enumerate(hands_pos)]
    unit_inv = {uid: dict(_dd(invs[uid] if uid < len(invs) else {})) for uid, _ in units}

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
                        if t.get("animal") in counts:
                            counts[t["animal"]] += 1
                    else:
                        structs.append((x, y, t))

    shed_used = sum(v for v in shed.values() if v > 0)
    shed_room = max(0, SHED_CAP - shed_used)
    n_unfed = sum(1 for _, _, t in livestock if not t.get("fed_today", False))
    wheat_have = shed.get("WHEAT", 0) + sum(unit_inv[u].get("WHEAT", 0) for u, _ in units)
    on_hand = {k: shed.get(k, 0) + sum(unit_inv[u].get(k, 0) for u, _ in units) for k in ANIMALS}
    plan = blueprint(empties, counts, crop_counts, days_left, money, structs, seeds)
    tasks = generate(plants, livestock, structs, weeds, plan, seeds, prices,
                     day, hour, days_left, endgame, on_hand, crop_counts)

    actions = {}
    free = dict(units)
    for uid, pos in units:
        carrying = sum(v for v in unit_inv[uid].values() if v > 0)
        must_dump = carrying >= 12 or (endgame and carrying >= 5)
        if hour >= TPD - 3 and carrying > 0 and shed_room < carrying:
            must_dump = True
        if must_dump:
            actions[uid] = ["DROP"] if tuple(pos) in ((4,4),(5,4),(4,5),(5,5)) else step_to(pos, nearest_shed(pos))
            free.pop(uid, None)

    fetch = []
    if n_unfed > 0 and shed.get("WHEAT", 0) > 0:
        fetch.append(("WHEAT", min(14, n_unfed, shed.get("WHEAT", 0))))
    for name in ("COW", "SHEEP", "GOOSE"):
        if shed.get(name, 0) > 0:
            slots = sum(1 for s in structs if s[2].get("kind") == ANIMALS[name]["struct"])
            if slots:
                fetch.append((name, min(shed.get(name, 0), slots, 3)))
    if crop_counts.get("STRAWBERRY", 0) + crop_counts.get("MELON", 0) > 0 and shed.get("FERTILIZER", 0) > 0 and not endgame:
        fetch.append(("FERTILIZER", min(4, shed.get("FERTILIZER", 0))))
    for uid, pos in sorted(free.items(), key=lambda kv: shed_dist(kv[1])):
        if not fetch or shed_dist(pos) > 6:
            break
        item, qty = fetch.pop(0)
        if tuple(pos) in ((4,4),(5,4),(4,5),(5,5)):
            actions[uid] = ["PICKUP", item, qty]
        else:
            actions[uid] = step_to(pos, nearest_shed(pos))
        free.pop(uid, None)

    tasks.sort(key=lambda t: -t[0])
    for _, tx, ty, act, req in tasks:
        if not free:
            break
        best = min(((mdist(pos, (tx, ty)), uid) for uid, pos in free.items()
                    if req is None or unit_inv[uid].get(req, 0) > 0), default=(999, None))
        dist, uid = best
        if uid is None or dist > hours_left:
            continue
        pos = free.pop(uid)
        actions[uid] = act if dist == 0 else step_to(pos, (tx, ty))

    for uid, pos in free.items():
        carrying = sum(v for v in unit_inv[uid].values() if v > 0)
        actions[uid] = (["DROP"] if carrying and tuple(pos) in ((4,4),(5,4),(4,5),(5,5)) else step_to(pos, nearest_shed(pos))) if carrying else ["PASS"]

    orders = build_orders(money, shed, seeds, prices, minv, day, hour, days_left,
                          endgame, unlocked, hires_today, len(hands_pos), counts,
                          crop_counts, structs, len(livestock), wheat_have,
                          len(empties), shed_room, hot, len(plants))
    return {"farmer": actions.get(0, ["PASS"]),
            "hands": [actions.get(i + 1, ["PASS"]) for i in range(len(hands_pos))],
            "market": orders[:10]}
