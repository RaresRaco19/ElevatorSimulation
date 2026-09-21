# Analysis

Charts generated from a full config sweep across every scenario in `data/requests/`.

## Scripts

- `scripts/run_sweep.py` — batch-runs every scenario in `data/requests/` across
  elevators 1-10 x capacity {3, 5, 8, 13}, for every implemented (scheduler,
  car_policy) pair — currently the full grid of {`round_robin`,
  `destination_dispatch`} x {`scan`, `look`, `bounded_detour`}, 6 pairs and ~2640
  configs in about half a minute. Writes a
  full run output (matching `run_simulation.py`'s own 5-file shape) for every config
  that converges under `outputs/sweep/<scenario>/<scheduler>_<car_policy>/
  e<elevators>_c<capacity>/`, plus `outputs/sweep/manifest.json` — a flat JSON index of
  every attempted config (converged or not) with that run's `passenger_stats.json`
  inlined. This is the prerequisite step for both scripts below, and for the `ui/`
  playback app's "Sweep" mode.
- `scripts/compare_schedulers.py` — reads `manifest.json` and aggregates one score per
  (scheduler, car_policy) pair, averaged across the **entire** sweep by default (every
  scenario x every elevator count x every capacity). Reports two separate bar charts —
  avg `total_time` and avg `wait_time` — rather than blending them into one number.
  `--min-elevators N` restricts this to configs with more than N elevators (elevators
  > N, exclusive) — e.g. to see how the pairs compare once a building is reasonably
  resourced, excluding small fleets that can be dominated by bottleneck effects.
  `--max-elevators N` caps it at N elevators (elevators <= N, inclusive) — the mirror
  case, e.g. to see how the pairs compare under a resourcing ceiling. The two are
  combinable for a range (`--min-elevators 2 --max-elevators 6`). Filtered runs write
  distinctly-named files (`..._min_elevators_N.png`, `..._max_elevators_N.png`, or
  both combined) rather than overwriting the full-sweep comparison.
- `scripts/plot_wait_times.py` — elevators (1-10) on the X axis, one trace per
  capacity (3/5/8/13), Y axis = avg metric, in two modes:
  - `--scenario X --scheduler Y --car-policy Z` — one scenario's own chart, useful for
    diagnosing that specific building's behavior (e.g. a capacity bottleneck visible
    only in one scenario's shape).
  - `--aggregate` — one chart per (scheduler, car_policy) pair, averaged across every
    scenario (unweighted mean, same convention as `compare_schedulers.py`), producing
    `<scheduler>_<car_policy>_avg_<metric>.png` for every pair found in the manifest —
    currently 12 files, a `total_time` and a `wait_time` chart for each of the 6 pairs.

  Both modes produce a `total_time` chart and a `wait_time` chart rather than blending
  them, and leave a gap in a trace wherever a config didn't converge rather than
  plotting a fabricated point.

Figures are written to `figures/` and, unlike the rest of `outputs/`, are **committed**
— they're meant to be dropped straight into a README or presentation without
regenerating anything, so re-run the scripts and commit the updated PNGs whenever the
underlying sweep changes.

## Regenerating figures

```
python analysis/scripts/run_sweep.py
python analysis/scripts/compare_schedulers.py
python analysis/scripts/compare_schedulers.py --min-elevators 4
python analysis/scripts/compare_schedulers.py --max-elevators 5
python analysis/scripts/compare_schedulers.py --max-elevators 6
python analysis/scripts/plot_wait_times.py --aggregate
python analysis/scripts/plot_wait_times.py \
    --scenario sample_full_day_skyscraper50 --scheduler round_robin --car-policy scan
```

`plot_wait_times.py`'s per-scenario mode takes any `--scenario`/`--scheduler`/
`--car-policy` combination present in the manifest — `sample_full_day_skyscraper50`
(the busiest, biggest scenario) is a good first one to try since it's the only one
where a config (1 elevator, capacity 3) fails to converge, visibly showing up as a gap
in the `capacity 3` trace. It's an example to run against whatever you're diagnosing
rather than a committed figure, so its output isn't kept in `figures/`.

## What the current sweep shows

Averaged across the entire sweep (`compare_schedulers.py` with no filter), in ticks:

| scheduler + car policy | avg wait | avg total |
| --- | --- | --- |
| destination_dispatch + bounded_detour | 14.5 | 34.3 |
| destination_dispatch + look | 15.2 | 34.9 |
| destination_dispatch + scan | 17.2 | 39.9 |
| round_robin + bounded_detour | 18.3 | 39.2 |
| round_robin + look | 19.0 | 39.8 |
| round_robin + scan | 19.2 | 42.8 |

Two things to read off it. The scheduler matters more than the car policy — swapping
`round_robin` for `destination_dispatch` buys more than any movement rule does. And the
grid is deliberately a full 2x3 so the two effects can be separated:
`round_robin`+`bounded_detour` isolates what the detour policy is worth on its own,
while `destination_dispatch`+`look` versus `destination_dispatch`+`bounded_detour`
isolates what the dispatcher gains specifically from *knowing* a car can detour (see
`schedulers/README.md`'s note on `bind_car_policy`). Averages also understate the detour
policy, which mostly moves the tail rather than the mean — compare max wait on the
curated `sample_full_day` runs in `outputs/runs/README.md`.
