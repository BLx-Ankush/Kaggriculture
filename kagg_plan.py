"""Market valuation and the route-derived production blueprint."""
from kagg_core import ANIMALS,CROPS,I0,MP,PRODUCTS,TGT_COW,TGT_GOOSE,TGT_MELON,TGT_SHEEP,TGT_STRAW,_g,price_at,shed_dist

def crop_window(crop):
    c=CROPS[crop]; return (c["myd"]+1)//2,c["myd"]
def crop_remaining_value(tile,crop,day,prices,days_left):
    c=CROPS[crop]; px=prices.get(crop,MP[crop]["base"]); age=day-(_g(tile,"planted_day",day) or day); held=_g(tile,"yield_units",0) or 0
    if c["ongoing"]:
        iv=max(1,c["iv"]); done=((age-c["fy"])//iv+1) if age>=c["fy"] else 0; rem=max(0,min(c["max"]-done,(days_left-1)//iv)); return (held+rem)*px
    ws,we=crop_window(crop); future=max(0,min(we,age+days_left-1)-max(ws-1,age)); return (held+future)*px
def animal_rate(name):
    a=ANIMALS[name]; return min(a["held"],1+a["iv"])/float(a["iv"])
def seed_value(crop,days_left,prices):
    c=CROPS[crop]; px=prices.get(crop,MP[crop]["base"])
    if c["ongoing"]: n=min(c["max"],max(0,(days_left-c["fy"])//max(1,c["iv"])+1))
    else:
        ws,we=crop_window(crop); n=min(c["max"],1+max(0,min(we,days_left-1)-ws+1))
    return max(0,n*px-c["seed"])*.5
def reserve_fraction(day,left):
    if left<=1:return 0.0
    if left<=2:return .30
    if left<=4:return .55
    if left<=7:return .68
    return .92 if day<8 else .80
def plan_sales(shed,minv,prices,day,days_left,wheat_reserve,fert_reserve,pressure):
    orders=[]; freed=0; floor_frac=reserve_fraction(day,days_left)
    for item in sorted([p for p in PRODUCTS if shed.get(p,0)>0],key=lambda p:-prices.get(p,MP[p]["base"])):
        qty=shed.get(item,0)-(wheat_reserve if item=="WHEAT" else fert_reserve if item=="FERTILIZER" else 0)
        if qty<=0:continue
        inv=minv.get(item,I0); n=0; floor=MP[item]["base"]*floor_frac
        while n<qty and price_at(item,inv)>=floor:
            n+=1
            if price_at(item,inv)>1:inv+=1
        if n<qty:n+=min(qty-n,max(0,pressure-freed))
        if n:orders.append(["SELL",item,n]);freed+=n
    return orders
def detect_dumping(m,minv):
    prev=m.get("prev_inv") or {}; hot={p for p in PRODUCTS if p in prev and minv.get(p,I0)>prev[p]+2}; m["prev_inv"]=dict(minv); return hot
def blueprint(empties,counts,crop_counts,days_left,money,structs,seeds):
    out={}; ordered=sorted(empties,key=lambda p:(shed_dist(p),p[1],p[0])); pending_p=sum(1 for _,_,t in structs if t.get("kind")=="PASTURE"); pending_c=sum(1 for _,_,t in structs if t.get("kind")=="COOP")
    # Reproduce route footprint: 14 pastures, no goose lane, then premium crops.
    want_p=max(0,min(14-pending_p,(TGT_COW-counts.get("COW",0))+(TGT_SHEEP-counts.get("SHEEP",0)))) if days_left>=9 else 0
    want_c=max(0,min(0-pending_c,0))
    want_m=max(0,TGT_MELON-crop_counts.get("MELON",0)) if days_left>=12 else 0
    want_s=max(0,TGT_STRAW-crop_counts.get("STRAWBERRY",0)) if days_left>=13 else 0
    for pos in ordered:
        if want_p:out[pos]="PASTURE";want_p-=1
        elif want_m and seeds.get("MELON",0)>0:out[pos]="MELON";want_m-=1
        elif want_s and seeds.get("STRAWBERRY",0)>0:out[pos]="STRAWBERRY";want_s-=1
        elif days_left>=12 and seeds.get("MELON",0)>0:out[pos]="MELON"
        elif days_left>=3 and seeds.get("WHEAT",0)>0:out[pos]="WHEAT"
    return out
