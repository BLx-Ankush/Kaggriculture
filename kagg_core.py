"""Engine constants and exact market model for Kaggriculture.

Targets are derived from the attached 2904-scoring v22 route's live trace:
12 melons, 7 early wheat, 42 strawberries, 8 cows, 6 sheep, 14 hands, and
only three unlocked quadrants. This is a research starting point, not a claim
that the route is optimal against adaptive opponents.
"""
import math
CROPS={"WHEAT":{"seed":10,"fy":2,"myd":4,"iv":0,"max":6,"ongoing":False},"CARROT":{"seed":20,"fy":2,"myd":3,"iv":0,"max":4,"ongoing":False},"TOMATO":{"seed":50,"fy":8,"myd":8,"iv":1,"max":4,"ongoing":True},"STRAWBERRY":{"seed":100,"fy":10,"myd":10,"iv":2,"max":4,"ongoing":True},"MELON":{"seed":80,"fy":10,"myd":12,"iv":0,"max":6,"ongoing":False}}
ANIMALS={"GOOSE":{"cost":300,"struct":"COOP","fy":4,"iv":1,"held":4,"prod":"EGG"},"COW":{"cost":400,"struct":"PASTURE","fy":8,"iv":2,"held":6,"prod":"MILK"},"SHEEP":{"cost":500,"struct":"PASTURE","fy":6,"iv":3,"held":6,"prod":"WOOL"}}
PRODUCTS=["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]
I0=10000
MP={"WHEAT":{"base":25,"T":400,"bf":"sqrt","bt":.8,"af":"log","at":.2},"CARROT":{"base":35,"T":450,"bf":"log","bt":.2,"af":"sqrt","at":.7},"TOMATO":{"base":60,"T":200,"bf":"linear","bt":.4,"af":"sqrt","at":.6},"STRAWBERRY":{"base":120,"T":100,"bf":"sqrt","bt":.7,"af":"linear","at":1.6},"MELON":{"base":250,"T":300,"bf":"log","bt":.2,"af":"sq","at":3.6},"EGG":{"base":50,"T":332,"bf":"linear","bt":.4,"af":"log","at":.2},"MILK":{"base":160,"T":122,"bf":"sqrt","bt":.6,"af":"linear","at":1.6},"WOOL":{"base":200,"T":105,"bf":"log","bt":.2,"af":"sq","at":3.2},"FERTILIZER":{"base":100,"T":200,"bf":"linear","bt":.4,"af":"linear","at":.4}}
LAND_PRICES=[1000,2000,4000]; BOARD=10; HALF=5; TPD=24; DAYS=30; SHED_TILES=((4,4),(5,4),(4,5),(5,5)); SHED_CAP=100
TGT_COW=8; TGT_SHEEP=6; TGT_MELON=12; TGT_STRAW=42; TGT_GOOSE=0

def _shape(fn,x):
    x=max(0.0,x); return {"linear":x,"sq":x*x,"sqrt":math.sqrt(x),"log":math.log(1+x),"log10":math.log10(1+x)}.get(fn,x)
_AMP={i:(p["bt"]*p["base"]/_shape(p["bf"],p["T"]),p["at"]*p["base"]/_shape(p["af"],p["T"])) for i,p in MP.items()}
def price_at(item,inv):
    p=MP[item]; lo,hi=_AMP[item]; v=p["base"]+(lo*_shape(p["bf"],I0-inv) if inv<I0 else -hi*_shape(p["af"],inv-I0)); return max(1,int(round(v)))
def fib(n):
    a,b=1,1
    for _ in range(n): a,b=b,a+b
    return a
def _g(o,k,d=None): return o.get(k,d) if isinstance(o,dict) else getattr(o,k,d)
def _dd(o):
    if isinstance(o,dict): return o
    if o is None:return {}
    try:return dict(o)
    except Exception:return {}
def quad(x,y): return ("N" if y<HALF else "S")+("W" if x<HALF else "E")
def mdist(a,b): return abs(a[0]-b[0])+abs(a[1]-b[1])
def shed_dist(p): return min(mdist(p,s) for s in SHED_TILES)
def nearest_shed(p): return min(SHED_TILES,key=lambda s:mdist(p,s))
def step_to(pos,tgt):
    dx,dy=tgt[0]-pos[0],tgt[1]-pos[1]
    if abs(dx)>=abs(dy):
        if dx>0:return ["EAST"]
        if dx<0:return ["WEST"]
    if dy>0:return ["SOUTH"]
    if dy<0:return ["NORTH"]
    return ["PASS"]
_MEM={}
def mem(player,day,hour):
    m=_MEM.get(player)
    if m is None or (day==0 and hour==0 and m.get("turns",0)>3):m={"turns":0,"prev_inv":{}};_MEM[player]=m
    m["turns"]+=1; return m
