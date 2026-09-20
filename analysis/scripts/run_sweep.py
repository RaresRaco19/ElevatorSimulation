"""Batch-run every scenario in data/requests/ across a grid of elevator counts and
capacities, for every implemented (scheduler, car_policy) pair, and write:

- a full 5-file run output (matching run_simulation.py's own output shape) for every
  config that converges, under outputs/sweep/<scenario>/<scheduler>_<car_policy>/
  e<elevators>_c<capacity>/
- outputs/sweep/manifest.json -- a flat JSON list of one record per attempted config
  (converged or not), with that run's passenger_stats.json inlined. This is the single
  source of truth consumed by compare_schedulers.py, plot_wait_times.py, and the UI's
  sweep browser.

Run with: python analysis/scripts/run_sweep.py
"""

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
PAIRS = [("round_robin", "scan"), ("round_robin", "look")]

ELEVATOR_COUNTS = range(1, 11)
CAPACITIES = [3, 5, 8, 13]

REQUESTS_DIR = ROOT / "data" / "requests"
SWEEP_OUT_DIR = ROOT / "outputs" / "sweep"


def run_one(requests, floors, scheduler_name, car_policy_name, elevators, capacity):
    elevator_ids = [f"E{i + 1}" for i in range(elevators)]
    elevator_objs = [Elevator(id=eid, current_floor=1, capacity=capacity) for eid in elevator_ids]
    building = Building(floors=floors, elevators=elevator_objs)
    simulation = Simulation(
        building, requests, SCHEDULERS[scheduler_name](), CAR_POLICIES[car_policy_name]()
    )
    passengers, position_log = simulation.run()
    return elevator_ids, passengers, position_log


def main():
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
                            requests, floors, scheduler_name, car_policy_name, elevators, capacity
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


if __name__ == "__main__":
    main()
