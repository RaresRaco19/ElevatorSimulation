# TODO: one test class per scheduler in src/elevator_sim/schedulers/
# (round_robin, zone_based, express) — each should at minimum verify
# every request submitted ends up served (assignment's "no indefinite wait" requirement).

from collections import Counter

import pytest

from elevator_sim.core.models import Elevator, Request
from elevator_sim.schedulers.express import ExpressScheduler, NoEligibleElevatorError, express_floor_set
from elevator_sim.schedulers.round_robin import RoundRobinScheduler


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
