# Curated runs

A small, curated set of simulation runs is committed here so a reviewer can browse
results, run the analysis scripts, and use the `ui/` playback tool without having to
run the simulation themselves first.

Each run lives in its own folder, named `<scheduler>_<car_policy>_<scenario>/`, and
contains:

- `config.json` — scheduler, car_policy, elevators, floors, capacity, and input file used
- `positions_log.csv` — wide format, one row per time step, one column per elevator id
  (e.g. `time,E1,E2,E3`), per the assignment's own spec wording ("one row per timestamp,
  showing elevator positions at that time")
- `requests.csv` — the input requests for that run (`time,id,source,dest`), copied in so
  the run's folder is self-contained
- `passenger_log.csv` — one row per passenger, with full timing detail: `id, source,
  dest, request_time, elevator, estimated_wait_time, pickup_time, actual_wait_time,
  dropoff_time, travel_time, total_time`. `estimated_wait_time` is whichever number the
  *scheduler* that made the assignment reported (see
  `src/elevator_sim/schedulers/README.md`) — currently always `round_robin`'s naive
  `|elevator_floor - source|` guess that ignores the elevator's committed stops.
  Comparing `estimated_wait_time` against `actual_wait_time` is the point: it shows
  when a scheduler's promise didn't hold, and by how much.
- `passenger_stats.json` — aggregate over `passenger_log.csv`: min/max/avg `wait_time`
  and `total_time`, plus an `estimate_drift` summary (max/avg gap between estimated and
  actual wait, and how many passengers were delayed beyond their estimate).

These are regenerated directly into this folder by `src/elevator_sim/run_simulation.py`
(not auto-synced from ad-hoc runs elsewhere) — only promote a run here once it's worth
showing.

## Current runs

Building configuration (elevator count, floors, capacity) is whatever each run was
generated with — check that run's own `config.json` rather than assuming a number
here, since any of these can be (and have been) regenerated with different values.

- **`round_robin_scan_full_day/`** — `sample_full_day.csv` (44 requests, a full
  simulated day) with `round_robin` + `scan`. Avg wait 9.9 ticks, max 46.
- **`round_robin_look_full_day/`** — same scenario/input as `round_robin_scan_full_day/`,
  swapping in `look` for `scan` to compare directly. Avg wait 13.3 ticks, max 53 —
  slightly worse here despite `look`'s usually-shorter routes, since this scenario's
  mid-service reversal-forcing requests interact differently with `look`'s earlier
  turnarounds than with `scan`'s full sweeps.
- **`destination_dispatch_look_full_day/`** — same scenario, input and configuration as
  the two runs above (`sample_full_day.csv`, 4 cars, capacity 8), swapping
  `round_robin` for `destination_dispatch` so the scheduler is the only variable. Avg
  wait 4.9 ticks against `round_robin`+`look`'s 13.3, max 30 against 53. The
  `estimate_drift` contrast is the sharper one — avg 0.1 / max 2 against avg 5.4 /
  max 50 — because this scheduler's `estimated_wait_time` is a computed arrival rather
  than a distance guess.
- **`destination_dispatch_bounded_detour_full_day/`** — same again, now swapping `look`
  for `bounded_detour` so the *car policy* is the only variable. Avg wait 4.0 ticks, and
  max wait drops from 30 to 19: the tail is where letting a car turn back for a stop it
  has just passed actually pays, which is what that policy exists for.

The remaining folders are `round_robin` with each of `scan` and `look` over
`sample_capacity_overload`, `sample_downpeak_highrise40` and
`sample_full_day_skyscraper50`.
