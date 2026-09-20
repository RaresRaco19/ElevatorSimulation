"""Bonus -- express elevator(s) that only stop at a subset of floors (a "serviceable
set"), selected by nearest-car distance among whichever elevators can actually reach
both ends of the trip.

An elevator opts into express behaviour via its `serviceable_floors` field on
core/models.py's Elevator (None, the default, means "stops everywhere" -- fully
backward compatible with every existing car). This module's `express_floor_set()`
helper builds one shared shape of serviceable set: floor 1 (lobby) always included,
plus every `stride`-th floor after that, capped at the building's top floor -- e.g.
floors=16, stride=5 -> {1, 6, 11, 16}. Nothing requires every express car in a fleet
to share the same set or stride; each car's serviceable_floors is independent.

Eligibility per request: a regular (non-express) car -- serviceable_floors is None --
can always take it. An express car can only take it if BOTH the source and dest floor
are in its serviceable_floors. Among all eligible cars, the nearest one by
abs(current_floor - request.source) wins, ties broken by position in the `elevators`
list -- a deterministic, still-naive rule in the same spirit as round_robin's, just
with an eligibility filter layered on top.

No transfer support: this engine has no multi-leg passenger model (core/models.py's
Passenger has exactly one assigned_elevator, one pickup, one dropoff), so a request
that no single eligible car can serve -- e.g. an all-express fleet asked to travel
between two floors neither express car stops at -- cannot be routed at all. assign()
raises NoEligibleElevatorError in that case rather than silently mis-assigning a car
that would never reach one end of the trip (which would either strand the passenger
forever or blow the engine's max-ticks safety cap with no clear cause far from the
real problem). Callers that want every request served must ensure the fleet passed to
assign() always has at least one regular car, or that express serviceable sets are
arranged so every requested (source, dest) pair is jointly covered."""

from elevator_sim.core.models import Elevator, Request
from .base import Scheduler

DEFAULT_STRIDE = 5


def express_floor_set(floors: int, stride: int = DEFAULT_STRIDE) -> frozenset[int]:
    """Serviceable floors for an express car: floor 1 (lobby) is always included,
    plus every `stride`-th floor after that, capped at the building's top floor.
    E.g. express_floor_set(16, 5) == frozenset({1, 6, 11, 16})."""
    if floors < 1:
        raise ValueError(f"floors must be >= 1, got {floors}")
    if stride < 1:
        raise ValueError(f"stride must be >= 1, got {stride}")
    return frozenset(range(1, floors + 1, stride))


class NoEligibleElevatorError(RuntimeError):
    """Raised when no elevator in the fleet passed to assign() can serve a request --
    no express car's serviceable_floors covers both source and dest, and there is no
    regular (all-floor) car to fall back to. This engine has no transfer mechanic, so
    such a request is genuinely unroutable; this is a fail-fast signal, not a bug in
    the scheduler."""


class ExpressScheduler(Scheduler):
    def assign(
        self, request: Request, elevators: list[Elevator], current_time: int, floors: int
    ) -> tuple[str, int]:
        eligible = [
            (index, elevator)
            for index, elevator in enumerate(elevators)
            if self._can_serve(elevator, request)
        ]
        if not eligible:
            raise NoEligibleElevatorError(
                f"No elevator can serve request {request.id} "
                f"(floor {request.source} -> {request.dest}): no express car's "
                f"serviceable_floors covers both floors, and no regular (all-floor) "
                f"elevator is available. Transfers between non-served floors are not "
                f"supported."
            )
        _, elevator = min(
            eligible,
            key=lambda pair: (abs(pair[1].current_floor - request.source), pair[0]),
        )
        return elevator.id, abs(elevator.current_floor - request.source)

    @staticmethod
    def _can_serve(elevator: Elevator, request: Request) -> bool:
        if elevator.serviceable_floors is None:
            return True
        return (
            request.source in elevator.serviceable_floors
            and request.dest in elevator.serviceable_floors
        )
