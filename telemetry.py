"""Optional local telemetry. Never changes agent decisions."""
from collections import Counter
_STATE = {}
def _get(player):
    if player not in _STATE:
        _STATE[player] = {"calls":0,"exceptions":0,"fallbacks":0,"first_error":None,"emitted":Counter(),"invalid_shape":0,"phases":Counter()}
    return _STATE[player]
def reset(player=None):
    _STATE.clear() if player is None else _STATE.pop(player,None)
def call(player): _get(player)["calls"] += 1
def phase(player,name): _get(player)["phases"][name] += 1
def fallback(player): _get(player)["fallbacks"] += 1
def action(player,payload):
    s=_get(player)
    if not isinstance(payload,dict): s["invalid_shape"]+=1; return
    for k in ("farmer","hands","market"):
        v=payload.get(k)
        if k=="farmer" and (not isinstance(v,list) or not v): s["invalid_shape"]+=1
        elif k!="farmer" and not isinstance(v,list): s["invalid_shape"]+=1
    for v in [payload.get("farmer",[])] + (payload.get("hands",[]) if isinstance(payload.get("hands"),list) else []):
        if isinstance(v,list) and v: s["emitted"][str(v[0])] += 1
    for v in payload.get("market",[]) if isinstance(payload.get("market"),list) else []:
        if isinstance(v,list) and v: s["emitted"][str(v[0])] += 1
def error(player,exc,day=None,hour=None):
    s=_get(player); s["exceptions"]+=1
    if s["first_error"] is None: s["first_error"]={"type":type(exc).__name__,"message":str(exc),"day":day,"hour":hour}
def snapshot():
    return {p:{"calls":s["calls"],"exceptions":s["exceptions"],"fallbacks":s["fallbacks"],"first_error":s["first_error"],"invalid_shape":s["invalid_shape"],"emitted":dict(s["emitted"]),"phases":dict(s["phases"])} for p,s in _STATE.items()}
