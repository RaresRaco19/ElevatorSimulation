"""I/O boundary -- the schema contract shared by the engine, analysis, and ui/.

Pure read/write functions; no simulation logic and no stats computation here (see
metrics.py for that) -- this module only parses input and serializes results."""

import csv
import json

from .models import Passenger, Request


def load_requests(path) -> list[Request]:
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [
            Request(time=int(row["time"]), id=row["id"], source=int(row["source"]), dest=int(row["dest"]))
            for row in reader
        ]


def write_requests_copy(requests: list[Request], path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "id", "source", "dest"])
        for r in requests:
            writer.writerow([r.time, r.id, r.source, r.dest])


def write_positions_log(position_log: list[dict], elevator_ids: list[str], path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", *elevator_ids])
        for row in position_log:
            writer.writerow([row["time"], *(row[eid] for eid in elevator_ids)])


def write_passenger_log(passengers: list[Passenger], path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id", "source", "dest", "request_time", "elevator",
                "estimated_wait_time", "pickup_time", "actual_wait_time",
                "dropoff_time", "travel_time", "total_time",
            ]
        )
        for p in passengers:
            writer.writerow(
                [
                    p.request.id, p.request.source, p.request.dest, p.request.time,
                    p.assigned_elevator, p.estimated_wait_time, p.pickup_time,
                    p.actual_wait_time, p.dropoff_time, p.travel_time, p.total_time,
                ]
            )


def write_passenger_stats(stats: dict, path) -> None:
    with open(path, "w") as f:
        json.dump(stats, f, indent=2)


def write_run_config(config: dict, path) -> None:
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
