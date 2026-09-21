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

### The recommended configuration

`destination_dispatch` + `bounded_detour` is what `run_simulation.py` defaults to. Both
runs below use `sample_full_day_skyscraper50.csv` (62 requests, 50 floors) at 6 cars /
capacity 10 — the same configuration as the two `round_robin` baselines committed for
that scenario, so every comparison here changes exactly one thing.

- **`destination_dispatch_bounded_detour_full_day_skyscraper50/`** — the default
  configuration. Avg wait **4.9** ticks, max **28**, avg total 36.8. Against the
  `round_robin`+`look` baseline on identical input (22.1 / 81 / 55.5) that is a 78%
  cut in average wait and a 65% cut in the worst case.
- **`destination_dispatch_look_full_day_skyscraper50/`** — the same scheduler with plain
  `look`, isolating what the detour policy itself contributes: avg wait 5.3 against 4.9,
  same max. Its `estimate_drift` of avg 0.2 / max 8 against `round_robin`+`look`'s
  avg 9.6 is the sharper contrast — this scheduler's `estimated_wait_time` is a computed
  arrival, not a distance guess.

### Baselines it is measured against

- **`round_robin_scan_full_day_skyscraper50/`** and
  **`round_robin_look_full_day_skyscraper50/`** — the naive scheduler on the same
  scenario and configuration. Avg wait 25.7 and 22.1, max 81 for both.
- **`round_robin_scan_full_day/`** — `sample_full_day.csv` (44 requests, a full
  simulated day) with `round_robin` + `scan`. Avg wait 9.9 ticks, max 46.
- **`round_robin_look_full_day/`** — same scenario/input, swapping in `look` for `scan`.
  Avg wait 13.3 ticks, max 53 — slightly worse here despite `look`'s usually-shorter
  routes, since this scenario's mid-service reversal-forcing requests interact
  differently with `look`'s earlier turnarounds than with `scan`'s full sweeps.

### A second scenario, kept because it is not flattering

- **`destination_dispatch_look_full_day/`** and
  **`destination_dispatch_bounded_detour_full_day/`** — the same two configurations on
  `sample_full_day.csv` at 4 cars / capacity 8. Avg wait 4.3 and 7.7, max 22 and 34.

  Note the ordering: on *this* scenario `bounded_detour` is worse than plain `look`,
  the reverse of the skyscraper result above. The shipped cost weights
  (`1.0 / 0.25 / 0.25`) were chosen on the sweep-wide average and are the strongest
  setting on `sample_full_day_skyscraper50` and `sample_stress`, but only mid-table on
  `sample_full_day`. These runs are kept committed so that trade-off stays visible
  rather than buried — see `docs/cost_weights.html`.

The remaining folders are `round_robin` with each of `scan` and `look` over
`sample_capacity_overload` and `sample_downpeak_highrise40`.
