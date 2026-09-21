"""CLI entrypoint.

Wires together: core.io.load_requests -> core.engine.Simulation(scheduler=...,
car_policy=...) -> run to completion -> core.io writes positions_log.csv /
requests.csv / passenger_log.csv / passenger_stats.json / config.json into
outputs/<scheduler>_<car_policy>_<scenario>/.
"""

import argparse
import os

from elevator_sim.car_policies.bounded_detour import BoundedDetourPolicy
from elevator_sim.car_policies.look import LookPolicy
from elevator_sim.car_policies.scan import ScanPolicy
from elevator_sim.core import io, metrics
from elevator_sim.core.engine import Simulation
from elevator_sim.core.models import Building, Elevator
from elevator_sim.schedulers.destination_dispatch import DestinationDispatchScheduler
from elevator_sim.schedulers.round_robin import RoundRobinScheduler

# More scheduler/policy choices get added here as those files get implemented.
SCHEDULERS = {
    "round_robin": RoundRobinScheduler,
    "destination_dispatch": DestinationDispatchScheduler,
}
CAR_POLICIES = {
    "scan": ScanPolicy,
    "look": LookPolicy,
    "bounded_detour": BoundedDetourPolicy,
}


def main():
    parser = argparse.ArgumentParser(description="Run the elevator simulation.")
    # destination_dispatch + bounded_detour is the recommended configuration -- see
    # analysis/README.md for the sweep it was chosen from. The baselines it is measured
    # against stay selectable.
    parser.add_argument(
        "--scheduler", choices=sorted(SCHEDULERS), default="destination_dispatch",
        help="default: %(default)s",
    )
    parser.add_argument(
        "--car-policy", choices=sorted(CAR_POLICIES), default="bounded_detour",
        help="default: %(default)s",
    )
    parser.add_argument("--requests", required=True)
    parser.add_argument("--elevators", type=int, required=True)
    parser.add_argument("--floors", type=int, required=True)
    parser.add_argument("--capacity", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.elevators < 1:
        parser.error("--elevators must be at least 1")

    requests = io.load_requests(args.requests)
    elevator_ids = [f"E{i + 1}" for i in range(args.elevators)]
    elevators = [Elevator(id=eid, current_floor=1, capacity=args.capacity) for eid in elevator_ids]
    building = Building(floors=args.floors, elevators=elevators)

    scheduler = SCHEDULERS[args.scheduler]()
    simulation = Simulation(building, requests, scheduler, CAR_POLICIES[args.car_policy]())
    passengers, position_log = simulation.run()

    os.makedirs(args.out, exist_ok=True)
    io.write_positions_log(position_log, elevator_ids, os.path.join(args.out, "positions_log.csv"))
    io.write_requests_copy(requests, os.path.join(args.out, "requests.csv"))
    io.write_passenger_log(passengers, os.path.join(args.out, "passenger_log.csv"))
    io.write_passenger_stats(
        metrics.compute_passenger_stats(passengers), os.path.join(args.out, "passenger_stats.json")
    )
    config = {
        "scheduler": args.scheduler,
        "car_policy": args.car_policy,
        "floors": args.floors,
        "elevators": elevator_ids,
        "capacity": args.capacity,
        "input_file": args.requests,
        "note": f"car_policy={args.car_policy}",
    }
    if args.scheduler == "destination_dispatch":
        # Recorded even though they are fixed: the constants have been retuned once
        # already, and this is what tells a run generated before that apart from one
        # generated after.
        config["weights"] = {
            "wait": scheduler.w_wait,
            "travel": scheduler.w_travel,
            "fairness": scheduler.w_fairness,
        }
    io.write_run_config(config, os.path.join(args.out, "config.json"))


if __name__ == "__main__":
    main()
