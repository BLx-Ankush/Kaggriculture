"""Trace the exact main.py submission entry point.

Run: python debug_trace.py
"""
import importlib.util
from telemetry import reset, snapshot
reset()
spec=importlib.util.spec_from_file_location("agent_mod","main.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
from kaggle_environments import make
env=make("kaggriculture",configuration={"episodeSteps":720,"seed":42},debug=True)
def traced(obs):
    result=mod.agent(obs)
    p=obs.get("player",0) if isinstance(obs,dict) else getattr(obs,"player",0)
    if p==0:
        d=obs.get("day",0) if isinstance(obs,dict) else getattr(obs,"day",0)
        h=obs.get("hour",0) if isinstance(obs,dict) else getattr(obs,"hour",0)
        if h==0 or (d==0 and h<3):
            farm=(obs.get("farms",[]) if isinstance(obs,dict) else getattr(obs,"farms",[]))[0]
            money=farm.get("money",0) if isinstance(farm,dict) else getattr(farm,"money",0)
            print(f"d{d}h{h:02d} bank=${money:.0f} market={result['market'][:4]}")
    return result
env.run([traced,"starter"])
for i,s in enumerate(env.state): print(f"final player {i}: ${s.get('reward',0):.0f}")
print("telemetry:",snapshot())
