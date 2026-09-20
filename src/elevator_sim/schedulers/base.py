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
