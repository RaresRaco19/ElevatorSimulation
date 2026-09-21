"""LOOK with bounded detours: a car mid-sweep may turn back for one nearby stop it has
already passed, then resume exactly where it left off.

Plain LOOK is unfair to anyone standing behind a car that has just gone by: they wait out
the entire remaining sweep plus the return leg, however close the car actually is. This
policy lets the car double back -- but only inside three hard bounds, so the fix cannot
turn into the thrashing that unrestricted reversal (`fcfs`-style) produces:

    D  MAX_DETOUR_DISTANCE     how far back the car may divert from where it stands
    k  MAX_DETOURS_PER_SWEEP   how many diversions one sweep may spend
    F  MAX_FAIRNESS_DELAY      how much one diversion may delay those already aboard

Together these bound the worst case at exactly `k * 2D` extra ticks per sweep for every
passenger aboard, which is a real guarantee rather than a tendency -- every quantity
involved is exact (see core/trip_estimator.py), so the bound is directly checkable, and
tests/test_car_policies.py checks it.

A detour is not a new kind of motion; it is a sweep extension that snaps back instead of
persisting, which is why the arithmetic is already in trip_estimator and none of it is
repeated here. This file contributes control flow only: `trip_estimator.detour_eligible`
decides whether a diversion is allowed and `look.look_direction` decides where the sweep
goes otherwise, so the movement a car performs and the cost a scheduler predicts for it
are derived from the same two functions and cannot drift apart.

Bounds are module constants rather than CLI flags deliberately: they are a property of
how this policy behaves, not of an individual run, so `run_simulation.py`'s interface is
unchanged and every existing command keeps working exactly as before.
"""

from dataclasses import dataclass

from elevator_sim.core import trip_estimator as te
from elevator_sim.core.models import Direction, Elevator
from .base import CarMovementPolicy
from .look import look_direction

MAX_DETOUR_DISTANCE = 4  # D
MAX_DETOURS_PER_SWEEP = 2  # k
MAX_FAIRNESS_DELAY = 8  # F -- worst case per sweep is k * 2D = 16 ticks


@dataclass
class _SweepState:
    """Per-car bookkeeping. `resume` is the sweep direction to return to once the
    current diversion finishes; it exists because `Elevator.direction` gets overwritten
    with whatever this policy last returned (core/engine.py), so once a car turns back
    the elevator itself no longer remembers which way it was sweeping."""

    target: int | None = None
    resume: Direction = Direction.IDLE
    used: int = 0


def _toward(floor: int, target: int) -> Direction:
    if target > floor:
        return Direction.UP
    if target < floor:
        return Direction.DOWN
    return Direction.IDLE


class BoundedDetourPolicy(CarMovementPolicy):
    reversal_geometry = te.LOOK  # between diversions this is LOOK, exactly

    def __init__(
        self,
        max_detour_distance: int = MAX_DETOUR_DISTANCE,
        max_detours_per_sweep: int = MAX_DETOURS_PER_SWEEP,
        max_fairness_delay: int = MAX_FAIRNESS_DELAY,
    ):
        self.max_detour_distance = max_detour_distance
        self.max_detours_per_sweep = max_detours_per_sweep
        self.max_fairness_delay = max_fairness_delay
        # One policy instance serves the whole fleet (run_simulation.py builds one), so
        # sweep state is per car, keyed by elevator id.
        self._sweeps: dict[str, _SweepState] = {}

    def detour_limits(self, elevator: Elevator) -> te.DetourLimits:
        """The bounds this car is under right now, for a scheduler scoring it.

        Without this a dispatcher would price every behind-the-car pickup at the cost of
        a full reversal and systematically pass over the cars best placed to take it.
        Duck-typed on the scheduler's side, so only policies that can actually detour
        need to offer it."""
        return te.DetourLimits(
            max_distance=self.max_detour_distance,
            max_fairness_delay=self.max_fairness_delay,
            detours_remaining=self.max_detours_per_sweep - self._state(elevator).used,
        )

    def _state(self, elevator: Elevator) -> _SweepState:
        return self._sweeps.setdefault(elevator.id, _SweepState())

    def next_direction(self, elevator: Elevator, current_time: int, floors: int) -> Direction:
        state = self._state(elevator)
        stops = elevator.stop_queue

        if not stops:
            self._sweeps[elevator.id] = _SweepState()
            return Direction.IDLE

        sweep = elevator.direction
        if state.target is not None:
            # Finish the diversion, or abandon it if the stop is gone (it was served on
            # the way, or the car arrived full and could not board anyone -- either way,
            # pressing on would strand the car).
            if elevator.current_floor == state.target or state.target not in stops:
                sweep = state.resume
                state.target = None
            else:
                return _toward(elevator.current_floor, state.target)

        heading = look_direction(elevator.current_floor, sweep, stops)
        if heading == Direction.IDLE:
            self._sweeps[elevator.id] = _SweepState()
            return Direction.IDLE

        if sweep not in (Direction.UP, Direction.DOWN):
            return heading  # no sweep under way yet -- nothing to interrupt
        if heading != sweep:
            # LOOK reversed of its own accord: this sweep is over and the next one
            # starts with a full budget.
            state.used = 0
            return heading

        # Still sweeping, so `heading == sweep` guarantees there is work ahead -- the
        # same condition trip_estimator._detour_applies() requires before pricing one.
        target = self._diversion_target(elevator, heading, stops, state)
        if target is None:
            return heading

        state.target = target
        state.resume = heading
        state.used += 1
        return _toward(elevator.current_floor, target)

    def _diversion_target(self, elevator, heading, stops, state) -> int | None:
        """Nearest already-passed stop this car may legally turn back for, if any."""
        limits = te.DetourLimits(
            max_distance=self.max_detour_distance,
            max_fairness_delay=self.max_fairness_delay,
            detours_remaining=self.max_detours_per_sweep - state.used,
        )
        floor = elevator.current_floor
        candidates = [
            f
            for f in stops
            if te.is_behind(floor, heading, f) and te.detour_eligible(floor, f, limits)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda f: (abs(floor - f), f))
