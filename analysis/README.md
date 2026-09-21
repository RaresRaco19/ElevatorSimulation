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
- `scripts/run_sweep.py --weights` — the other question: holding the scheduler fixed at
  `destination_dispatch`, how do its **cost weights** compare? Sweeps five presets x
  three car policies over the same config grid (~6600 runs, about half a minute) and
  writes `outputs/weights/manifest.json`. Weights and the movement rule interact, so
  every preset is run against every policy rather than against one.

  | preset | wait / travel / fairness | |
  | --- | --- | --- |
  | `default` | 1.0 / 0.25 / 0.25 | whatever `destination_dispatch.py`'s constants say |
  | `ride-heavy` | 1.0 / 1.0 / 0.2 | ride time counts as much as waiting |
  | `balanced` | 1.0 / 0.5 / 0.5 | what shipped before the sweep retuned the defaults |
  | `fair` | 1.0 / 0.5 / 1.5 | guard routes already promised to passengers |
  | `selfish` | 1.0 / 0.5 / 0.0 | fairness off — nearest-car-with-a-real-ETA |

  The same table, the cost formula it feeds, and the measured result per preset are
  laid out in [`docs/cost_weights.html`](../docs/cost_weights.html).

  Unlike the main sweep this writes **stats only**, no per-run output folders: the chart
  needs nothing else, the UI doesn't browse this directory, and 6600 five-file runs would
  cost ~100MB for nothing. To inspect one weighting as a real, playable run, use
  edit the constants in `destination_dispatch.py` and run it through
  `run_simulation.py`, or construct the scheduler directly as this mode does.

  It writes to `outputs/weights/`, not `outputs/sweep/`, because each mode wipes its own
  output directory on every run — sharing one would make them delete each other.

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
- `scripts/compare_schedulers.py --weights` — the same aggregation applied to
  `outputs/weights/manifest.json`, grouped by `(preset, car_policy)` instead of
  `(scheduler, car_policy)`, producing `weight_comparison_total_time.png` and
  `weight_comparison_wait_time.png`. These are **grouped** bar charts — one x-axis group
  per preset, one bar per car policy — because fifteen flat bars would need a 33-inch
  figure and would hide the very interaction they exist to show. The elevator-count
  filters work here too.
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
python analysis/scripts/run_sweep.py --weights
python analysis/scripts/compare_schedulers.py --weights
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
| destination_dispatch + bounded_detour | 14.4 | 34.3 |
| destination_dispatch + look | 14.9 | 34.9 |
| destination_dispatch + scan | 17.2 | 40.2 |
| round_robin + bounded_detour | 18.3 | 39.2 |
| round_robin + look | 19.0 | 39.8 |
| round_robin + scan | 19.2 | 42.8 |

Across the weight sweep (`compare_schedulers.py --weights`) the weights move things far
less than the scheduler choice does, but not by nothing — the shipped `default`
(`1.0 / 0.25 / 0.25`) was picked from it, and leads on wait time with `bounded_detour`
(14.4 against `balanced`'s 14.5, the setting that shipped before). Two further things
stand out. `selfish` (fairness off) is the worst weighting for both `look` and
`bounded_detour` (total_time 36.0 / 35.3 against `default`'s 34.9 / 34.3), so the
fairness term earns its place. And under `scan` the weights barely matter at all —
`balanced`, `fair` and `selfish` all score *identically* (17.2 / 39.9). That last one is
a consistency check rather than a coincidence: under true SCAN a car reverses at the
building's end no matter what, so `delta_imposed_on_existing` is always 0 and
`W_FAIRNESS` has nothing to multiply.

Note the averages hide a real trade. `default` wins the sweep-wide mean but is not
uniformly best: it is the strongest setting on `sample_full_day_skyscraper50` and
`sample_stress`, and mid-table on `sample_full_day`. `docs/cost_weights.html` spells
that out.

Two things to read off it. The scheduler matters more than the car policy — swapping
`round_robin` for `destination_dispatch` buys more than any movement rule does. And the
grid is deliberately a full 2x3 so the two effects can be separated:
`round_robin`+`bounded_detour` isolates what the detour policy is worth on its own,
while `destination_dispatch`+`look` versus `destination_dispatch`+`bounded_detour`
isolates what the dispatcher gains specifically from *knowing* a car can detour (see
`schedulers/README.md`'s note on `bind_car_policy`). Averages also understate the detour
policy, which mostly moves the tail rather than the mean — compare max wait on the
curated runs in `outputs/runs/README.md`.

The top row is the pair `run_simulation.py` now defaults to.
