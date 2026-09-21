"""Closed-form trip arithmetic shared by dispatch and movement.

Pure functions over a hypothetical car state -- no I/O, no mutation, and no import of
`schedulers/` or `car_policies/`, so both layers can depend on this one without
depending on each other. The point is that the dispatcher's cost function and a car
policy's detour gate ask the *same* code the same question, so they can never silently
disagree about what a car is going to do.

Everything here is exact rather than approximate, because the engine models zero dwell
time (see the README's "Assumptions"): a car covers exactly one floor per tick and
boarding is instantaneous, so the time to reach any floor is pure geometry -- the
distance forward, or the distance out to the reversal point and back.

The one thing that geometry depends on is *where the car turns around*, which is the
active car policy's defining rule: `look.py` turns at the furthest committed stop
(`extent`), `scan.py` runs on to floor 1 or the top floor regardless. `turn_point()`
takes that as a parameter (`geometry` + `floors`), which makes every formula below exact
for both policies instead of exact for one and wrong for the other. It also means SCAN
correctly reports `extra_extent == 0` for every insertion: under true SCAN the car was
travelling to the end of the building anyway, so an extra stop genuinely costs the
passengers already aboard nothing.
"""

from dataclasses import dataclass

from .models import Direction

# Reversal geometries -- a car policy declares one via its `reversal_geometry` attribute
# (see car_policies/base.py), and a scheduler that scores candidate cars reads it off
# whichever policy it was bound to.
LOOK = "look"
SCAN = "scan"


@dataclass(frozen=True)
class DetourLimits:
    """The bounds a bounded-detour car is operating under, as seen right now.

    `detours_remaining` is `max_detours_per_sweep - used_this_sweep`, i.e. already
    resolved against that car's current sweep, so this module needs no per-car state of
    its own."""

    max_distance: int  # D -- furthest a car may divert from its current floor
    max_fairness_delay: int  # F -- most one detour may delay those already aboard
    detours_remaining: int  # k - used_this_sweep


@dataclass(frozen=True)
class CarState:
    """A candidate car, as the cost function sees it.

    `stops` is the car's *full* commitment set, which is not the same thing as
    `Elevator.stop_queue`: the engine only adds a passenger's destination at boarding
    time, so a caller scoring future assignments has to fold in the destinations it has
    already promised but not yet handed over (see schedulers/destination_dispatch.py's
    pledge ledger). Frozen, so a batch assigner can fork hypothetical futures with
    dataclasses.replace() instead of mutating a shared object."""

    id: str
    floor: int
    direction: Direction
    stops: frozenset[int]
    load: int
    capacity: int
    floors: int  # building top floor; only SCAN geometry needs it
    geometry: str = LOOK
    detour: DetourLimits | None = None


@dataclass(frozen=True)
class InsertionResult:
    """What happens if this car takes this request.

    `extra_extent` is reported separately even though `delta_imposed_on_existing` is
    derived from it, because the batch assigner classifies requests on it directly:
    `extra_extent == 0` means the request nests inside a sweep the car is already
    committed to, which is what makes it free and therefore order-independent."""

    ticks_to_pickup: int
    ticks_to_dropoff: int
    delta_imposed_on_existing: int
    extra_extent: int
    via_detour: bool


def opposite(direction: Direction) -> Direction:
    if direction is Direction.UP:
        return Direction.DOWN
    if direction is Direction.DOWN:
        return Direction.UP
    return Direction.IDLE


def extent(floor: int, direction: Direction, stops) -> int:
    """The furthest floor the car is committed to before it is forced to reverse -- the
    single primitive every other formula here is built from. Returns `floor` itself when
    nothing is committed further that way (a car with nothing ahead of it reverses
    immediately, which is exactly LOOK's rule)."""
    if direction is Direction.UP:
        return max([floor, *(f for f in stops if f > floor)])
    if direction is Direction.DOWN:
        return min([floor, *(f for f in stops if f < floor)])
    return floor


def resolve_direction(floor: int, direction: Direction, stops) -> Direction:
    """The direction a car with `direction` will actually travel. Mirrors the IDLE
    branch that look.py and scan.py share verbatim: an idle car heads toward the first
    committed stop, preferring up."""
    if direction is not Direction.IDLE:
        return direction
    if any(f > floor for f in stops):
        return Direction.UP
    if any(f < floor for f in stops):
        return Direction.DOWN
    return Direction.IDLE


