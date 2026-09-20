"""Pure computation of aggregate passenger statistics. No file I/O -- see
core/io.py's write_passenger_stats for serialization of this module's output."""

from .models import Passenger


def _summary(values: list[float]) -> dict:
    return {"min": min(values), "max": max(values), "avg": sum(values) / len(values)}


def compute_passenger_stats(passengers: list[Passenger]) -> dict:
    wait_times = [p.actual_wait_time for p in passengers]
    total_times = [p.total_time for p in passengers]
    drifts = [p.actual_wait_time - p.estimated_wait_time for p in passengers]

    return {
        "count": len(passengers),
        "wait_time": _summary(wait_times),
        "total_time": _summary(total_times),
        "estimate_drift": {
            "max": max(drifts),
            "avg": sum(drifts) / len(drifts),
            "passengers_delayed_beyond_estimate": sum(1 for d in drifts if d > 0),
        },
        "notes": [],
    }
