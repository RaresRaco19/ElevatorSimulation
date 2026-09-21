"""Tests for core/trip_estimator.py.

The central test here is TestTicksMatchesSimulation: every closed-form answer is
cross-checked against the real car policy, driven tick by tick over a frozen stop set.
The estimator claims to be *exact*, not close, so these assert equality -- a mismatch is
a bug in the formula, not a tolerance to widen.
"""

import itertools

import pytest

from elevator_sim.car_policies.look import LookPolicy
from elevator_sim.car_policies.scan import ScanPolicy
from elevator_sim.core import trip_estimator as te
from elevator_sim.core.models import Direction, Elevator

FLOORS = 10


def _walk_to(policy, floor, direction, stops, target, floors=FLOORS):
    """Drive `policy` tick by tick from `floor` with a *frozen* stop queue and return
    the tick at which the car first arrives at `target`.

    The queue is deliberately not consumed on arrival: trip_estimator.ticks() answers
    "when does this car reach floor X given this queue", so the comparison has to hold
    the queue still. That makes the walk non-terminating by construction (the car
    oscillates between its extents forever), hence the iteration cap."""
    elevator = Elevator(
        id="E1", current_floor=floor, capacity=99, direction=direction, stop_queue=set(stops)
    )
    for tick in range(0, 8 * floors):
        if elevator.current_floor == target:
            return tick
        step = policy.next_direction(elevator, tick, floors)
        elevator.direction = step
        if step is Direction.UP:
            elevator.current_floor += 1
        elif step is Direction.DOWN:
            elevator.current_floor -= 1
        else:
            return None  # parked without reaching the target
    return None


def _stop_sets():
    """A spread of queue shapes: empty, one-sided, straddling, and at the extremes."""
    return [
        frozenset(),
        frozenset({1}),
        frozenset({10}),
        frozenset({4}),
        frozenset({7}),
        frozenset({2, 9}),
        frozenset({3, 5, 8}),
        frozenset({1, 10}),
        frozenset({5}),
    ]


def _grid():
    positions = [1, 3, 5, 8, 10]
    directions = [Direction.UP, Direction.DOWN, Direction.IDLE]
    targets = [1, 2, 5, 6, 9, 10]
    return itertools.product(positions, directions, _stop_sets(), targets)


class TestTicksMatchesSimulation:
    """The closed form must reproduce the car policy exactly, for both geometries."""

    @pytest.mark.parametrize("floor,direction,stops,target", list(_grid()))
    def test_look_geometry(self, floor, direction, stops, target):
        queue = stops | {target}
        expected = _walk_to(LookPolicy(), floor, direction, queue, target)
        actual = te.ticks(floor, direction, stops, target, te.LOOK, FLOORS)
        assert actual == (0 if expected is None else expected)

    @pytest.mark.parametrize("floor,direction,stops,target", list(_grid()))
    def test_scan_geometry(self, floor, direction, stops, target):
        queue = stops | {target}
        expected = _walk_to(ScanPolicy(), floor, direction, queue, target)
        actual = te.ticks(floor, direction, stops, target, te.SCAN, FLOORS)
        assert actual == (0 if expected is None else expected)

    def test_a_walk_that_parks_is_a_zero_tick_answer(self):
        # The only case _walk_to returns None for: the target is the current floor and
        # nothing else is queued, so the policy idles rather than moving.
        assert _walk_to(LookPolicy(), 5, Direction.IDLE, {5}, 5) == 0
        assert te.ticks(5, Direction.IDLE, frozenset(), 5) == 0


class TestExtent:
    def test_up_takes_the_highest_committed_stop(self):
        assert te.extent(5, Direction.UP, {2, 7, 9}) == 9

    def test_down_takes_the_lowest_committed_stop(self):
        assert te.extent(5, Direction.DOWN, {2, 7, 9}) == 2

    def test_nothing_ahead_means_the_car_reverses_where_it_stands(self):
        assert te.extent(5, Direction.UP, {2, 3}) == 5
        assert te.extent(5, Direction.DOWN, {7, 9}) == 5

    def test_idle_has_no_extent(self):
        assert te.extent(5, Direction.IDLE, {2, 9}) == 5