def turn_point(
    floor: int, direction: Direction, stops, geometry: str = LOOK, floors: int = 0
) -> int:
    """Where the car reverses -- the one value that differs between car policies. LOOK
    turns at the furthest committed stop; SCAN runs to the building's end."""
    if geometry == SCAN:
        return floors if direction is Direction.UP else 1
    return extent(floor, direction, stops)


def ticks(
    floor: int,
    direction: Direction,
    stops,
    target: int,
    geometry: str = LOOK,
    floors: int = 0,
) -> int:
    """Exact ticks for a car at `floor` travelling `direction` with commitments `stops`
    to reach `target`.

    `target` is unioned into `stops` internally, so a caller cannot pass a target the car
    is not actually committed to and get a nonsense answer back.

    Forward targets are plain distance. Backward targets are "out to the reversal point,
    then back", which is a single reversal and therefore still closed-form -- a car
    cannot turn twice before reaching a floor behind it.

    The edge cases fall out rather than needing special handling: a car marked UP with
    nothing above it has `turn == floor` under LOOK, so the backward branch collapses to
    plain distance -- which matches LOOK reversing on this very tick."""
    committed = frozenset(stops) | {target}
    resolved = resolve_direction(floor, direction, committed)
    if resolved is Direction.IDLE:
        return 0  # nothing committed anywhere but the current floor
    turn = turn_point(floor, resolved, committed, geometry, floors)
    if resolved is Direction.UP:
        if target >= floor:
            return target - floor
        return 2 * turn - floor - target
    if target <= floor:
        return floor - target
    return floor + target - 2 * turn


def detour_round_trip(floor: int, target: int) -> int:
    """Exact cost of interrupting a sweep at `floor` to serve `target` and return.

    The same quantity as `2 * extra_extent` in evaluate_insertion(): a bounded detour is
    just a sweep extension that snaps back afterwards instead of persisting."""
    return 2 * abs(floor - target)


def ticks_with_detour(
    floor: int,
    direction: Direction,
    stops,
    target: int,
    detour_floor: int,
    geometry: str = LOOK,
    floors: int = 0,
) -> int:
    """Ticks to `target` for a car that first detours to `detour_floor` and comes back.

    A flat surcharge on the undetoured answer, because once back at `floor` the car
    resumes the exact trajectory it would have taken anyway -- with `detour_floor` now
    cleared from its queue. That flatness is what keeps this closed-form, and it is what
    lets detour_eligible() check fairness once instead of once per passenger."""
    remaining = frozenset(stops) - {detour_floor}
    return detour_round_trip(floor, detour_floor) + ticks(
        floor, direction, remaining, target, geometry, floors
    )


def detour_eligible(floor: int, target: int, limits: DetourLimits | None) -> bool:
    """Whether a car at `floor` may divert to `target` under `limits`.

    The fairness bound collapses to a single scalar check rather than a loop over
    everyone aboard: with zero dwell time a detour delays *every* remaining stop by
    exactly `detour_round_trip(floor, target)` (see ticks_with_detour -- the surcharge is
    flat and independent of which stop you measure), so checking it once checks it for
    everyone. tests/test_trip_estimator.py verifies that against a brute-force
    per-passenger comparison rather than taking it on faith.

    A *relative* bound -- "no more than F% of each passenger's remaining trip" -- would
    reintroduce the per-passenger loop, since remaining trips differ. Not the default
    here."""
    if limits is None:
        return False
    return (
        limits.detours_remaining > 0
        and abs(floor - target) <= limits.max_distance
        and detour_round_trip(floor, target) <= limits.max_fairness_delay
    )


def is_behind(floor: int, direction: Direction, target: int) -> bool:
    """True when `target` sits on the far side of the car -- reachable only after a
    reversal."""
    if direction is Direction.UP:
        return target < floor
    if direction is Direction.DOWN:
        return target > floor
    return False


def is_ahead(floor: int, direction: Direction, target: int) -> bool:
    if direction is Direction.UP:
        return target > floor
    if direction is Direction.DOWN:
        return target < floor
    return False


