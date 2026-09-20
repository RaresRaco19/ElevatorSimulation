"""Request, Passenger, Elevator, Building dataclasses shared across the engine,
schedulers, and car policies."""

from dataclasses import dataclass, field
from enum import Enum


class Direction(Enum):
    UP = 1
    DOWN = -1
    IDLE = 0


@dataclass
class Request:
    time: int
    id: str
    source: int
    dest: int


@dataclass
class Elevator:
    id: str
    current_floor: int
    capacity: int
    direction: Direction = Direction.IDLE
    onboard: list = field(default_factory=list)  # list[Passenger]
    stop_queue: set = field(default_factory=set)  # floors with a pending pickup/dropoff
    serviceable_floors: frozenset[int] | None = None  # None = stops at every floor


@dataclass
class Passenger:
    request: Request
    assigned_elevator: str | None = None
    estimated_wait_time: int | None = None
    pickup_time: int | None = None
    dropoff_time: int | None = None

    @property
    def actual_wait_time(self) -> int | None:
        if self.pickup_time is None:
            return None
        return self.pickup_time - self.request.time

    @property
    def travel_time(self) -> int | None:
        if self.dropoff_time is None or self.pickup_time is None:
            return None
        return self.dropoff_time - self.pickup_time

    @property
    def total_time(self) -> int | None:
        if self.actual_wait_time is None or self.travel_time is None:
            return None
        return self.actual_wait_time + self.travel_time


@dataclass
class Building:
    floors: int
    elevators: list  # list[Elevator]
