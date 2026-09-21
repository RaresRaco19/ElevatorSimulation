"""Destination dispatch -- pick the car whose *whole trip cost* is lowest, using the
passenger's destination, which every other scheduler here throws away.

`round_robin` cycles cars blind; `express` picks the nearest eligible one. Both answer
"which car is closest to the pickup", which is a question about the first leg only. This
scheduler scores three things instead, all of them exact closed-form values from
core/trip_estimator.py (no per-candidate simulation):

    cost = w_wait     * ticks_to_pickup                      how long this passenger waits
         + w_travel   * (ticks_to_dropoff - ticks_to_pickup) how long they then ride
         + w_fairness * delta_imposed_on_existing            what it costs everyone else

The weights are constructor arguments defaulting to the W_* constants below, so a run
can be scored under any weighting without editing this file.

The third term is the one destination knowledge buys. Sending a passenger to a car whose
sweep already covers both their floors is nearly free; sending them to a car that has to
extend its sweep makes every passenger waiting on the far side of that car's reversal
wait longer. Only a scheduler that knows the destination up front can tell those apart.

Because it scores against real car geometry, its `estimated_wait_time` is a genuine ETA
rather than a distance guess, which finally makes `estimate_drift` in
`passenger_stats.json` (see outputs/runs/README.md) measure something.

Two things about the engine shape this file, and both are worth knowing before changing
it:

1. **The engine adds a passenger's destination to `stop_queue` only at boarding**
   (core/engine.py), not at assignment. A lobby car with eight people assigned and none
   boarded has `stop_queue == {1}` and looks completely idle. Scoring against
   `stop_queue` alone would therefore pile every up-peak request onto one car. The
   pledge ledger below closes that gap without touching the engine or the data model.

2. **Requests arriving on the same tick interact.** Committing one to a car moves that
   car's reversal point, which changes what the next one costs there. `assign_batch`
   (called by the engine, see schedulers/base.py) handles the tick as a batch instead of
   scoring each request against a stale snapshot.

Like `round_robin`, this scheduler treats the fleet as homogeneous -- it does not consult
`Elevator.serviceable_floors`, so it should not be paired with an express fleet (see
`express.py`, which owns that eligibility rule).
"""

from dataclasses import replace

from elevator_sim.core import trip_estimator as te
from elevator_sim.core.models import Elevator, Request
from .base import Scheduler

# Default relative weights of the three cost terms. Waiting at a floor with no
# information is worse than riding in a car that is visibly moving, so waiting is
# weighted heaviest; delay imposed on people who were already promised a car is weighted
# the same as the new passenger's own ride, so the scheduler won't wreck a committed
# route to shave a tick off one trip.
#
# These are defaults, not fixed rules -- an instance can be built with any weighting, and
# analysis/scripts/run_sweep.py --weights sweeps a table of presets so the settings can
# be compared on evidence rather than argued about. Only the ratios matter: the cost
# ranks candidate cars and is never reported, so scaling all three changes nothing.
W_WAIT = 1.0
W_TRAVEL = 0.5
W_FAIRNESS = 0.5


