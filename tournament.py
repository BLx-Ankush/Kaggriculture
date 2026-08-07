"""
Kaggriculture Tournament Runner
Round-robin tournament with Elo ratings.
Usage: python tournament.py --agents agent.py,starter,random --rounds 50
"""

import argparse
import importlib.util
import math
import os
import sys
import time
from collections import defaultdict

def load_agent_from_file(filepath):
    spec = importlib.util.spec_from_file_location("agent_mod_" + os.path.basename(filepath), filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "agent"):
        return mod.agent
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and "agent" in name.lower():
            return obj
    raise ValueError(f"No agent function found in {filepath}")


def update_elo(ra, rb, result, k=32):
    """Update Elo ratings. result: 1 = A wins, 0 = B wins, 0.5 = draw."""
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    eb = 1 - ea
    ra_new = ra + k * (result - ea)
    rb_new = rb + k * ((1 - result) - eb)
    return ra_new, rb_new


def run_tournament(agents_dict, rounds_per_pair=10, episode_steps=720, seed=42):
    from kaggle_environments import make

    names = list(agents_dict.keys())
    n = len(names)
    ratings = {name: 1500 for name in names}
    stats = {name: {"wins": 0, "losses": 0, "ties": 0, "total_money": 0, "games": 0} for name in names}

    game_num = 0
    for round_idx in range(rounds_per_pair):
        for i in range(n):
            for j in range(i + 1, n):
                a_name, b_name = names[i], names[j]
                a_agent, b_agent = agents_dict[a_name], agents_dict[b_name]

                ep_seed = seed + game_num
                config = {"episodeSteps": episode_steps, "seed": ep_seed}
                env = make("kaggriculture", configuration=config, debug=False)

                try:
                    env.run([a_agent, b_agent])
                    state = env.state
                    a_money = state[0].get("reward", 0) or 0
                    b_money = state[1].get("reward", 0) or 0
                except Exception as e:
                    print(f"  ERROR in {a_name} vs {b_name}: {e}")
                    game_num += 1
                    continue

                if a_money > b_money:
                    result = 1
                    stats[a_name]["wins"] += 1
                    stats[b_name]["losses"] += 1
                elif b_money > a_money:
                    result = 0
                    stats[a_name]["losses"] += 1
                    stats[b_name]["wins"] += 1
                else:
                    result = 0.5
                    stats[a_name]["ties"] += 1
                    stats[b_name]["ties"] += 1

                stats[a_name]["total_money"] += a_money
                stats[b_name]["total_money"] += b_money
                stats[a_name]["games"] += 1
                stats[b_name]["games"] += 1

                ratings[a_name], ratings[b_name] = update_elo(
                    ratings[a_name], ratings[b_name], result
                )

                game_num += 1
                winner = a_name if result == 1 else (b_name if result == 0 else "TIE")
                print(f"  Game {game_num:3d}: {a_name} (${a_money:,.0f}) vs {b_name} (${b_money:,.0f}) -> {winner}")

    # Print final standings
    print(f"\n{'='*70}")
    print(f"TOURNAMENT RESULTS ({game_num} games)")
    print(f"{'='*70}")
    sorted_names = sorted(names, key=lambda n: ratings[n], reverse=True)
    print(f"{'Rank':<5} {'Agent':<20} {'Elo':>6} {'W':>4} {'L':>4} {'T':>4} {'Avg $':>10}")
    print("-" * 70)
    for rank, name in enumerate(sorted_names, 1):
        s = stats[name]
        avg_money = s["total_money"] / max(1, s["games"])
        print(f"{rank:<5} {name:<20} {ratings[name]:>6.0f} {s['wins']:>4} {s['losses']:>4} {s['ties']:>4} ${avg_money:>9,.0f}")
    print(f"{'='*70}")

    return ratings, stats


def main():
    parser = argparse.ArgumentParser(description="Kaggriculture Tournament")
    parser.add_argument("--agents", default="agent.py,starter,random",
                        help="Comma-separated list of agents (file paths or builtins)")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per pair")
    parser.add_argument("--steps", type=int, default=720, help="Episode steps")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    args = parser.parse_args()

    builtins = {"starter", "random", "pass"}
    agents_dict = {}

    for agent_spec in args.agents.split(","):
        agent_spec = agent_spec.strip()
        if agent_spec in builtins:
            agents_dict[agent_spec] = agent_spec
        else:
            path = os.path.join(os.path.dirname(__file__), agent_spec) if not os.path.isabs(agent_spec) else agent_spec
            name = os.path.splitext(os.path.basename(agent_spec))[0]
            agents_dict[name] = load_agent_from_file(path)

    print(f"Tournament: {list(agents_dict.keys())}")
    print(f"Rounds per pair: {args.rounds}")
    print(f"Steps per episode: {args.steps}")
    print("-" * 70)

    run_tournament(agents_dict, args.rounds, args.steps, args.seed)


if __name__ == "__main__":
    main()