def _reach(floor: int, direction: Direction, stops, geometry: str, floors: int) -> int:
    """How far past `floor` the car travels before reversing, as a distance. Using a
    distance rather than a floor number lets the UP and DOWN cases share one expression,
    and routing it through turn_point() is what makes SCAN correctly report no change in
    reach when stops are added."""
    return abs(turn_point(floor, direction, stops, geometry, floors) - floor)


def _behind_count(floor: int, direction: Direction, stops) -> int:
    return sum(1 for f in stops if is_behind(floor, direction, f))


def evaluate_insertion(car: CarState, source: int, dest: int) -> InsertionResult:
    """Everything the dispatcher needs in order to score `car` taking `source -> dest`.

    Two branches. The normal one is the two-stage insertion: reach the pickup with the
    pickup folded into the queue, then reach the destination from there with the pickup
    cleared and the destination folded in.

    The detour branch applies only to a detour-capable car whose sweep is currently
    carrying it *away* from the pickup: such a car can turn back now rather than make the
    passenger sit out a full reversal, so scoring it on the LOOK-only path would
    systematically undervalue it. Note the passenger waits `dist`, not the round trip --
    they board on arrival. The round trip is what the *other* passengers pay, and it is
    charged to `delta_imposed_on_existing` where it belongs; taking the discount without
    the cost would overvalue detour-capable cars exactly as badly as ignoring detours
    undervalues them.

    Both branches are estimates in the honest sense: exact for the queue as it stands,
    and the queue keeps growing as later requests arrive. What a car ultimately does is
    the car policy's call -- re-derived from this same module."""
    stops = frozenset(car.stops)

    if _detour_applies(car, source, stops):
        sweep = car.direction
        dist = abs(car.floor - source)
        ticks_to_pickup = dist
        # The passenger rides back to the interruption point, then the sweep resumes.
        ticks_to_dropoff = 2 * dist + ticks(
            car.floor, sweep, stops | {dest}, dest, car.geometry, car.floors
        )
        before = _reach(car.floor, sweep, stops, car.geometry, car.floors)
        after = _reach(car.floor, sweep, stops | {dest}, car.geometry, car.floors)
        extra_extent = max(0, after - before)
        delta = 2 * extra_extent * _behind_count(car.floor, sweep, stops)
        delta += detour_round_trip(car.floor, source) * len(stops)
        return InsertionResult(ticks_to_pickup, ticks_to_dropoff, delta, extra_extent, True)

    with_pickup = stops | {source}
    ticks_to_pickup = ticks(car.floor, car.direction, with_pickup, source, car.geometry, car.floors)

    # Direction the car is travelling at the moment it collects the passenger: still the
    # sweep direction if the pickup was ahead of it, the reverse if it had to turn
    # around to get there.
    sweep = resolve_direction(car.floor, car.direction, with_pickup)
    at_pickup = opposite(sweep) if is_behind(car.floor, sweep, source) else sweep

    with_dest = (with_pickup - {source}) | {dest}
    ticks_to_dropoff = ticks_to_pickup + ticks(
        source, at_pickup, with_dest, dest, car.geometry, car.floors
    )

    # Impact on whoever is already committed: the sweep now runs `extra_extent` further
    # out, and everything waiting on the far side of the reversal pays for that twice --
    # once on the way out, once on the way back.
    full = resolve_direction(car.floor, car.direction, stops | {source, dest})
    before = _reach(car.floor, full, stops, car.geometry, car.floors)
    after = _reach(car.floor, full, stops | {source, dest}, car.geometry, car.floors)
    extra_extent = max(0, after - before)
    delta = 2 * extra_extent * _behind_count(car.floor, full, stops)
    return InsertionResult(ticks_to_pickup, ticks_to_dropoff, delta, extra_extent, False)


def _detour_applies(car: CarState, source: int, stops) -> bool:
    """A detour is only on the table for a detour-capable car that is mid-sweep (an idle
    car has no sweep to interrupt -- it simply heads for the pickup), whose sweep is
    carrying it away from the pickup floor, that still has somewhere to be in its current
    direction, and that is inside all three bounds."""
    return (
        car.detour is not None
        and car.direction in (Direction.UP, Direction.DOWN)
        and is_behind(car.floor, car.direction, source)
        and any(is_ahead(car.floor, car.direction, f) for f in stops)
        and detour_eligible(car.floor, source, car.detour)
    )
