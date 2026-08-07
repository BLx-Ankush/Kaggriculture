"""Debug script to trace agent behavior turn by turn."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("agent_mod", "d:/Kaggriculture/agent.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from kaggle_environments import make

env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 42}, debug=True)

# Run with tracing
def traced_agent(obs):
    result = mod.agent(obs)
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    if player == 0:
        day = obs.get("day", 0) if isinstance(obs, dict) else getattr(obs, "day", 0)
        hour = obs.get("hour", 0) if isinstance(obs, dict) else getattr(obs, "hour", 0)
        step = day * 24 + hour
        farms = obs.get("farms", []) if isinstance(obs, dict) else getattr(obs, "farms", [])
        if farms:
            farm = farms[0]
            money = farm.get("money", 0) if isinstance(farm, dict) else getattr(farm, "money", 0)
            private = obs.get("private", {}) if isinstance(obs, dict) else getattr(obs, "private", {})
            if isinstance(private, dict):
                shed = private.get("shed", {})
                seeds = private.get("seeds", {})
            else:
                shed = getattr(private, "shed", {})
                seeds = getattr(private, "seeds", {})
            
            if step <= 48 or step % 24 == 0:  # First 2 days + start of each day
                print(f"Step {step:3d} (d{day}h{hour:02d}): ${money:.0f} | "
                      f"farmer={result['farmer']} | market={result['market'][:3]} | "
                      f"seeds={dict(seeds) if seeds else {{}}} | shed_items={sum(v for v in (dict(shed).values() if shed else []))}")
    return result

env.run([traced_agent, "starter"])

# Final state
state = env.state
for i in range(2):
    s = state[i]
    money = s.get("reward", 0)
    print(f"\nFinal Player {i}: ${money:.0f}")
