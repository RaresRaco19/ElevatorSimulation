"""LOOK: like SCAN, but reverses as soon as there are no more committed stops
further in the current direction, instead of continuing on to floor 1 or the top
floor. Closer to what real elevator controllers do."""

from elevator_sim.core.models import Direction, Elevator
from .base import CarMovementPolicy


class LookPolicy(CarMovementPolicy):
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
            if any(f > elevator.current_floor for f in elevator.stop_queue):
                return Direction.UP
            return Direction.DOWN if any(f < elevator.current_floor for f in elevator.stop_queue) else Direction.IDLE

        if any(f < elevator.current_floor for f in elevator.stop_queue):
            return Direction.DOWN
        return Direction.UP if any(f > elevator.current_floor for f in elevator.stop_queue) else Direction.IDLE
