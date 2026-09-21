# TODO: one test class per scheduler in src/elevator_sim/schedulers/
# (round_robin, zone_based, express) — each should at minimum verify
# every request submitted ends up served (assignment's "no indefinite wait" requirement).
#
# Done so far: round_robin, express, destination_dispatch. zone_based still owes a class.

from collections import Counter
from pathlib import Path

import pytest

from elevator_sim.car_policies.bounded_detour import BoundedDetourPolicy
from elevator_sim.car_policies.look import LookPolicy
from elevator_sim.car_policies.scan import ScanPolicy
from elevator_sim.core import io, metrics
from elevator_sim.core import trip_estimator as te
from elevator_sim.core.engine import Simulation
from elevator_sim.core.models import Building, Direction, Elevator, Passenger, Request
from elevator_sim.schedulers import destination_dispatch as dd
from elevator_sim.schedulers.destination_dispatch import DestinationDispatchScheduler
from elevator_sim.schedulers.express import ExpressScheduler, NoEligibleElevatorError, express_floor_set
from elevator_sim.schedulers.round_robin import RoundRobinScheduler

ROOT = Path(__file__).resolve().parents[1]
FLOORS = 20

# (floors, elevators, capacity) per scenario, matching data/requests/README.md's
# recommended configuration for each.
DD_SCENARIOS = {
    "sample_full_day.csv": (35, 4, 8),
    "sample_uppeak_highrise30.csv": (30, 4, 10),
    "sample_downpeak_highrise40.csv": (40, 5, 10),
    "sample_capacity_overload.csv": (15, 2, 4),
    "sample_single_elevator_bottleneck.csv": (15, 1, 6),
}


def _elevators(n, capacity):
    return [Elevator(id=f"E{i + 1}", current_floor=1, capacity=capacity) for i in range(n)]


def _requests(n, source=1, dest=10):
    return [Request(time=0, id=f"R{i + 1}", source=source, dest=dest) for i in range(n)]


def _express_elevator(elevator_id, current_floor=1, capacity=4, floors=16, stride=5):
    return Elevator(
        id=elevator_id,
        current_floor=current_floor,
        capacity=capacity,
        serviceable_floors=express_floor_set(floors, stride),
    )


def _regular_elevator(elevator_id, current_floor=1, capacity=4):
    return Elevator(id=elevator_id, current_floor=current_floor, capacity=capacity)


class TestRoundRobinScheduler:
    def test_same_tick_batch_does_not_exceed_capacity(self):
        scheduler = RoundRobinScheduler()
        elevators = _elevators(n=3, capacity=4)

        assignments = [
            scheduler.assign(r, elevators, current_time=0, floors=10) for r in _requests(10)
        ]

        counts = Counter(elevator_id for elevator_id, _ in assignments)
        assert all(count <= 4 for count in counts.values())
        assert sum(counts.values()) == 10

    def test_overflow_rotates_to_next_elevators_in_order(self):
        scheduler = RoundRobinScheduler()
        elevators = _elevators(n=3, capacity=4)

        assignments = [
            scheduler.assign(r, elevators, current_time=0, floors=10) for r in _requests(10)
        ]

        assigned_ids = [elevator_id for elevator_id, _ in assignments]
        assert assigned_ids == ["E1"] * 4 + ["E2"] * 4 + ["E3"] * 2

    def test_single_elevator_still_serves_every_request(self):
        scheduler = RoundRobinScheduler()
        elevators = _elevators(n=1, capacity=4)

        assignments = [
            scheduler.assign(r, elevators, current_time=0, floors=10) for r in _requests(10)
        ]

        assert [elevator_id for elevator_id, _ in assignments] == ["E1"] * 10

    def test_different_ticks_do_not_share_a_batch(self):
        scheduler = RoundRobinScheduler()
        elevators = _elevators(n=3, capacity=4)

        first = scheduler.assign(_requests(1)[0], elevators, current_time=0, floors=10)
        # A second same-tick request reuses the same car (capacity 4, only 2 used so far).
        scheduler.assign(_requests(1)[0], elevators, current_time=0, floors=10)
        # A new tick should start a fresh batch, even though capacity is not exhausted.
        second = scheduler.assign(_requests(1)[0], elevators, current_time=1, floors=10)

        assert first[0] == "E1"
        assert second[0] == "E2"


