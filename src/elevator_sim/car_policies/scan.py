"""SCAN ("elevator algorithm"): continue moving in the current direction, serving
every committed stop along the way, until reaching floor 1 or the top floor -- then
reverse, even if no committed stops remain in that direction."""

from elevator_sim.core import trip_estimator
from elevator_sim.core.models import Direction, Elevator
from .base import CarMovementPolicy


class ScanPolicy(CarMovementPolicy):
    reversal_geometry = trip_estimator.SCAN

    def next_direction(self, elevator: Elevator, current_time: int, floors: int) -> Direction:
        if not elevator.stop_queue:
            return Direction.IDLE

        direction = elevator.direction
        if direction == Direction.IDLE:
            if any(f > elevator.current_floor for f in elevator.stop_queue):
                direction = Direction.UP
            elif any(f < elevator.current_floor for f in elevator.stop_queue):
                direction = Direction.DOWN
            else:
                return Direction.IDLE  # only pending stop is the current floor

        if direction == Direction.UP:
            return Direction.DOWN if elevator.current_floor >= floors else Direction.UP
        return Direction.UP if elevator.current_floor <= 1 else Direction.DOWN
