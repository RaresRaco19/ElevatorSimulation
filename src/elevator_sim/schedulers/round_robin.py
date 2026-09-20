"""Bonus -- cycle elevators in a fixed rotation, still ignoring each elevator's
actual position and remaining stop queue. The two things it does account for:
requests arriving in the very same tick and heading the same direction are
bucketed onto the same car instead of each claiming a fresh one off the rotation
(otherwise a burst of simultaneous compatible requests would pointlessly occupy every
elevator at once) -- but that bucket is capped at the car's capacity, so once it
fills up the next same-tick/same-direction request rolls onto the next car in the
rotation instead of overloading the one already chosen. Still a purely mechanical
baseline (no distance/ETA comparison, no awareness of what's already onboard from
earlier ticks) to contrast against other scheduler algorithms in analysis/."""

from elevator_sim.core.models import Elevator, Request
from .base import Scheduler


class RoundRobinScheduler(Scheduler):
    def __init__(self):
        self._next_index = 0
        self._batch_tick: int | None = None
        self._batches: dict[str, tuple[Elevator, int]] = {}

    def assign(
        self, request: Request, elevators: list[Elevator], current_time: int, floors: int
    ) -> tuple[str, int]:
        if current_time != self._batch_tick:
            self._batch_tick = current_time
            self._batches = {}

        direction = "UP" if request.dest >= request.source else "DOWN"
        elevator, count = self._batches.get(direction, (None, 0))
        if elevator is None or count >= elevator.capacity:
            elevator = elevators[self._next_index % len(elevators)]
            self._next_index += 1
            count = 0

        self._batches[direction] = (elevator, count + 1)
        return elevator.id, abs(elevator.current_floor - request.source)
