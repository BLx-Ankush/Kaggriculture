"""Turns board state into a queue of dollar-valued jobs.

This version is deliberately production-first. The previous scheduler valued
future crop revenue too aggressively and could spend scarce unit turns on
fertilizer/blueprint work while milk, wool, or strawberry output sat on tiles.
"""
from kagg_core import ANIMALS, CROPS, MP, TPD
from kagg_plan import animal_rate, crop_remaining_value, crop_window, seed_value


def generate(plants, livestock, structs, weeds, plan, seeds, prices, day,
             hour, days_left, endgame, on_hand, crop_counts):
    tasks=[]
    late=1.0+2.5*(hour/float(TPD))**2
    fert_targets=crop_counts.get("STRAWBERRY",0)+crop_counts.get("MELON",0)
    for x,y,t in plants:
        crop=t.get("crop","WHEAT"); cd=CROPS.get(crop)
        if cd is None: continue
        px=prices.get(crop,MP[crop]["base"])
        age=day-(t.get("planted_day",day) or day)
        held=t.get("yield_units",0) or 0
        rem=crop_remaining_value(t,crop,day,prices,days_left)
        if not t.get("watered_today",False):
            danger=(t.get("consecutive_unwatered",0) or 0)>=1
            gain=px if (not cd["ongoing"] and crop_window(crop)[0]<=age<=crop_window(crop)[1]) else 0
            tasks.append(((rem*late+500 if danger else max(gain,rem*.25)*late),x,y,["WATER"],None))
        if held>0 and age>=cd["fy"]:
            # Ongoing plants have a hard max-held/output schedule. Harvesting
            # available units is always worth more than waiting for a perfect
            # sale: the next production can otherwise be capped/lost.
            if cd["ongoing"]:
                v=held*px*(1.8 if held>=cd["max"]-1 else 1.05)
            elif endgame or age>cd["myd"]:
                v=held*px*1.3
            elif held>=cd["max"]:
                v=held*px*.7
            else:
                v=held*px*.25
            tasks.append((v*late,x,y,["HARVEST"],None))
        if (crop in ("STRAWBERRY","MELON") and days_left>3
                and (t.get("fertilized_until_day",-1) or -1)<day
                and age+3>=cd["fy"]):
            tasks.append((px*1.2,x,y,["FERTILIZE"],"FERTILIZER"))
    for x,y,t in livestock:
        name=t.get("animal","GOOSE"); a=ANIMALS.get(name,ANIMALS["GOOSE"])
        px=prices.get(a["prod"],MP[a["prod"]]["base"]); rate=animal_rate(name)
        held=t.get("yield_units",0) or 0
        if not t.get("fed_today",False):
            danger=(t.get("consecutive_unfed",0) or 0)>=1
            v=(a["cost"]+rate*px*days_left) if danger else px*rate*2
            tasks.append((v*late,x,y,["FEED"],"WHEAT"))
        if not t.get("cared_today",False):
            tasks.append((px*late*1.1,x,y,["CARE"],None))
        if held>0:
            # Prevent max_held saturation and preserve the next production.
            v=held*px*(2.0 if held>=a["held"]-1 else 1.15)
            tasks.append((v*late,x,y,["HARVEST"],None))
        if t.get("fertilizer_available",False) and not endgame:
            tasks.append(((90 if fert_targets else 45),x,y,["COLLECT_FERTILIZER"],None))
    for x,y,t in structs:
        kind=t.get("kind")
        for an,a in ANIMALS.items():
            if a["struct"]==kind and on_hand.get(an,0)>0:
                tasks.append((a["cost"]*2,x,y,["PLACE",an],an)); break
    for x,y in weeds: tasks.append(((40 if days_left>4 else 5),x,y,["DIG"],None))
    for pos,what in plan.items():
        x,y=pos
        if what in ("COOP","PASTURE"): tasks.append((260,x,y,["BUILD_"+what],None))
        elif what in CROPS and seeds.get(what,0)>0:
            tasks.append((seed_value(what,days_left,prices),x,y,["PLANT",what],None))
    return tasks
