"""Capital-first market scheduler calibrated from the attached v22 trace."""
from kagg_core import ANIMALS,CROPS,I0,LAND_PRICES,MP,TGT_COW,TGT_MELON,TGT_SHEEP,TGT_STRAW,fib,price_at
from kagg_plan import plan_sales

def _target_hands(day,n):
    return max(n,min(14,{0:1,1:2,2:4,3:6,4:8,5:9,6:10,7:11,8:12,10:13}.get(day,14)))
def build_orders(money,shed,seeds,prices,minv,day,hour,days_left,endgame,unlocked,hires_today,n_hands,counts,crop_counts,structs,n_animals,wheat_have,n_empty,shed_room,hot,n_plants):
    orders=[]; cash=float(money)
    # Keep the route's staged sale behavior: wheat is the cash/space valve;
    # premium products are sold only when the marginal price clears reserve.
    sales=plan_sales(shed,minv,prices,day,days_left,min(60,n_animals*2),6 if crop_counts.get("STRAWBERRY",0)>0 else 0,max(0,30-shed_room))
    if hot:sales.sort(key=lambda o:(o[1] not in hot,-prices.get(o[1],0)))
    for o in sales[:4]:orders.append(o);cash+=o[2]*prices.get(o[1],MP[o[1]]["base"])*.65
    if endgame:return orders[:10]
    # Opening buys: do not let hires consume the entire market queue.
    reserve=900 if day<=4 else 650
    held_seeds=sum(v for v in seeds.values() if v>0)
    def buy_seed(crop,want):
        nonlocal cash,held_seeds
        if len(orders)>=10 or want<=0:return
        qty=int(min(want,max(0,(cash-reserve)//CROPS[crop]["seed"]),12))
        if qty>0:orders.append(["BUY_SEED",crop,qty]);cash-=qty*CROPS[crop]["seed"];held_seeds+=qty
    # Small melon batch, then the high-demand strawberry lane.
    if days_left>=12:buy_seed("MELON",max(0,TGT_MELON-crop_counts.get("MELON",0)-seeds.get("MELON",0)))
    if days_left>=13:buy_seed("STRAWBERRY",max(0,TGT_STRAW-crop_counts.get("STRAWBERRY",0)-seeds.get("STRAWBERRY",0)))
    # Wheat is grown early only as a small tile lane; feed is bought later.
    if days_left>=3:buy_seed("WHEAT",max(0,7-crop_counts.get("WHEAT",0)-seeds.get("WHEAT",0)))
    # Progressive land: third quadrant is the route target; preserve cash first.
    extra=len(unlocked)-1
    if extra<len(LAND_PRICES) and day>=3 and days_left>7 and cash>=LAND_PRICES[extra]+reserve:
        orders.append(["BUY_LAND"]);cash-=LAND_PRICES[extra]
    # Hire progressively. Never spend more than 5 slots on labor in opening.
    if hour<=1:
        target=_target_hands(day,n_hands); cap=2 if day==0 else 3 if day<=4 else 5
        while n_hands<target and cap>0 and len(orders)<10:
            c=fib(hires_today)
            if c>cash-reserve:break
            orders.append(["HIRE"]);cash-=c;hires_today+=1;n_hands+=1;cap-=1
    # Feed reserve before livestock purchases.
    if n_animals and len(orders)<10:
        want=max(0,n_animals*4-wheat_have); px=price_at("WHEAT",minv.get("WHEAT",I0)-1); qty=int(min(want,max(0,(cash-reserve)*.4/max(1,px)),max(0,shed_room-8)))
        if qty>0:orders.append(["BUY_PRODUCT","WHEAT",qty]);cash-=qty*px
    # Fill empty pastures in cow-first then sheep order.
    empty_p=sum(1 for _,_,t in structs if t.get("kind")=="PASTURE"); held=sum(shed.get(a,0) for a in ANIMALS)
    if empty_p and len(orders)<10:
        if counts.get("COW",0)<TGT_COW:name="COW";want=min(empty_p,TGT_COW-counts.get("COW",0))
        else:name="SHEEP";want=min(empty_p,TGT_SHEEP-counts.get("SHEEP",0))
        qty=int(min(want,max(0,(cash-reserve)//ANIMALS[name]["cost"]),5))
        if qty>0:orders.append(["BUY_ANIMAL",name,qty]);cash-=qty*ANIMALS[name]["cost"]
    # Fertilizer only for strawberries with enough runway.
    if len(orders)<10 and day<24 and crop_counts.get("STRAWBERRY",0)>0 and cash>1800 and shed_room>10:
        orders.append(["BUY_PRODUCT","FERTILIZER",min(3,max(0,4-shed.get("FERTILIZER",0)))])
    return orders[:10]
