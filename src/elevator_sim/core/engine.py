"""Discrete-time simulation engine.

Owns the tick loop: releases requests once due, hands them to the active Scheduler
for car selection, delegates per-tick movement to the active CarMovementPolicy, and
records positions and passenger pickup/dropoff events."""

from .models import Building, Direction, Passenger, Request

_MAX_TICKS_PER_FLOOR = 20  # safety cap against a runaway loop from a policy bug


class Simulation:
    def __init__(self, building: Building, requests: list[Request], scheduler, car_policy):
        self.building = building
        self.scheduler = scheduler
        self.car_policy = car_policy
        self.passengers = [Passenger(request=r) for r in sorted(requests, key=lambda r: r.time)]
        self.position_log: list[dict] = []
        self.tick = 0

    def _elevator_by_id(self, elevator_id: str):
        return next(e for e in self.building.elevators if e.id == elevator_id)

    def _release_and_assign(self):
        for p in self.passengers:
            if p.request.time <= self.tick and p.assigned_elevator is None:
                elevator_id, estimated_wait_time = self.scheduler.assign(
                    p.request, self.building.elevators, self.tick, self.building.floors
                )
                elevator = self._elevator_by_id(elevator_id)
                p.assigned_elevator = elevator_id
                p.estimated_wait_time = estimated_wait_time
                elevator.stop_queue.add(p.request.source)

    def _board_and_dropoff(self, elevator):
        floor = elevator.current_floor
        if floor not in elevator.stop_queue:
            return

        elevator.onboard = [p for p in elevator.onboard if not self._dropoff_if_arrived(p, floor)]

        waiting_here = [
            p for p in self.passengers
            if p.assigned_elevator == elevator.id and p.request.source == floor and p.pickup_time is None
        ]
        for p in waiting_here:
            if len(elevator.onboard) >= elevator.capacity:
                break
            p.pickup_time = self.tick
            elevator.onboard.append(p)
            elevator.stop_queue.add(p.request.dest)

        pending_pickup = any(
            p.assigned_elevator == elevator.id and p.request.source == floor and p.pickup_time is None
            for p in self.passengers
        )
        pending_dropoff = any(p.request.dest == floor for p in elevator.onboard)
        if not pending_pickup and not pending_dropoff:
            elevator.stop_queue.discard(floor)

    def _dropoff_if_arrived(self, passenger: Passenger, floor: int) -> bool:
        if passenger.request.dest == floor:
            passenger.dropoff_time = self.tick
            return True
        return False

    def _move(self, elevator):
        direction = self.car_policy.next_direction(elevator, self.tick, self.building.floors)
        elevator.direction = direction
        if direction == Direction.UP:
            elevator.current_floor += 1
        elif direction == Direction.DOWN:
            elevator.current_floor -= 1

    def run(self):
        max_ticks = self.building.floors * _MAX_TICKS_PER_FLOOR
        while not all(p.dropoff_time is not None for p in self.passengers):
            if self.tick > max_ticks:
                raise RuntimeError(f"simulation did not terminate within {max_ticks} ticks")

            self._release_and_assign()

            for elevator in self.building.elevators:
                self._board_and_dropoff(elevator)

            self.position_log.append(
                {"time": self.tick, **{e.id: e.current_floor for e in self.building.elevators}}
            )

            for elevator in self.building.elevators:
                self._move(elevator)

            self.tick += 1

        return self.passengers, self.position_log