class TestTicksClosedForm:
    def test_forward_target_is_plain_distance(self):
        assert te.ticks(5, Direction.UP, {8}, 8) == 3

    def test_backward_target_engages_the_reversal_branch(self):
        # Out to the extent at 8, then back down to 3: 3 + 5 = 8, i.e. 2U - c - t.
        assert te.ticks(5, Direction.UP, {3, 8}, 3) == 2 * 8 - 5 - 3 == 8

    def test_backward_target_with_nothing_ahead_collapses_to_distance(self):
        # LOOK reverses on this very tick, so the reversal branch must degrade to |c-t|.
        assert te.ticks(5, Direction.UP, {3}, 3) == 2

    def test_scan_runs_to_the_building_end_before_reversing(self):
        # SCAN ignores the queue when deciding where to turn: 5 -> 10 -> 3.
        assert te.ticks(5, Direction.UP, {3}, 3, te.SCAN, FLOORS) == 12

    def test_target_is_folded_into_the_queue(self):
        # Passing a target the caller forgot to commit must not change the answer.
        assert te.ticks(5, Direction.UP, {3, 8}, 9) == te.ticks(5, Direction.UP, {3, 8, 9}, 9)


def _car(floor, direction, stops, *, geometry=te.LOOK, detour=None, load=0, capacity=8):
    return te.CarState(
        id="E1",
        floor=floor,
        direction=direction,
        stops=frozenset(stops),
        load=load,
        capacity=capacity,
        floors=FLOORS,
        geometry=geometry,
        detour=detour,
    )


class TestEvaluateInsertion:
    def test_request_nested_in_the_current_sweep_is_free(self):
        # Car at 2 heading up to 9; a 4 -> 7 trip fits entirely inside that commitment.
        result = te.evaluate_insertion(_car(2, Direction.UP, {9}), source=4, dest=7)

        assert result.extra_extent == 0
        assert result.delta_imposed_on_existing == 0
        assert result.ticks_to_pickup == 2
        assert result.ticks_to_dropoff == 5

    def test_request_extending_the_sweep_charges_those_left_behind(self):
        # Car at 5 heading up, committed to 7 ahead and 2 behind. A 6 -> 9 trip pushes
        # the turn from 7 out to 9, so the stop at 2 waits an extra 2*2 ticks.
        result = te.evaluate_insertion(_car(5, Direction.UP, {2, 7}), source=6, dest=9)

        assert result.extra_extent == 2
        assert result.delta_imposed_on_existing == 4
        assert result.ticks_to_pickup == 1

    def test_request_behind_the_car_engages_the_reversal_branch(self):
        # Car at 5 heading up to 8; pickup at 3 is only reachable after the reversal.
        result = te.evaluate_insertion(_car(5, Direction.UP, {8}), source=3, dest=1)

        assert result.ticks_to_pickup == 2 * 8 - 5 - 3 == 8
        assert result.ticks_to_dropoff == 8 + 2

    def test_scan_geometry_never_reports_an_extension(self):
        # True SCAN was already going to the top, so nothing an insertion adds can
        # lengthen the sweep for anyone already aboard.
        result = te.evaluate_insertion(
            _car(5, Direction.UP, {2, 7}, geometry=te.SCAN), source=6, dest=9
        )

        assert result.extra_extent == 0
        assert result.delta_imposed_on_existing == 0

    def test_idle_car_simply_travels_to_the_pickup(self):
        result = te.evaluate_insertion(_car(5, Direction.IDLE, set()), source=8, dest=10)

        assert result.ticks_to_pickup == 3
        assert result.ticks_to_dropoff == 5
        assert result.delta_imposed_on_existing == 0

    def test_idle_car_with_a_committed_stop_still_charges_the_extension(self):
        # Car idle at 5 with a stop at 3; an 8 -> 8 insertion turns it upward first, so
        # the stop at 3 now waits 5 -> 8 -> 3 instead of 5 -> 3: six ticks more.
        result = te.evaluate_insertion(_car(5, Direction.IDLE, {3}), source=8, dest=8)

        assert result.extra_extent == 3
        assert result.delta_imposed_on_existing == 6


