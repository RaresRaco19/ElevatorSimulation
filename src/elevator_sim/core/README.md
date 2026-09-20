# core/

The shared substrate every scheduler and car policy plugs into. Nothing here decides
*which* elevator gets a request (that's `schedulers/`) or *how* an elevator moves once
it has work (that's `car_policies/`) — `core/` owns everything else.

- **`models.py`** — plain dataclasses, no behavior: `Direction` (UP/DOWN/IDLE),
  `Request` (a parsed input row), `Elevator` (id, floor, capacity, `direction`,
  `onboard`, `stop_queue`), `Passenger` (a `Request` plus assignment/pickup/dropoff
  timestamps, with `actual_wait_time`/`travel_time`/`total_time` as derived
  properties), `Building` (floor count + elevator list).

- **`engine.py`** — `Simulation`, the tick loop. Each tick: releases due requests and
  hands each to the active `Scheduler` (capacity is *not* checked here — the engine
  just records whatever the scheduler decided); calls the active `CarMovementPolicy`
  once per elevator to get its direction and moves it one floor; boards/drops off
  passengers at floors an elevator is currently sitting on (capacity **is** enforced
  here — a full elevator simply won't board a waiting passenger); records a
  positions-log snapshot every tick; stops once every passenger has a `dropoff_time`.
  A `_MAX_TICKS_PER_FLOOR` safety cap raises `RuntimeError` instead of hanging forever
  if a car policy bug leaves a passenger unreachable.

- **`metrics.py`** — `compute_passenger_stats(passengers)`, a pure function (no file
  I/O) producing the aggregate stats dict (`count`, `wait_time`/`total_time`
  min/max/avg, `estimate_drift`) that `io.write_passenger_stats` serializes.

- **`io.py`** — the schema boundary: `load_requests` parses input CSVs;
  `write_positions_log` / `write_requests_copy` / `write_passenger_log` /
  `write_passenger_stats` / `write_run_config` write a run's output folder. Nothing
  else in the codebase touches the filesystem directly, so `analysis/` and `ui/` have
  one shared, stable contract to read.

## How it fits together

`run_simulation.py` calls `io.load_requests`, builds a `Simulation(building,
requests, scheduler, car_policy)`, runs it to completion, then calls `io.write_*` on
the results. `models.py` is the shared vocabulary everything else passes around.