class TestExpressFloorSet:
    def test_default_stride_16_floors(self):
        assert express_floor_set(16) == frozenset({1, 6, 11, 16})

    def test_top_floor_not_aligned_to_stride_is_excluded(self):
        assert express_floor_set(10, 5) == frozenset({1, 6})

    def test_small_building_still_includes_lobby(self):
        assert express_floor_set(5, 5) == frozenset({1})

    def test_custom_stride(self):
        assert express_floor_set(20, 3) == frozenset({1, 4, 7, 10, 13, 16, 19})

    def test_single_floor_building(self):
        assert express_floor_set(1, 5) == frozenset({1})

    def test_invalid_floors_raises(self):
        with pytest.raises(ValueError):
            express_floor_set(0)

    def test_invalid_stride_raises(self):
        with pytest.raises(ValueError):
            express_floor_set(16, stride=0)


class TestExpressScheduler:
    def test_request_between_two_express_floors_goes_to_express_car(self):
        scheduler = ExpressScheduler()
        elevators = [_express_elevator("EXPRESS"), _regular_elevator("REGULAR")]

        elevator_id, _ = scheduler.assign(
            Request(time=0, id="R1", source=6, dest=11), elevators, current_time=0, floors=16
        )

        assert elevator_id == "EXPRESS"

    def test_request_needing_non_express_source_falls_back_to_regular_car(self):
        scheduler = ExpressScheduler()
        elevators = [_express_elevator("EXPRESS"), _regular_elevator("REGULAR")]

        elevator_id, _ = scheduler.assign(
            Request(time=0, id="R1", source=2, dest=6), elevators, current_time=0, floors=16
        )

        assert elevator_id == "REGULAR"

    def test_request_needing_non_express_dest_falls_back_to_regular_car(self):
        scheduler = ExpressScheduler()
        elevators = [_express_elevator("EXPRESS"), _regular_elevator("REGULAR")]

        elevator_id, _ = scheduler.assign(
            Request(time=0, id="R1", source=6, dest=8), elevators, current_time=0, floors=16
        )

        assert elevator_id == "REGULAR"

    def test_nearest_eligible_car_by_distance_wins(self):
        scheduler = ExpressScheduler()
        elevators = [
            _express_elevator("FAR", current_floor=1),
            _express_elevator("NEAR", current_floor=11),
        ]

        elevator_id, _ = scheduler.assign(
            Request(time=0, id="R1", source=11, dest=16), elevators, current_time=0, floors=16
        )

        assert elevator_id == "NEAR"

    def test_tie_breaks_by_elevators_list_order(self):
        scheduler = ExpressScheduler()
        elevators = [
            _express_elevator("FIRST", current_floor=1),
            _express_elevator("SECOND", current_floor=1),
        ]

        elevator_id, _ = scheduler.assign(
            Request(time=0, id="R1", source=1, dest=6), elevators, current_time=0, floors=16
        )

        assert elevator_id == "FIRST"

    def test_all_express_fleet_serves_burst_without_starvation(self):
        scheduler = ExpressScheduler()
        elevators = [_express_elevator(f"E{i + 1}") for i in range(3)]
        requests = [
            Request(time=0, id=f"R{i + 1}", source=1, dest=[6, 11, 16][i % 3]) for i in range(10)
        ]

        assignments = [
            scheduler.assign(r, elevators, current_time=0, floors=16) for r in requests
        ]

        assert len(assignments) == 10
        assert all(elevator_id in {"E1", "E2", "E3"} for elevator_id, _ in assignments)

    def test_no_eligible_elevator_raises_for_all_express_fleet(self):
        scheduler = ExpressScheduler()
        elevators = [_express_elevator("E1"), _express_elevator("E2")]

        with pytest.raises(NoEligibleElevatorError):
            scheduler.assign(
                Request(time=0, id="R1", source=2, dest=3), elevators, current_time=0, floors=16
            )

    def test_estimated_wait_time_is_distance_to_source(self):
        scheduler = ExpressScheduler()
        elevators = [_regular_elevator("E1", current_floor=4)]

        _, estimated_wait_time = scheduler.assign(
            Request(time=0, id="R1", source=9, dest=10), elevators, current_time=0, floors=16
        )

        assert estimated_wait_time == 5

    def test_mixed_fleet_every_request_gets_a_valid_eligible_assignment(self):
        scheduler = ExpressScheduler()
        elevators = [_express_elevator("EXPRESS"), _regular_elevator("REGULAR")]
        requests = [
            Request(time=0, id="R1", source=1, dest=6),
            Request(time=0, id="R2", source=2, dest=9),
            Request(time=0, id="R3", source=11, dest=16),
            Request(time=0, id="R4", source=3, dest=14),
        ]

        for request in requests:
            elevator_id, _ = scheduler.assign(request, elevators, current_time=0, floors=16)
            elevator = next(e for e in elevators if e.id == elevator_id)
            assert ExpressScheduler._can_serve(elevator, request)


def _dispatcher(car_policy=None):
    scheduler = DestinationDispatchScheduler()
    if car_policy is not None:
        scheduler.bind_car_policy(car_policy)
    return scheduler


