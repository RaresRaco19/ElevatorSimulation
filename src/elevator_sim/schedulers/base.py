"""Scheduler interface.

Each scheduler decides *which elevator handles a request* (and, for express variants,
which floors are reachable at all) -- the engine in core/engine.py owns everything
else (movement, capacity, direction, timing). The scheduler also owns its own
estimated_wait_time for the request: a naive scheduler like round_robin can return a
plain distance guess, while a more informed future scheduler could compute a real ETA
to pick the best elevator and report that same number instead of having the engine
recompute a cruder one. This is what makes adding a bonus algorithm a one-file
change.
"""

from abc import ABC, abstractmethod

from elevator_sim.core.models import Elevator, Request


class Scheduler(ABC):
    @abstractmethod
    def assign(
        self, request: Request, elevators: list[Elevator], current_time: int, floors: int
    ) -> tuple[str, int]:
        """Return (elevator_id, estimated_wait_time) for this request."""
        raise NotImplementedError

    def assign_batch(
        self, requests: list[Request], elevators: list[Elevator], current_time: int, floors: int
    ) -> dict[str, tuple[str, int]]:
        """Assign every request released on one tick, keyed by request id.

        The engine calls this rather than assign() directly, because requests arriving
        together interact: committing one to a car changes what that car costs for the
        next one, and a scheduler that scores each request independently cannot see
        that. Schedulers that don't care get the default -- independent, in-order
        assign() calls, exactly what the engine used to do itself.
        """
        return {r.id: self.assign(r, elevators, current_time, floors) for r in requests}

    def bind_car_policy(self, car_policy) -> None:
        """Called once by core/engine.py's Simulation with the car policy this run
        uses. A scheduler whose estimates depend on how cars actually move (where they
        reverse, whether they may detour) needs this; the naive ones ignore it, which
        is why it's a no-op here rather than abstract.
        """
