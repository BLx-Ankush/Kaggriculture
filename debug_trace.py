"""Trace one episode and print policy telemetry.

Run from the repository after installing kaggle-environments:
    python debug_trace.py
"""
import importlib.util
from telemetry import snapshot, reset

reset()
spec = importlib.util.spec_from_file_location("agent_mod", "main.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from kaggle_environments import make

env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 42}, debug=True)

def traced_agent(obs):
    result = mod.agent(obs)
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    if player == 0:
        day = obs.get("day", 0) if isinstance(obs, dict) else getattr(obs, "day", 0)
        hour = obs.get("hour", 0) if isinstance(obs, dict) else getattr(obs, "hour", 0)
        if hour == 0 or day == 0 and hour < 3:
            farm = (obs.get("farms", []) if isinstance(obs, dict) else getattr(obs, "farms", []))[0]
            money = farm.get("money", 0) if isinstance(farm, dict) else getattr(farm, "money", 0)
            print(f"d{day}h{hour:02d}: bank=${money:.0f}, market={result['market'][:4]}, farmer={result['farmer']}")
    return result

env.run([traced_agent, "starter"])
for i, s in enumerate(env.state):
    print(f"final player {i}: ${s.get('reward', 0):.0f}")
print("telemetry:", snapshot())