def _car(elevator_id, floor, *, direction=Direction.IDLE, stops=(), capacity=8, onboard=()):
    return Elevator(
        id=elevator_id,
        current_floor=floor,
        capacity=capacity,
        direction=direction,
        onboard=list(onboard),
        stop_queue=set(stops),
    )


def _cost_of(elevator, request, floors=FLOORS):
    """The cost function applied from outside the scheduler, for cross-checking which
    car it picks."""
    state = te.CarState(
        id=elevator.id,
        floor=elevator.current_floor,
        direction=elevator.direction,
        stops=frozenset(elevator.stop_queue),
        load=len(elevator.onboard),
        capacity=elevator.capacity,
        floors=floors,
    )
    result = te.evaluate_insertion(state, request.source, request.dest)
    return (
        dd.W_WAIT * result.ticks_to_pickup
        + dd.W_TRAVEL * (result.ticks_to_dropoff - result.ticks_to_pickup)
        + dd.W_FAIRNESS * result.delta_imposed_on_existing
    )


class TestDestinationDispatchScheduler:
    def test_single_request_goes_to_the_minimum_cost_car(self):
        """A batch of one has to reduce to plain argmin over the cost function -- the
        invariant that keeps assign() and assign_batch() from drifting apart."""
        elevators = [
            _car("E1", 2, direction=Direction.UP, stops=(15,)),
            _car("E2", 9, direction=Direction.DOWN, stops=(4,)),
            _car("E3", 18),
        ]
        request = Request(time=0, id="R1", source=6, dest=11)

        chosen, _ = _dispatcher(LookPolicy()).assign(request, elevators, 0, FLOORS)

        costs = {e.id: _cost_of(e, request) for e in elevators}
        assert chosen == min(costs, key=lambda elevator_id: costs[elevator_id])

    def test_batch_of_one_matches_the_single_request_path(self):
        request = Request(time=0, id="R1", source=6, dest=11)

        def fleet():
            return [
                _car("E1", 2, direction=Direction.UP, stops=(15,)),
                _car("E2", 9, direction=Direction.DOWN, stops=(4,)),
            ]

        single = _dispatcher(LookPolicy()).assign(request, fleet(), 0, FLOORS)
        batched = _dispatcher(LookPolicy()).assign_batch([request], fleet(), 0, FLOORS)

        assert batched == {request.id: single}

    def test_prefers_a_car_whose_sweep_already_covers_the_trip(self):
        """E2 stands nearer the pickup, but taking the trip drags its sweep out past 8
        and makes the stop at 1 behind it wait; E1 already runs to 10, so the same trip
        costs nobody anything. Only a scheduler that knows the destination up front can
        tell those two apart."""
        elevators = [
            _car("E1", 3, direction=Direction.UP, stops=(10,)),
            _car("E2", 4, direction=Direction.UP, stops=(1, 6)),
        ]

        chosen, _ = _dispatcher(LookPolicy()).assign(
            Request(time=0, id="R1", source=5, dest=8), elevators, 0, FLOORS
        )

        assert chosen == "E1"

    def test_skips_a_car_that_is_already_full(self):
        aboard = [
            Passenger(request=Request(time=0, id=f"X{i}", source=5, dest=9)) for i in range(2)
        ]
        elevators = [
            _car("E1", 5, capacity=2, onboard=aboard, stops=(9,)),  # sitting on the pickup
            _car("E2", 12, capacity=2),
        ]

        chosen, _ = _dispatcher(LookPolicy()).assign(
            Request(time=0, id="R1", source=5, dest=9), elevators, 0, FLOORS
        )

        assert chosen == "E2"

    def test_a_pledged_destination_counts_toward_a_car_load(self):
        """core/engine.py only puts a destination in stop_queue at boarding, so without
        the ledger a car with every seat promised but nobody aboard still reads as
        empty -- and an up-peak burst piles onto one car."""
        scheduler = _dispatcher(LookPolicy())
        elevators = [_car("E1", 1, capacity=1), _car("E2", 1, capacity=1)]
        first_request = Request(time=0, id="R1", source=1, dest=15)

        first, _ = scheduler.assign(first_request, elevators, 0, FLOORS)
        elevators[0].stop_queue.add(first_request.source)  # what the engine does next

        second, _ = scheduler.assign(
            Request(time=1, id="R2", source=1, dest=16), elevators, 1, FLOORS
        )

        assert first == "E1"
        assert second == "E2"

    def test_a_pledged_destination_is_visible_to_the_next_estimate(self):
        scheduler = _dispatcher(LookPolicy())
        car = _car("E1", 1)
        scheduler.assign(Request(time=0, id="R1", source=1, dest=15), [car], 0, FLOORS)
        car.stop_queue.add(1)

        assert 15 in scheduler._car_state(car, FLOORS).stops

    def test_a_pledge_is_retired_once_the_passenger_boards(self):
        scheduler = _dispatcher(LookPolicy())
        request = Request(time=0, id="R1", source=1, dest=15)
        car = _car("E1", 1, capacity=4)
        scheduler.assign(request, [car], 0, FLOORS)
        car.stop_queue.add(1)

        assert scheduler._car_state(car, FLOORS).load == 1

        # The engine boards the passenger: the destination joins stop_queue, the source
        # leaves it. The pledge has to retire, or the car is counted as carrying two.
        car.onboard.append(Passenger(request=request))
        car.stop_queue = {15}
        scheduler._prune_pledges([car])

        assert scheduler._car_state(car, FLOORS).load == 1
        assert scheduler._car_state(car, FLOORS).stops == frozenset({15})

    def test_same_tick_batch_accounts_for_its_own_commitments(self):
        """Two simultaneous requests must not both be scored against the same untouched
        car: committing the first one changes what the second costs."""
        elevators = [_car("E1", 1, capacity=1), _car("E2", 1, capacity=1)]
        requests = [
            Request(time=0, id="R1", source=1, dest=15),
            Request(time=0, id="R2", source=1, dest=16),
        ]

        decisions = _dispatcher(LookPolicy()).assign_batch(requests, elevators, 0, FLOORS)

        assert {elevator_id for elevator_id, _ in decisions.values()} == {"E1", "E2"}
        assert set(decisions) == {"R1", "R2"}

    def test_estimate_follows_the_bound_policy_reversal_rule(self):
        """The same car and the same request, priced against two movement rules: LOOK
        turns at its last stop, SCAN runs to the top of the building first."""
        elevators = [_car("E1", 5, direction=Direction.UP, stops=(9,))]
        request = Request(time=0, id="R1", source=3, dest=1)

        _, look_eta = _dispatcher(LookPolicy()).assign(request, elevators, 0, FLOORS)
        _, scan_eta = _dispatcher(ScanPolicy()).assign(request, elevators, 0, FLOORS)

        assert look_eta == 2 * 9 - 5 - 3
        assert scan_eta == 2 * FLOORS - 5 - 3

    def test_prices_a_detour_capable_car_at_the_detour_cost(self):
        """Integration point 2. Without it the dispatcher assumes every pickup behind a
        car must wait out a full reversal, and so systematically passes over exactly the
        cars best placed to take it."""
        elevators = [_car("E1", 5, direction=Direction.UP, stops=(9,))]
        request = Request(time=0, id="R1", source=3, dest=1)

        _, look_eta = _dispatcher(LookPolicy()).assign(request, elevators, 0, FLOORS)
        _, detour_eta = _dispatcher(BoundedDetourPolicy()).assign(request, elevators, 0, FLOORS)

        assert look_eta == 10  # out to the reversal at 9, then back down to 3
        assert detour_eta == 2  # turn back now

    @pytest.mark.parametrize("scenario", sorted(DD_SCENARIOS))
    @pytest.mark.parametrize("policy", [ScanPolicy, LookPolicy, BoundedDetourPolicy])
    def test_every_request_is_served_under_every_car_policy(self, scenario, policy):
        """The assignment's "no indefinite wait" requirement, end to end."""
        floors, cars, capacity = DD_SCENARIOS[scenario]
        requests = io.load_requests(ROOT / "data" / "requests" / scenario)
        building = Building(
            floors=floors,
            elevators=[
                Elevator(id=f"E{i + 1}", current_floor=1, capacity=capacity) for i in range(cars)
            ],
        )

        passengers, _ = Simulation(
            building, requests, DestinationDispatchScheduler(), policy()
        ).run()

        assert len(passengers) == len(requests)
        assert all(p.dropoff_time is not None for p in passengers)
        assert all(p.pickup_time >= p.request.time for p in passengers)

    def test_estimates_are_more_accurate_than_the_naive_distance_guess(self):
        """estimated_wait_time is the scheduler's own promise (see
        outputs/runs/README.md's estimate_drift). round_robin guesses plain distance;
        this one computes the arrival it actually expects, so the gap should shrink
        sharply on the same scenario."""
        requests = io.load_requests(ROOT / "data" / "requests" / "sample_full_day.csv")

        def drift(scheduler):
            building = Building(
                floors=35,
                elevators=[Elevator(id=f"E{i + 1}", current_floor=1, capacity=8) for i in range(4)],
            )
            passengers, _ = Simulation(building, requests, scheduler, LookPolicy()).run()
            return metrics.compute_passenger_stats(passengers)["estimate_drift"]["avg"]

        assert drift(DestinationDispatchScheduler()) < drift(RoundRobinScheduler())
