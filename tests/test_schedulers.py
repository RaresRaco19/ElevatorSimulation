# TODO: one test class per scheduler in src/elevator_sim/schedulers/
# (round_robin, zone_based, express) — each should at minimum verify
# every request submitted ends up served (assignment's "no indefinite wait" requirement).

from collections import Counter

from elevator_sim.core.models import Elevator, Request
from elevator_sim.schedulers.round_robin import RoundRobinScheduler


def _elevators(n, capacity):
    return [Elevator(id=f"E{i + 1}", current_floor=1, capacity=capacity) for i in range(n)]


def _requests(n, source=1, dest=10):
    return [Request(time=0, id=f"R{i + 1}", source=source, dest=dest) for i in range(n)]


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
