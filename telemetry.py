"""Runtime telemetry for local benchmarks.

The Kaggle contract does not expose a logger, so this module stays optional and
stdlib-only. It records emitted actions and exceptions in memory; local trace
scripts can print `snapshot()` after a game. It never changes policy behavior.
"""
from collections import Counter

_STATE = {}


def _get(player):
    if player not in _STATE:
        _STATE[player] = {
            "calls": 0,
            "exceptions": 0,
            "first_error": None,
            "emitted": Counter(),
            "invalid_shape": 0,
        }
    return _STATE[player]


def reset(player=None):
    if player is None:
        _STATE.clear()
    else:
        _STATE.pop(player, None)


def call(player):
    _get(player)["calls"] += 1


def action(player, payload):
    s = _get(player)
    if not isinstance(payload, dict):
        s["invalid_shape"] += 1
        return
    for key in ("farmer", "hands", "market"):
        value = payload.get(key)
        if key == "farmer" and (not isinstance(value, list) or not value):
            s["invalid_shape"] += 1
        elif key != "farmer" and not isinstance(value, list):
            s["invalid_shape"] += 1
    farmer = payload.get("farmer", [])
    if isinstance(farmer, list) and farmer:
        s["emitted"][str(farmer[0])] += 1
    for hand in payload.get("hands", []) if isinstance(payload.get("hands"), list) else []:
        if isinstance(hand, list) and hand:
            s["emitted"][str(hand[0])] += 1
    for order in payload.get("market", []) if isinstance(payload.get("market"), list) else []:
        if isinstance(order, list) and order:
            s["emitted"][str(order[0])] += 1


def error(player, exc, day=None, hour=None):
    s = _get(player)
    s["exceptions"] += 1
    if s["first_error"] is None:
        s["first_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "day": day,
            "hour": hour,
        }


def snapshot():
    out = {}
    for player, s in _STATE.items():
        out[player] = {
            "calls": s["calls"],
            "exceptions": s["exceptions"],
            "first_error": s["first_error"],
            "invalid_shape": s["invalid_shape"],
            "emitted": dict(s["emitted"]),
        }
    return out
