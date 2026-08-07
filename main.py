"""Kaggriculture agent entry point with explicit phases and telemetry."""
from kagg_core import ANIMALS, BOARD, CROPS, DAYS, I0, MP, PRODUCTS, SHED_CAP, TPD, _dd, _g, mdist, mem, nearest_shed, quad, shed_dist, step_to
from kagg_market import build_orders
from kagg_plan import blueprint, detect_dumping
from kagg_tasks import generate
from phases import phase
from telemetry import call, action as record_action, error as record_error, fallback, phase as record_phase
IDLE={"farmer":["PASS"],"hands":[],"market":[]}

def agent(obs):
    player=_g(obs,"player",0); day=_g(obs,"day",0); hour=_g(obs,"hour",0)
    call(player)
    record_phase(player,phase(day))
    try:
        result=_think(obs); record_action(player,result); return result
    except Exception as exc:
        record_error(player,exc,day,hour); fallback(player)
        return dict(IDLE)

def _think(obs):
    player=_g(obs,"player",0); day=_g(obs,"day",0); hour=_g(obs,"hour",0)
    farms=_g(obs,"farms",[]) or []; market=_g(obs,"market",{}) or {}; private=_g(obs,"private",{}) or {}
    if player>=len(farms): raise ValueError("missing player farm")
    farm=farms[player]; money=_g(farm,"money",0) or 0; tiles=_g(farm,"tiles",[]) or []
    unlocked=set(_g(farm,"unlocked_quadrants",["NW"]) or ["NW"]); hires=_g(farm,"hires_today",0) or 0
    farmer=tuple(_g(farm,"farmer",[4,4])); hands=[tuple(h) for h in (_g(farm,"hands",[]) or [])]
    shed=_dd(_g(private,"shed",{})); seeds=_dd(_g(private,"seeds",{})); invs=_g(private,"inventories",[{}]) or [{}]
    prices=dict(_dd(_g(market,"prices",{}))); minv=dict(_dd(_g(market,"inventory",{})))
    for it in PRODUCTS: prices.setdefault(it,MP[it]["base"]); minv.setdefault(it,I0)
    left=DAYS-day; hours=TPD-hour; endgame=left<=2; hot=detect_dumping(mem(player,day,hour),minv)
    units=[(0,farmer)]+[(i+1,p) for i,p in enumerate(hands)]
    unit_inv={u:dict(_dd(invs[u] if u<len(invs) else {})) for u,_ in units}
    empties=[]; plants=[]; livestock=[]; structs=[]; weeds=[]; counts={"COW":0,"SHEEP":0,"GOOSE":0}; crop_counts={c:0 for c in CROPS}
    for y,row in enumerate(tiles[:BOARD]):
        for x,t in enumerate(row[:BOARD]):
            if quad(x,y) not in unlocked: continue
            if t is None: empties.append((x,y))
            elif isinstance(t,dict):
                k=t.get("kind")
                if k=="PLANT": plants.append((x,y,t)); crop_counts[t.get("crop","WHEAT")]=crop_counts.get(t.get("crop","WHEAT"),0)+1
                elif k=="WEED": weeds.append((x,y))
                elif k in ("COOP","PASTURE"):
                    if "animal" in t: livestock.append((x,y,t)); counts[t.get("animal")] = counts.get(t.get("animal"),0)+1
                    else: structs.append((x,y,t))
    shed_used=sum(v for v in shed.values() if v>0); room=max(0,SHED_CAP-shed_used)
    n_unfed=sum(1 for _,_,t in livestock if not t.get("fed_today",False))
    wheat=shed.get("WHEAT",0)+sum(unit_inv[u].get("WHEAT",0) for u,_ in units)
    on_hand={a:shed.get(a,0)+sum(unit_inv[u].get(a,0) for u,_ in units) for a in ANIMALS}
    plan=blueprint(empties,counts,crop_counts,left,money,structs,seeds)
    tasks=generate(plants,livestock,structs,weeds,plan,seeds,prices,day,hour,left,endgame,on_hand,crop_counts)
    actions={}; free=dict(units); shed_tiles=((4,4),(5,4),(4,5),(5,5))
    for u,pos in units:
        carrying=sum(v for v in unit_inv[u].values() if v>0)
        if carrying>=12 or (endgame and carrying>=5) or (hour>=TPD-3 and carrying>0 and room<carrying):
            actions[u]=["DROP"] if tuple(pos) in shed_tiles else step_to(pos,nearest_shed(pos)); free.pop(u,None)
    fetch=[]
    if n_unfed and shed.get("WHEAT",0)>0: fetch.append(("WHEAT",min(14,n_unfed,shed.get("WHEAT",0))))
    for a in ("COW","SHEEP","GOOSE"):
        if shed.get(a,0)>0:
            slots=sum(1 for s in structs if s[2].get("kind")==ANIMALS[a]["struct"])
            if slots: fetch.append((a,min(shed.get(a,0),slots,3)))
    for u,pos in sorted(free.items(),key=lambda kv:shed_dist(kv[1])):
        if not fetch: break
        item,qty=fetch.pop(0)
        actions[u]=["PICKUP",item,qty] if tuple(pos) in shed_tiles else step_to(pos,nearest_shed(pos)); free.pop(u,None)
    tasks.sort(key=lambda t:-t[0])
    for _,tx,ty,act,req in tasks:
        if not free: break
        dist,u=min(((mdist(pos,(tx,ty)),uid) for uid,pos in free.items() if req is None or unit_inv[uid].get(req,0)>0),default=(999,None))
        if u is None or dist>hours: continue
        pos=free.pop(u); actions[u]=act if dist==0 else step_to(pos,(tx,ty))
    for u,pos in free.items():
        carrying=sum(v for v in unit_inv[u].values() if v>0)
        actions[u]=(["DROP"] if carrying and tuple(pos) in shed_tiles else step_to(pos,nearest_shed(pos))) if carrying else ["PASS"]
    orders=build_orders(money,shed,seeds,prices,minv,day,hour,left,endgame,unlocked,hires,len(hands),counts,crop_counts,structs,len(livestock),wheat,len(empties),room,hot,len(plants))
    return {"farmer":actions.get(0,["PASS"]),"hands":[actions.get(i+1,["PASS"]) for i in range(len(hands))],"market":orders[:10]}
