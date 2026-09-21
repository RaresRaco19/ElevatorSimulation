"""Batch-run every scenario in data/requests/ across a grid of elevator counts and
capacities, for every implemented (scheduler, car_policy) pair, and write:

- a full 5-file run output (matching run_simulation.py's own output shape) for every
  config that converges, under outputs/sweep/<scenario>/<scheduler>_<car_policy>/
  e<elevators>_c<capacity>/
- outputs/sweep/manifest.json -- a flat JSON list of one record per attempted config
  (converged or not), with that run's passenger_stats.json inlined. This is the single
  source of truth consumed by compare_schedulers.py, plot_wait_times.py, and the UI's
  sweep browser.

A second, independent mode sweeps destination_dispatch's cost weights instead of the
scheduler/car-policy grid -- see WEIGHT_PRESETS and sweep_weights() below. It writes to
its own directory and its own manifest so the two can never clobber each other (this
script wipes its output directory on every run), and so the schema above stays exactly as
plot_wait_times.py and the UI expect it.

Run with: python analysis/scripts/run_sweep.py
          python analysis/scripts/run_sweep.py --weights
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from elevator_sim.core import io, metrics
from elevator_sim.core.engine import Simulation
from elevator_sim.core.models import Building, Elevator
from elevator_sim.run_simulation import CAR_POLICIES, SCHEDULERS
from elevator_sim.schedulers import destination_dispatch as dd

# Floors are structural per scenario (every source/dest in that file was authored
# against this cap) -- only elevators/capacity are swept. Values match the
# recommendations documented in data/requests/README.md.
SCENARIOS = {
    "sample_stress.csv": 60,
    "sample_full_day.csv": 35,
    "sample_small_office_day.csv": 10,
    "sample_quiet_intermittent.csv": 10,
    "sample_lunch_rush.csv": 20,
    "sample_uppeak_highrise30.csv": 30,
    "sample_downpeak_highrise40.csv": 40,
    "sample_full_day_skyscraper50.csv": 50,
    "sample_capacity_overload.csv": 15,
    "sample_contradictory_conflicts.csv": 15,
    "sample_single_elevator_bottleneck.csv": 15,
}

# (scheduler_name, car_policy_name) pairs to sweep -- both must already be wired into
# run_simulation.py's SCHEDULERS/CAR_POLICIES registries. Extend this list as more
# schedulers get wired in.
PAIRS = [
    ("round_robin", "scan"),
    ("round_robin", "look"),
    ("round_robin", "bounded_detour"),
    ("destination_dispatch", "scan"),
    ("destination_dispatch", "look"),
    ("destination_dispatch", "bounded_detour"),
]

ELEVATOR_COUNTS = range(1, 11)
CAPACITIES = [3, 5, 8, 13]

REQUESTS_DIR = ROOT / "data" / "requests"
SWEEP_OUT_DIR = ROOT / "outputs" / "sweep"
WEIGHTS_OUT_DIR = ROOT / "outputs" / "weights"

# --weights mode: cost weightings for schedulers/destination_dispatch.py, as
# (w_wait, w_travel, w_fairness). The anchor is derived from the scheduler's own
# constants rather than repeated here, so it stays the true default if those are ever
# retuned. Every preset is swept against every car policy, because the weights and the
# movement rule interact -- fairness may well matter less when cars can already detour.
WEIGHT_PRESETS = {
    "default": (dd.W_WAIT, dd.W_TRAVEL, dd.W_FAIRNESS),
    "ride-heavy": (1.0, 1.0, 0.2),
    "balanced": (1.0, 0.5, 0.5),  # what shipped before the sweep retuned the defaults
    "fair": (1.0, 0.5, 1.5),
    "selfish": (1.0, 0.5, 0.0),  # fairness off -> nearest-car-with-a-real-ETA
}
WEIGHT_CAR_POLICIES = ["scan", "look", "bounded_detour"]


def run_one(requests, floors, scheduler, car_policy_name, elevators, capacity):
    """`scheduler` is an instance, not a registry name, so a caller can hand over one
    built with non-default settings (see sweep_weights)."""
    elevator_ids = [f"E{i + 1}" for i in range(elevators)]
    elevator_objs = [Elevator(id=eid, current_floor=1, capacity=capacity) for eid in elevator_ids]
    building = Building(floors=floors, elevators=elevator_objs)
    simulation = Simulation(building, requests, scheduler, CAR_POLICIES[car_policy_name]())
    passengers, position_log = simulation.run()
    return elevator_ids, passengers, position_log


def sweep_weights():
    """Sweep destination_dispatch's cost weights over the same config grid as the main
    sweep, for every preset x car policy.

    Stats only -- no per-run output files. compare_schedulers.py needs nothing but the
    stats; the UI browses outputs/ and outputs/runs/, not this directory; and writing
    five files for each of ~6600 runs would cost ~100MB and most of the runtime. To
    inspect one weighting as a real run, use run_simulation.py's --w-* flags, which
    produce an ordinary browsable run folder.
    """
    if WEIGHTS_OUT_DIR.exists():
        shutil.rmtree(WEIGHTS_OUT_DIR)
    WEIGHTS_OUT_DIR.mkdir(parents=True)

    manifest = []
    per_preset = {name: [0, 0] for name in WEIGHT_PRESETS}  # name -> [converged, total]

    for filename, floors in SCENARIOS.items():
        scenario = filename[:-4]  # strip ".csv"
        requests = io.load_requests(REQUESTS_DIR / filename)

        for preset, (w_wait, w_travel, w_fairness) in WEIGHT_PRESETS.items():
            for car_policy_name in WEIGHT_CAR_POLICIES:
                for elevators in ELEVATOR_COUNTS:
                    for capacity in CAPACITIES:
                        per_preset[preset][1] += 1
                        record = {
                            "scenario": scenario,
                            "scheduler": "destination_dispatch",
                            "car_policy": car_policy_name,
                            "preset": preset,
                            "weights": {
                                "wait": w_wait,
                                "travel": w_travel,
                                "fairness": w_fairness,
                            },
                            "elevators": elevators,
                            "capacity": capacity,
                            "floors": floors,
                        }
                        scheduler = dd.DestinationDispatchScheduler(
                            w_wait=w_wait, w_travel=w_travel, w_fairness=w_fairness
                        )
                        try:
                            _ids, passengers, _log = run_one(
                                requests, floors, scheduler, car_policy_name, elevators, capacity
                            )
                        except RuntimeError:
                            record["converged"] = False
                            record["stats"] = None
                            manifest.append(record)
                            continue

                        per_preset[preset][0] += 1
                        record["converged"] = True
                        record["stats"] = metrics.compute_passenger_stats(passengers)
                        manifest.append(record)

    manifest_path = WEIGHTS_OUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    converged = sum(c for c, _ in per_preset.values())
    total = sum(t for _, t in per_preset.values())
    print(f"Weight sweep complete: {converged}/{total} configs converged.")
    for preset, (c, t) in per_preset.items():
        w_wait, w_travel, w_fairness = WEIGHT_PRESETS[preset]
        print(f"  {preset:<11} {w_wait} / {w_travel} / {w_fairness}: {c}/{t} converged")
    print(f"Manifest written to {manifest_path.relative_to(ROOT)}")
    print("Chart it with: python analysis/scripts/compare_schedulers.py --weights")


def sweep_pairs():
    if SWEEP_OUT_DIR.exists():
        shutil.rmtree(SWEEP_OUT_DIR)
    SWEEP_OUT_DIR.mkdir(parents=True)

    manifest = []
    converged_count = 0
    total_count = 0
    per_pair_totals = {pair: [0, 0] for pair in PAIRS}  # pair -> [converged, total]

    for filename, floors in SCENARIOS.items():
        scenario = filename[:-4]  # strip ".csv"
        requests_path = REQUESTS_DIR / filename
        requests = io.load_requests(requests_path)

        for scheduler_name, car_policy_name in PAIRS:
            for elevators in ELEVATOR_COUNTS:
                for capacity in CAPACITIES:
                    total_count += 1
                    per_pair_totals[(scheduler_name, car_policy_name)][1] += 1
                    record = {
                        "scenario": scenario,
                        "scheduler": scheduler_name,
                        "car_policy": car_policy_name,
                        "elevators": elevators,
                        "capacity": capacity,
                        "floors": floors,
                    }
                    try:
                        elevator_ids, passengers, position_log = run_one(
                            requests,
                            floors,
                            SCHEDULERS[scheduler_name](),
                            car_policy_name,
                            elevators,
                            capacity,
                        )
                    except RuntimeError:
                        record["converged"] = False
                        record["run_dir"] = None
                        record["stats"] = None
                        manifest.append(record)
                        continue

                    converged_count += 1
                    per_pair_totals[(scheduler_name, car_policy_name)][0] += 1

                    run_dir_rel = f"sweep/{scenario}/{scheduler_name}_{car_policy_name}/e{elevators}_c{capacity}"
                    run_dir = ROOT / "outputs" / run_dir_rel
                    run_dir.mkdir(parents=True, exist_ok=True)

                    stats = metrics.compute_passenger_stats(passengers)
                    io.write_positions_log(position_log, elevator_ids, run_dir / "positions_log.csv")
                    io.write_requests_copy(requests, run_dir / "requests.csv")
                    io.write_passenger_log(passengers, run_dir / "passenger_log.csv")
                    io.write_passenger_stats(stats, run_dir / "passenger_stats.json")
                    io.write_run_config(
                        {
                            "scheduler": scheduler_name,
                            "car_policy": car_policy_name,
                            "floors": floors,
                            "elevators": elevator_ids,
                            "capacity": capacity,
                            "input_file": f"data/requests/{filename}",
                            "note": f"car_policy={car_policy_name}",
                        },
                        run_dir / "config.json",
                    )

                    record["converged"] = True
                    record["run_dir"] = run_dir_rel
                    record["stats"] = stats
                    manifest.append(record)

    manifest_path = SWEEP_OUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Sweep complete: {converged_count}/{total_count} configs converged.")
    for pair, (converged, total) in per_pair_totals.items():
        print(f"  {pair[0]}+{pair[1]}: {converged}/{total} converged")
    print(f"Manifest written to {manifest_path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weights",
        action="store_true",
        help="Sweep destination_dispatch's cost weight presets instead of the "
        "scheduler/car-policy grid. Writes outputs/weights/manifest.json and leaves "
        "outputs/sweep/ untouched.",
    )
    args = parser.parse_args()

    if args.weights:
        sweep_weights()
    else:
        sweep_pairs()


if __name__ == "__main__":
    main()
