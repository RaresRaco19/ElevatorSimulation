# tests/

**Status: partly implemented.** `test_engine.py` is still a TODO comment; the other
three files are runnable.

- `test_trip_estimator.py` — covers `core/trip_estimator.py`. The central test drives
  `LookPolicy` and `ScanPolicy` tick by tick over a frozen stop queue and asserts the
  closed-form answer matches the simulated one **exactly**, across a grid of position ×
  heading × queue shape × target, for both geometries. The estimator claims to be exact,
  so a mismatch is a formula bug, not a tolerance to widen. Also checks the collapsed
  fairness gate in `detour_eligible()` against a brute-force per-passenger comparison,
  since the claim that one detour delays every onboard passenger identically is what
  lets that check be a single scalar.
- `test_schedulers.py` — one test class per scheduler (`round_robin`, `express`,
  `destination_dispatch`; `zone_based` still owes one). Each verifies every request
  submitted eventually gets served. `destination_dispatch` additionally cross-checks
  that a single request lands on the true minimum-cost car, that a batch of one reduces
  to that same answer, that the pledge ledger keeps a car's promised-but-not-boarded
  load visible, and that estimates track whichever car policy is bound.
- `test_car_policies.py` — one test class per policy (`look`, `bounded_detour`; `scan`
  and `fcfs` still owe one). Each verifies every committed stop is eventually visited
  (no starvation) and that direction only reverses per that policy's own rule.
  `bounded_detour` additionally asserts its `k * 2D` worst-case per-sweep delay bound
  holds against a plain LOOK baseline on the same queue.
- `test_engine.py` (TODO) — ticks advance one floor at a time; requests are never
  consumed ahead of their `time`; capacity is never exceeded; direction logic is
  respected; the simulation terminates once all known requests are served.

Run with:

```
PYTHONPATH=src pytest
```
