"""Measure per-phase search timings from a short self-play run."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))

from cg.game import battle_finish, battle_select, battle_start
from main import agent, read_deck_csv
from pvs_bridge import bridge


PHASE_KEYS = [
    "wall_ms",
    "root_action_ms",
    "belief_ms",
    "search_wall_ms",
    "aggregate_ms",
    "simulator_cpu_ms",
    "import_cpu_ms",
    "json_cpu_ms",
    "action_cpu_ms",
    "evaluation_cpu_ms",
]


def load_deck() -> list[int]:
    deck_path = ROOT / "sample_submission" / "deck.csv"
    if deck_path.exists():
        return [int(x) for x in deck_path.read_text().split() if x.strip()]
    return read_deck_csv()


def summarize(samples: list[dict]) -> dict:
    if not samples:
        return {}
    totals = {key: 0.0 for key in PHASE_KEYS}
    for sample in samples:
        for key in PHASE_KEYS:
            totals[key] += float(sample.get(key, 0.0))
    count = len(samples)
    avg = {key: totals[key] / count for key in PHASE_KEYS}
    avg["samples"] = count
    avg["avg_nodes"] = sum(float(s.get("call_nodes", 0)) for s in samples) / count
    avg["avg_depth"] = sum(float(s.get("depth", 0)) for s in samples) / count
    avg["avg_actions"] = sum(float(s.get("actions", 0)) for s in samples) / count
    profile_cpu = (
        avg["simulator_cpu_ms"]
        + avg.get("import_cpu_ms", avg.get("json_cpu_ms", 0.0))
        + avg["action_cpu_ms"]
        + avg["evaluation_cpu_ms"]
    )
    if profile_cpu > 0:
        import_cpu = avg.get("import_cpu_ms", avg.get("json_cpu_ms", 0.0))
        avg["simulator_pct"] = 100.0 * avg["simulator_cpu_ms"] / profile_cpu
        avg["import_pct"] = 100.0 * import_cpu / profile_cpu
        avg["action_pct"] = 100.0 * avg["action_cpu_ms"] / profile_cpu
        avg["evaluation_pct"] = 100.0 * avg["evaluation_cpu_ms"] / profile_cpu
    return avg


def run(max_turns: int = 40, profile: bool = True, threads: int = 0) -> tuple[list[dict], dict]:
    config = {
        "hypotheses": 6,
        "threads": threads,
        "max_depth": 20,
        "max_ms": 5000,
        "profile": profile,
    }
    os.environ["POKEMON_PVS_CONFIG"] = json.dumps(config, separators=(",", ":"))

    deck = load_deck()
    if not bridge.initialize(deck):
        raise RuntimeError(f"bridge init failed: {bridge.error}")

    obs, start = battle_start(deck, deck)
    if obs is None:
        raise RuntimeError(f"battle start failed: error={start.errorType}")

    samples: list[dict] = []
    turns = 0
    try:
        while turns < max_turns:
            if obs.get("select") is None:
                choice = agent(obs)
                obs = battle_select(choice)
                continue

            context = obs.get("select", {}).get("context", -1)
            choice = agent(obs)
            diag = bridge.diagnostics()
            if context == 0 and diag:
                samples.append(diag)
            obs = battle_select(choice)
            if obs.get("current", {}).get("result", -1) >= 0:
                break
            turns += 1
    finally:
        battle_finish()

    return samples, summarize(samples)


def print_report(samples: list[dict], summary: dict) -> None:
    print(f"profiled main decisions: {len(samples)}")
    if not summary:
        print("no timing samples collected")
        return

    print("\nAverage phase timings (ms):")
    for key in PHASE_KEYS:
        if key in summary:
            print(f"  {key:22s} {summary[key]:8.2f}")

    print("\nSearch stats:")
    print(f"  avg_nodes             {summary.get('avg_nodes', 0):8.1f}")
    print(f"  avg_depth             {summary.get('avg_depth', 0):8.1f}")
    print(f"  avg_actions           {summary.get('avg_actions', 0):8.1f}")
    if samples:
        print(f"  threads               {samples[-1].get('threads', '?'):>8}")

    if "import_pct" in summary:
        print("\nProfiled CPU breakdown:")
        print(f"  simulator             {summary['simulator_pct']:6.1f}%")
        print(f"  import                {summary['import_pct']:6.1f}%")
        print(f"  action                {summary['action_pct']:6.1f}%")
        print(f"  evaluation            {summary['evaluation_pct']:6.1f}%")

    print("\nLast sample:")
    print(json.dumps(samples[-1], indent=2, sort_keys=True))


if __name__ == "__main__":
    profile = "--no-profile" not in sys.argv
    max_turns = 40
    threads = 0
    for arg in sys.argv[1:]:
        if arg.isdigit():
            max_turns = int(arg)
        elif arg.startswith("--threads="):
            threads = int(arg.split("=", 1)[1])
    samples, summary = run(max_turns=max_turns, profile=profile, threads=threads)
    print_report(samples, summary)
