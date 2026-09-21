# TODO: one test class per policy in src/elevator_sim/car_policies/
# (scan, look, fcfs) — each should at minimum verify every committed stop on an
# elevator is eventually visited (no starvation) and that direction only reverses
# when that policy's rule says it should (e.g. scan.py only reverses at a terminal
# floor with no further stops in the current direction; look.py reverses as soon as
# there are no more stops further in the current direction).
#
# Done so far: look and bounded_detour. scan and fcfs still owe a class each.

import pytest

from elevator_sim.car_policies.bounded_detour import BoundedDetourPolicy
from elevator_sim.car_policies.look import LookPolicy, look_direction
from elevator_sim.core.models import Direction, Elevator

FLOORS = 20


def _drive(policy, floor, stops, direction=Direction.IDLE, floors=FLOORS, max_ticks=400):
    """Run a single car to completion the way core/engine.py does: serve (and clear) the
    stop under the car, then ask the policy for one floor of movement.

    `direction` seeds the car's heading -- pass UP or DOWN to start it already mid-sweep,
    since a car that is still idle has no sweep for a detour to interrupt.

    Returns (path, arrivals): every floor occupied in order, and the tick each stop was
    served on."""
    elevator = Elevator(
        id="E1", current_floor=floor, capacity=99, direction=direction, stop_queue=set(stops)
    )
    path, arrivals = [floor], {}

    for tick in range(max_ticks):
        if elevator.current_floor in elevator.stop_queue:
            arrivals[elevator.current_floor] = tick
            elevator.stop_queue.discard(elevator.current_floor)
        if not elevator.stop_queue:
            return path, arrivals

        step = policy.next_direction(elevator, tick, floors)
        elevator.direction = step
        if step == Direction.UP:
            elevator.current_floor += 1
        elif step == Direction.DOWN:
            elevator.current_floor -= 1
        else:
            pytest.fail(f"policy idled at {elevator.current_floor} with stops {elevator.stop_queue}")
        path.append(elevator.current_floor)

    pytest.fail(f"policy did not clear {elevator.stop_queue} within {max_ticks} ticks")


class TestLookPolicy:
    """Guards the extraction of look_direction() out of LookPolicy -- the rule itself is
    unchanged, so these pin the behaviour the refactor had to preserve."""

    def test_continues_while_stops_remain_ahead(self):
        elevator = Elevator(
            id="E1", current_floor=5, capacity=8, direction=Direction.UP, stop_queue={3, 8}
        )
        assert LookPolicy().next_direction(elevator, 0, FLOORS) == Direction.UP

    def test_reverses_as_soon_as_nothing_remains_ahead(self):
        elevator = Elevator(
            id="E1", current_floor=5, capacity=8, direction=Direction.UP, stop_queue={3}
        )
        assert LookPolicy().next_direction(elevator, 0, FLOORS) == Direction.DOWN

    def test_idle_car_heads_toward_its_first_stop(self):
        elevator = Elevator(id="E1", current_floor=5, capacity=8, stop_queue={2})
        assert LookPolicy().next_direction(elevator, 0, FLOORS) == Direction.DOWN

    def test_no_stops_means_idle(self):
        elevator = Elevator(id="E1", current_floor=5, capacity=8)
        assert LookPolicy().next_direction(elevator, 0, FLOORS) == Direction.IDLE

    def test_policy_and_extracted_function_agree(self):
        for direction in (Direction.UP, Direction.DOWN, Direction.IDLE):
            for stops in ({3, 8}, {3}, {8}, {5}, set()):
                elevator = Elevator(
                    id="E1", current_floor=5, capacity=8, direction=direction, stop_queue=set(stops)
                )
                assert LookPolicy().next_direction(elevator, 0, FLOORS) == look_direction(
                    5, direction, stops
                )

    def test_every_committed_stop_is_eventually_served(self):
        _, arrivals = _drive(LookPolicy(), 10, {2, 4, 9, 15, 19})
        assert set(arrivals) == {2, 4, 9, 15, 19}


