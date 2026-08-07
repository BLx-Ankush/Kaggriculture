"""Engine constants and the exact market price model.

Everything here is mirrored from kaggle_environments/envs/kaggriculture so the
agent can price its own decisions instead of guessing.
"""

import math

CROPS = {
    "WHEAT":      {"seed": 10,  "fy": 2,  "myd": 4,  "iv": 0, "max": 6, "ongoing": False},
    "CARROT":     {"seed": 20,  "fy": 2,  "myd": 3,  "iv": 0, "max": 4, "ongoing": False},
    "TOMATO":     {"seed": 50,  "fy": 8,  "myd": 8,  "iv": 1, "max": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "fy": 10, "myd": 10, "iv": 2, "max": 4, "ongoing": True},
    "MELON":      {"seed": 80,  "fy": 10, "myd": 12, "iv": 0, "max": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "struct": "COOP",    "fy": 4, "iv": 1, "held": 4, "prod": "EGG"},
    "COW":   {"cost": 400, "struct": "PASTURE", "fy": 8, "iv": 2, "held": 6, "prod": "MILK"},
    "SHEEP": {"cost": 500, "struct": "PASTURE", "fy": 6, "iv": 3, "held": 6, "prod": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER"]

I0 = 10000
MP = {
    "WHEAT":      {"base": 25,  "T": 400, "bf": "sqrt",   "bt": 0.80, "af": "log",    "at": 0.20},
    "CARROT":     {"base": 35,  "T": 450, "bf": "log",    "bt": 0.20, "af": "sqrt",   "at": 0.70},
    "TOMATO":     {"base": 60,  "T": 200, "bf": "linear", "bt": 0.40, "af": "sqrt",   "at": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "bf": "sqrt",   "bt": 0.70, "af": "linear", "at": 1.60},
    "MELON":      {"base": 250, "T": 300, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.60},
    "EGG":        {"base": 50,  "T": 332, "bf": "linear", "bt": 0.40, "af": "log",    "at": 0.20},
    "MILK":       {"base": 160, "T": 122, "bf": "sqrt",   "bt": 0.60, "af": "linear", "at": 1.60},
    "WOOL":       {"base": 200, "T": 105, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "bf": "linear", "bt": 0.40, "af": "linear", "at": 0.40},
}

LAND_PRICES = [1000, 2000, 4000]
BOARD = 10
HALF = 5
TPD = 24
DAYS = 30
SHED_TILES = ((4, 4), (5, 4), (4, 5), (5, 5))
SHED_CAP = 100

# Build targets. Cows and sheep are capped by how much milk and wool the
# market absorbs before the price collapses; geese are the overflow sink
# because the egg glut curve is logarithmic and barely moves.
TGT_COW = 14
TGT_SHEEP = 12
TGT_MELON = 18
TGT_STRAW = 8
TGT_GOOSE = 26


def _shape(fn, x):
    if x < 0.0:
        x = 0.0
    if fn == "linear":
        return x
    if fn == "sq":
        return x * x
    if fn == "sqrt":
        return math.sqrt(x)
    if fn == "log":
        return math.log(1.0 + x)
    if fn == "log10":
        return math.log10(1.0 + x)
    return x


_AMP = {}
for _it, _p in MP.items():
    _AMP[_it] = (_p["bt"] * _p["base"] / _shape(_p["bf"], _p["T"]),
                 _p["at"] * _p["base"] / _shape(_p["af"], _p["T"]))


def price_at(item, inv):
    """Exact replica of the engine's market_price(). Lets us compute the
    marginal revenue of the Nth unit before we commit to selling it."""
    p = MP.get(item)
    if p is None:
        return 1
    lo, hi = _AMP[item]
    if inv < I0:
        v = p["base"] + lo * _shape(p["bf"], I0 - inv)
    else:
        v = p["base"] - hi * _shape(p["af"], inv - I0)
    v = int(round(v))
    return v if v > 1 else 1


def fib(n):
    """Cost of the n-th farm hand hired today (fib starts 1, 1, 2, 3, 5...)."""
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _g(o, k, d=None):
    if isinstance(o, dict):
        return o.get(k, d)
    return getattr(o, k, d)


def _dd(o):
    if isinstance(o, dict):
        return o
    if o is None:
        return {}
    try:
        return dict(o)
    except Exception:
        return {}


def quad(x, y):
    return ("N" if y < HALF else "S") + ("W" if x < HALF else "E")


def mdist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def shed_dist(p):
    return min(mdist(p, s) for s in SHED_TILES)


def nearest_shed(p):
    best = SHED_TILES[0]
    bd = 99
    for s in SHED_TILES:
        d = mdist(p, s)
        if d < bd:
            bd = d
            best = s
    return best


def step_to(pos, tgt):
    """One move toward tgt, longer axis first so units fan out."""
    dx = tgt[0] - pos[0]
    dy = tgt[1] - pos[1]
    if abs(dx) >= abs(dy):
        if dx > 0:
            return ["EAST"]
        if dx < 0:
            return ["WEST"]
    if dy > 0:
        return ["SOUTH"]
    if dy < 0:
        return ["NORTH"]
    return ["PASS"]


# Cross-turn memory. Module scope, keyed by player so self-play stays sane.
_MEM = {}


def mem(player, day, hour):
    m = _MEM.get(player)
    if m is None or (day == 0 and hour == 0 and m.get("turns", 0) > 3):
        m = {"turns": 0, "prev_inv": {}}
        _MEM[player] = m
    m["turns"] = m.get("turns", 0) + 1
    return m