class DestinationDispatchScheduler(Scheduler):
    def __init__(
        self,
        w_wait: float = W_WAIT,
        w_travel: float = W_TRAVEL,
        w_fairness: float = W_FAIRNESS,
    ):
        self.w_wait = w_wait
        self.w_travel = w_travel
        self.w_fairness = w_fairness
        self._car_policy = None
        # elevator id -> {request id: (source, dest)} for requests this scheduler has
        # promised to a car but whose destination the engine has not yet committed.
        self._pledges: dict[str, dict[str, tuple[int, int]]] = {}

    def bind_car_policy(self, car_policy) -> None:
        """The cost model is only exact if it knows where cars reverse and whether they
        may detour, both of which are the car policy's rules, not the scheduler's."""
        self._car_policy = car_policy

    def assign(
        self, request: Request, elevators: list[Elevator], current_time: int, floors: int
    ) -> tuple[str, int]:
        return self.assign_batch([request], elevators, current_time, floors)[request.id]

    def assign_batch(
        self, requests: list[Request], elevators: list[Elevator], current_time: int, floors: int
    ) -> dict[str, tuple[str, int]]:
        """Cheapest-insertion assignment over one tick's requests.

        Two phases, on the observation that `extra_extent` splits requests cleanly:

        *Phase 1 -- free.* A request that costs its best car nothing (it nests inside a
        sweep that car is already committed to) can be committed straight away. It
        cannot make any other request more expensive on any other car, so there is
        nothing to gain by deferring it.

        *Phase 2 -- greedy.* Everything left extends some car's sweep, so the
        commitments interact and order matters. Repeatedly commit the single cheapest
        (request, car) pair available *right now*, then re-score what remains against
        the state that commit produced. This is cheapest insertion: not globally
        optimal, but it captures the interaction a one-shot scoring pass misses, and
        because every evaluation is closed-form arithmetic rather than a simulated run,
        the O(R^2 * C) of it is trivial at realistic batch sizes.

        A batch of one reduces to "pick the minimum-cost car", which is exactly what
        assign() promises -- there is only one scoring path in this file.
        """
        self._prune_pledges(elevators)
        rank = {e.id: index for index, e in enumerate(elevators)}
        states = {e.id: self._car_state(e, floors) for e in elevators}
        decisions: dict[str, tuple[str, int]] = {}

        extending = []
        for request in requests:
            car, result = self._best_car(states, rank, request)
            if result.delta_imposed_on_existing == 0 and result.extra_extent == 0:
                self._commit(states, decisions, car, request, result)
            else:
                extending.append(request)

        while extending:
            best = None
            for request in extending:
                car, result = self._best_car(states, rank, request)
                key = (self._cost(result), rank[car.id], request.id)
                if best is None or key < best[0]:
                    best = (key, request, car, result)

            _, request, car, result = best
            self._commit(states, decisions, car, request, result)
            extending = [r for r in extending if r.id != request.id]

        return decisions

    # -- scoring ---------------------------------------------------------------

    def _cost(self, result: te.InsertionResult) -> float:
        ride = result.ticks_to_dropoff - result.ticks_to_pickup
        return (
            self.w_wait * result.ticks_to_pickup
            + self.w_travel * ride
            + self.w_fairness * result.delta_imposed_on_existing
        )

    def _best_car(self, states, rank, request):
        """Minimum-cost car for one request, ties broken by fleet order (the same
        deterministic convention express.py uses).

        Cars already at capacity are skipped, since a passenger assigned to a full car
        just watches it go by (core/engine.py enforces capacity at boarding). If the
        entire fleet is full the filter is dropped rather than leaving the request
        unassigned -- the engine assigns every released passenger every tick, and an
        unassigned one would never be served.
        """
        candidates = [s for s in states.values() if s.load < s.capacity] or list(states.values())

        best = None
        for state in candidates:
            result = te.evaluate_insertion(state, request.source, request.dest)
            key = (self._cost(result), rank[state.id])
            if best is None or key < best[0]:
                best = (key, state, result)
        return best[1], best[2]

    def _commit(self, states, decisions, car, request, result):
        """Record an assignment and fold it into the hypothetical state the rest of the
        batch is scored against."""
        decisions[request.id] = (car.id, result.ticks_to_pickup)

        detour = car.detour
        if result.via_detour and detour is not None:
            detour = replace(detour, detours_remaining=detour.detours_remaining - 1)
        states[car.id] = replace(
            car,
            stops=car.stops | {request.source, request.dest},
            load=car.load + 1,
            detour=detour,
        )
        self._pledges.setdefault(car.id, {})[request.id] = (request.source, request.dest)

    # -- pledge ledger ---------------------------------------------------------

    def _car_state(self, elevator: Elevator, floors: int) -> te.CarState:
        pledged = self._pledges.get(elevator.id, {})
        return te.CarState(
            id=elevator.id,
            floor=elevator.current_floor,
            direction=elevator.direction,
            stops=frozenset(elevator.stop_queue) | {dest for _source, dest in pledged.values()},
            load=len(elevator.onboard) + len(pledged),
            capacity=elevator.capacity,
            floors=floors,
            geometry=getattr(self._car_policy, "reversal_geometry", te.LOOK),
            detour=self._detour_limits(elevator),
        )

    def _detour_limits(self, elevator: Elevator) -> te.DetourLimits | None:
        """Non-None only when the bound car policy can actually detour -- duck-typed so
        this file doesn't need to import (or know about) any particular policy."""
        limits_of = getattr(self._car_policy, "detour_limits", None)
        return limits_of(elevator) if limits_of is not None else None

    def _prune_pledges(self, elevators: list[Elevator]) -> None:
        """Drop pledges the engine has taken over, using only observable car state -- so
        the ledger cannot drift permanently out of step with the simulation.

        A pledge is live for exactly one window: from the moment this scheduler promises
        a car, until that passenger boards. Boarding is visible two ways, and either one
        retires the pledge: the passenger appears in `onboard` (at which point the engine
        has put their destination in `stop_queue` itself), or their source floor has left
        `stop_queue` entirely (they boarded and were dropped off between two calls).
        """
        for elevator in elevators:
            ledger = self._pledges.setdefault(elevator.id, {})
            onboard = {p.request.id for p in elevator.onboard}
            for request_id, (source, _dest) in list(ledger.items()):
                if request_id in onboard or source not in elevator.stop_queue:
                    del ledger[request_id]