class TestBoundedDetourPolicy:
    D, K, F = 4, 2, 8

    def _policy(self):
        return BoundedDetourPolicy(
            max_detour_distance=self.D, max_detours_per_sweep=self.K, max_fairness_delay=self.F
        )

    def _mid_sweep_car(self, floor=10, stops=(8, 9, 18)):
        return Elevator(
            id="E1", current_floor=floor, capacity=8, direction=Direction.UP, stop_queue=set(stops)
        )

    def test_turns_back_for_a_stop_just_behind_it(self):
        policy = self._policy()
        assert policy.next_direction(self._mid_sweep_car(), 0, FLOORS) == Direction.DOWN

    def test_picks_the_nearest_eligible_stop_behind_it(self):
        policy = self._policy()
        elevator = self._mid_sweep_car(stops=(7, 9, 18))
        policy.next_direction(elevator, 0, FLOORS)

        assert policy._sweeps["E1"].target == 9

    def test_ignores_a_stop_beyond_the_distance_bound(self):
        # 3 is 7 floors back, outside D = 4, so the sweep to 18 continues.
        policy = self._policy()
        assert policy.next_direction(self._mid_sweep_car(stops=(3, 18)), 0, FLOORS) == Direction.UP

    def test_does_not_divert_when_nothing_lies_ahead(self):
        # With no forward work, LOOK reverses anyway -- there is no sweep to interrupt,
        # so this must be an ordinary reversal and must not spend any budget.
        policy = self._policy()
        elevator = self._mid_sweep_car(stops=(8, 9))

        assert policy.next_direction(elevator, 0, FLOORS) == Direction.DOWN
        assert policy._sweeps["E1"].target is None
        assert policy.detour_limits(elevator).detours_remaining == self.K

    def test_an_idle_car_never_diverts(self):
        policy = self._policy()
        elevator = Elevator(id="E1", current_floor=10, capacity=8, stop_queue={9, 18})

        policy.next_direction(elevator, 0, FLOORS)
        assert policy._sweeps["E1"].target is None

    def test_resumes_the_original_sweep_after_serving_the_diversion(self):
        # The engine overwrites Elevator.direction with whatever the policy returned, so
        # after a diversion the car itself no longer knows which way it was sweeping --
        # the policy has to remember. 10 -> 9 -> 8 -> up to 18.
        path, arrivals = _drive(self._policy(), 10, {8, 9, 18}, Direction.UP)

        assert path[:3] == [10, 9, 8]
        assert path[-1] == 18
        assert arrivals[9] < arrivals[8] < arrivals[18]

    def test_spends_at_most_k_diversions_per_sweep(self):
        policy = self._policy()
        elevator = self._mid_sweep_car(stops=(6, 7, 8, 9, 18))

        for tick in range(60):
            if elevator.current_floor in elevator.stop_queue:
                elevator.stop_queue.discard(elevator.current_floor)
            if not elevator.stop_queue:
                break
            step = policy.next_direction(elevator, tick, FLOORS)
            elevator.direction = step
            elevator.current_floor += step.value
            assert policy._sweeps["E1"].used <= self.K

    def test_worst_case_delay_over_one_sweep_is_bounded_by_k_times_2d(self):
        """The guarantee the three bounds exist to provide: within a single sweep, a
        passenger already aboard loses at most k * 2D ticks to other people's
        diversions. Checkable exactly rather than statistically, because every quantity
        involved is closed-form."""
        stops = {8, 9, 18}

        _, detoured = _drive(self._policy(), 10, stops, Direction.UP)
        _, plain = _drive(LookPolicy(), 10, stops, Direction.UP)

        # 18 is the far end of the sweep, so its arrival absorbs every diversion taken.
        assert detoured[18] - plain[18] <= self.K * 2 * self.D
        assert detoured[18] > plain[18]  # it really did divert, so this isn't vacuous

    def test_budget_refreshes_on_a_natural_reversal(self):
        policy = self._policy()
        elevator = self._mid_sweep_car(stops=(9, 12))

        policy.next_direction(elevator, 0, FLOORS)  # diverts down to 9
        assert policy.detour_limits(elevator).detours_remaining == self.K - 1

        elevator.current_floor, elevator.stop_queue = 12, {4}
        elevator.direction = Direction.UP
        policy._sweeps["E1"].target = None
        policy.next_direction(elevator, 1, FLOORS)  # nothing above 12: LOOK reverses

        assert policy.detour_limits(elevator).detours_remaining == self.K

    def test_diversions_never_starve_a_committed_stop(self):
        _, arrivals = _drive(self._policy(), 10, {2, 4, 9, 11, 12, 15, 19}, Direction.UP)
        assert set(arrivals) == {2, 4, 9, 11, 12, 15, 19}

    def test_each_car_keeps_its_own_budget(self):
        policy = self._policy()
        first = self._mid_sweep_car()
        second = Elevator(
            id="E2", current_floor=10, capacity=8, direction=Direction.UP, stop_queue={18}
        )

        policy.next_direction(first, 0, FLOORS)

        assert policy.detour_limits(first).detours_remaining == self.K - 1
        assert policy.detour_limits(second).detours_remaining == self.K
