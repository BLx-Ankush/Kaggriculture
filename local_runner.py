"""
Kaggriculture Local Runner
Run N episodes between two agents and report statistics.
Usage:
    python local_runner.py                        # default: agent.py vs starter
    python local_runner.py --episodes 20 --opponent random
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from collections import defaultdict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_agent_from_file(filepath):
    """Import a .py file and return its `agent` function."""
    spec = importlib.util.spec_from_file_location("agent_mod", filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "agent"):
        return mod.agent
    # fallback: look for any callable named *agent*
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and "agent" in name.lower():
            return obj
    raise ValueError(f"No agent function found in {filepath}")


def run_episodes(agent1, agent2, n_episodes=10, episode_steps=720, debug=False, seed=None):
    """Run N episodes and return list of result dicts."""
    from kaggle_environments import make

    results = []
    for ep in range(n_episodes):
        ep_seed = (seed + ep) if seed is not None else None
        config = {"episodeSteps": episode_steps}
        if ep_seed is not None:
            config["seed"] = ep_seed

        env = make("kaggriculture", configuration=config, debug=debug)

        t0 = time.time()
        try:
            env.run([agent1, agent2])
        except Exception as e:
            print(f"  Episode {ep+1}: ERROR during run â€” {e}")
            traceback.print_exc()
            results.append({
                "episode": ep + 1,
                "error": str(e),
                "p0_money": 0,
                "p1_money": 0,
                "winner": -1,
                "wall_time": time.time() - t0,
            })
            continue
        wall_time = time.time() - t0

        # Extract final state
        final_state = env.state
        p0_money = 0
        p1_money = 0
        p0_status = "UNKNOWN"
        p1_status = "UNKNOWN"

        if final_state and len(final_state) >= 2:
            p0_money = final_state[0].get("reward", 0) or 0
            p1_money = final_state[1].get("reward", 0) or 0
            p0_status = final_state[0].get("status", "UNKNOWN")
            p1_status = final_state[1].get("status", "UNKNOWN")

        if p0_money > p1_money:
            winner = 0
        elif p1_money > p0_money:
            winner = 1
        else:
            winner = -1  # tie

        result = {
            "episode": ep + 1,
            "p0_money": p0_money,
            "p1_money": p1_money,
            "winner": winner,
            "p0_status": p0_status,
            "p1_status": p1_status,
            "wall_time": wall_time,
        }
        results.append(result)

        winner_str = f"P{winner}" if winner >= 0 else "TIE"
        print(f"  Episode {ep+1:3d}: P0=${p0_money:,.0f}  P1=${p1_money:,.0f}  "
              f"Winner={winner_str}  Time={wall_time:.1f}s")

    return results


def summarize(results, agent1_name, agent2_name):
    """Print summary statistics."""
    valid = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    if not valid:
        print("\nNo valid episodes completed.")
        return

    p0_wins = sum(1 for r in valid if r["winner"] == 0)
    p1_wins = sum(1 for r in valid if r["winner"] == 1)
    ties = sum(1 for r in valid if r["winner"] == -1)
    total = len(valid)

    p0_money_avg = sum(r["p0_money"] for r in valid) / total
    p1_money_avg = sum(r["p1_money"] for r in valid) / total
    p0_money_max = max(r["p0_money"] for r in valid)
    p1_money_max = max(r["p1_money"] for r in valid)
    p0_money_min = min(r["p0_money"] for r in valid)
    p1_money_min = min(r["p1_money"] for r in valid)
    avg_time = sum(r["wall_time"] for r in valid) / total

    print(f"\n{'='*60}")
    print(f"RESULTS: {agent1_name} (P0) vs {agent2_name} (P1)")
    print(f"{'='*60}")
    print(f"Episodes:    {total} valid, {len(errors)} errors")
    print(f"Win Rate:    P0={p0_wins}/{total} ({100*p0_wins/total:.1f}%)  "
          f"P1={p1_wins}/{total} ({100*p1_wins/total:.1f}%)  "
          f"Ties={ties}/{total}")
    print(f"P0 Money:    avg=${p0_money_avg:,.0f}  min=${p0_money_min:,.0f}  max=${p0_money_max:,.0f}")
    print(f"P1 Money:    avg=${p1_money_avg:,.0f}  min=${p1_money_min:,.0f}  max=${p1_money_max:,.0f}")
    print(f"Margin:      avg=${p0_money_avg - p1_money_avg:,.0f}")
    print(f"Avg Time:    {avg_time:.1f}s per episode")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Kaggriculture Local Runner")
    parser.add_argument("--agent", default="agent.py", help="Path to agent file (default: agent.py)")
    parser.add_argument("--opponent", default="starter", help="Opponent: 'starter', 'random', 'pass', or path to .py file")
    parser.add_argument("--episodes", type=int, default=10, help="Number of episodes to run")
    parser.add_argument("--steps", type=int, default=720, help="Episode steps (default: 720)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--seed", type=int, default=None, help="Base seed for reproducibility")
    parser.add_argument("--swap", action="store_true", help="Also run with swapped positions")
    args = parser.parse_args()

    # Load agent
    agent_path = os.path.join(os.path.dirname(__file__), args.agent) if not os.path.isabs(args.agent) else args.agent
    print(f"Loading agent from: {agent_path}")
    agent1 = load_agent_from_file(agent_path)
    agent1_name = os.path.basename(args.agent)

    # Load opponent
    builtin_agents = {"starter", "random", "pass"}
    if args.opponent in builtin_agents:
        agent2 = args.opponent
        agent2_name = args.opponent
    else:
        opp_path = os.path.join(os.path.dirname(__file__), args.opponent) if not os.path.isabs(args.opponent) else args.opponent
        agent2 = load_agent_from_file(opp_path)
        agent2_name = os.path.basename(args.opponent)

    print(f"\nRunning {args.episodes} episodes: {agent1_name} (P0) vs {agent2_name} (P1)")
    print(f"Steps per episode: {args.steps}")
    print("-" * 60)

    results = run_episodes(agent1, agent2, args.episodes, args.steps, args.debug, args.seed)
    summarize(results, agent1_name, agent2_name)

    if args.swap:
        print(f"\n\nSWAPPED: {agent2_name} (P0) vs {agent1_name} (P1)")
        print("-" * 60)
        results_swap = run_episodes(agent2, agent1, args.episodes, args.steps, args.debug,
                                     args.seed + 10000 if args.seed else None)
        summarize(results_swap, agent2_name, agent1_name)

        # Combined stats
        total_agent1_wins = sum(1 for r in results if r["winner"] == 0)
        total_agent1_wins += sum(1 for r in results_swap if r["winner"] == 1)
        total_games = len(results) + len(results_swap)
        print(f"\nCOMBINED: {agent1_name} wins {total_agent1_wins}/{total_games} "
              f"({100*total_agent1_wins/total_games:.1f}%)")


if __name__ == "__main__":
    main()