class TestDetourBranch:
    LIMITS = te.DetourLimits(max_distance=4, max_fairness_delay=8, detours_remaining=2)

    def test_eligible_backward_pickup_is_scored_one_way_not_round_trip(self):
        # Car at 5 heading up to 9, pickup at 3 behind it. Without a detour the
        # passenger waits out the reversal (2*9 - 5 - 3 = 10); with one they wait 2.
        car = _car(5, Direction.UP, {9}, detour=self.LIMITS)
        plain = te.evaluate_insertion(_car(5, Direction.UP, {9}), source=3, dest=1)
        detoured = te.evaluate_insertion(car, source=3, dest=1)

        assert plain.via_detour is False
        assert plain.ticks_to_pickup == 10
        assert detoured.via_detour is True
        assert detoured.ticks_to_pickup == 2

    def test_the_detour_charges_its_round_trip_to_everyone_else(self):
        car = _car(5, Direction.UP, {9}, detour=self.LIMITS)
        result = te.evaluate_insertion(car, source=3, dest=1)

        # One committed stop (9), delayed by the full 2*|5-3| round trip.
        assert result.delta_imposed_on_existing == te.detour_round_trip(5, 3) * 1 == 4

    def test_a_pickup_beyond_the_distance_bound_takes_the_plain_path(self):
        car = _car(9, Direction.UP, {10}, detour=self.LIMITS)
        result = te.evaluate_insertion(car, source=1, dest=2)  # 8 floors back, D = 4

        assert result.via_detour is False

    def test_no_detour_when_nothing_lies_ahead(self):
        # Nothing ahead means LOOK reverses anyway -- there is no sweep to interrupt.
        car = _car(5, Direction.UP, {2}, detour=self.LIMITS)
        result = te.evaluate_insertion(car, source=3, dest=1)

        assert result.via_detour is False

    def test_an_idle_car_never_detours(self):
        car = _car(5, Direction.IDLE, {8}, detour=self.LIMITS)
        result = te.evaluate_insertion(car, source=3, dest=1)

        assert result.via_detour is False


class TestDetourFairnessCollapse:
    """detour_eligible() checks the fairness bound once rather than once per passenger,
    on the claim that a detour delays every onboard passenger by exactly the same
    amount. That claim is load-bearing, so verify it directly."""

    CASES = [
        (5, Direction.UP, frozenset({2, 8, 9}), 3),
        (5, Direction.UP, frozenset({1, 4, 7}), 4),
        (7, Direction.DOWN, frozenset({2, 3, 9}), 9),
        (6, Direction.DOWN, frozenset({1, 5, 8, 10}), 8),
        (4, Direction.UP, frozenset({3, 6}), 3),
    ]

    @pytest.mark.parametrize("floor,direction,stops,detour_floor", CASES)
    @pytest.mark.parametrize("geometry", [te.LOOK, te.SCAN])
    def test_every_onboard_stop_is_delayed_by_exactly_the_round_trip(
        self, floor, direction, stops, detour_floor, geometry
    ):
        expected = te.detour_round_trip(floor, detour_floor)

        for target in stops - {detour_floor}:
            with_detour = te.ticks_with_detour(
                floor, direction, stops, target, detour_floor, geometry, FLOORS
            )
            without = te.ticks(floor, direction, stops, target, geometry, FLOORS)
            assert with_detour - without == expected

    @pytest.mark.parametrize("floor,direction,stops,detour_floor", CASES)
    def test_collapsed_gate_agrees_with_a_brute_force_per_passenger_check(
        self, floor, direction, stops, detour_floor
    ):
        for fairness in range(0, 13):
            limits = te.DetourLimits(
                max_distance=FLOORS, max_fairness_delay=fairness, detours_remaining=1
            )
            collapsed = te.detour_eligible(floor, detour_floor, limits)
            brute_force = all(
                te.ticks_with_detour(floor, direction, stops, t, detour_floor, te.LOOK, FLOORS)
                - te.ticks(floor, direction, stops, t, te.LOOK, FLOORS)
                <= fairness
                for t in stops - {detour_floor}
            )
            assert collapsed == brute_force

    def test_exhausted_budget_blocks_an_otherwise_fine_detour(self):
        spent = te.DetourLimits(max_distance=4, max_fairness_delay=8, detours_remaining=0)
        assert te.detour_eligible(5, 3, spent) is False

    def test_no_limits_means_no_detour(self):
        assert te.detour_eligible(5, 3, None) is False
