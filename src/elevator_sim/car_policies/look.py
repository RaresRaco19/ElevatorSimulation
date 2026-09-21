"""LOOK: like SCAN, but reverses as soon as there are no more committed stops
further in the current direction, instead of continuing on to floor 1 or the top
floor. Closer to what real elevator controllers do."""

from elevator_sim.core import trip_estimator
from elevator_sim.core.models import Direction, Elevator
from .base import CarMovementPolicy


def look_direction(floor: int, direction: Direction, stops) -> Direction:
    """The LOOK rule as a plain function of position, heading, and committed stops.

    Split out of LookPolicy so bounded_detour.py can ask "what would LOOK do from
    here?" while a car is mid-detour -- at which point `Elevator.direction` is the
    direction of the detour, not of the sweep the car means to resume, so passing the
    elevator itself would give the wrong answer. One rule, one implementation."""
    if not stops:
        return Direction.IDLE

    direction = trip_estimator.resolve_direction(floor, direction, stops)
    if direction == Direction.IDLE:
        return Direction.IDLE  # only pending stop is the current floor

    if direction == Direction.UP:
        if any(f > floor for f in stops):
            return Direction.UP
        return Direction.DOWN if any(f < floor for f in stops) else Direction.IDLE

    if any(f < floor for f in stops):
        return Direction.DOWN
    return Direction.UP if any(f > floor for f in stops) else Direction.IDLE


class LookPolicy(CarMovementPolicy):
    def next_direction(self, elevator: Elevator, current_time: int, floors: int) -> Direction:
        return look_direction(elevator.current_floor, elevator.direction, elevator.stop_queue)
