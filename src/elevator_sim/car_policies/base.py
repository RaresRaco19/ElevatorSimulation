"""CarMovementPolicy interface.

Orthogonal to schedulers/base.py's Scheduler: a Scheduler decides *which elevator*
handles a new request; a CarMovementPolicy decides *how a single already-assigned
car moves* -- which direction it travels next and when it reverses, given its
current floor, current direction, and committed stop queue (pickup + dropoff
floors already assigned to it by the Scheduler). It does not decide which requests
get assigned to the car (Scheduler's job) and does not enforce capacity (engine's
job).
"""

from abc import ABC, abstractmethod

from elevator_sim.core import trip_estimator
from elevator_sim.core.models import Direction, Elevator


class CarMovementPolicy(ABC):
    #: Which reversal rule this policy follows, in core/trip_estimator.py's terms --
    #: LOOK turns around at the furthest committed stop, SCAN runs on to the building's
    #: end. It is declared here rather than inferred, because a scheduler that estimates
    #: travel times has to know where cars turn around to get them right, and that is
    #: this layer's rule to state. Default LOOK: a policy only needs to override it if
    #: it really does run past its last stop.
    reversal_geometry: str = trip_estimator.LOOK

    @abstractmethod
    def next_direction(self, elevator: Elevator, current_time: int, floors: int) -> Direction:
        """Direction the elevator should move this tick (or IDLE if it has no
        committed stops). Called once per tick per elevator by core/engine.py."""
        raise NotImplementedError
