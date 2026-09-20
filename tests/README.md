# tests/

**Status: not implemented yet.** All three files below are TODO comments describing
intended test coverage, not runnable test code — `pytest` would currently collect
zero tests here.

- `test_engine.py` — ticks advance one floor at a time; requests are never consumed
  ahead of their `time`; capacity is never exceeded; direction logic is respected;
  the simulation terminates once all known requests are served.
- `test_schedulers.py` — one test class per scheduler in `src/elevator_sim/schedulers/`
  (`round_robin`, and eventually `zone_based`, `express`); each should
  at minimum verify every request submitted eventually gets served.
- `test_car_policies.py` — one test class per policy in
  `src/elevator_sim/car_policies/` (`scan`, and eventually `look`, `fcfs`); each
  should verify every committed stop is eventually visited (no starvation) and that
  direction only reverses per that policy's own rule.

Once written, run with:

```
PYTHONPATH=src pytest
```
