# Analysis

Static charts generated from completed runs in `outputs/` (typically `outputs/examples/`).

**Status: the scripts below are still TODO stubs, not implemented yet.** The output
schema they'll read is finalized, though (see
[`outputs/examples/README.md`](../outputs/examples/README.md)) — this is unwritten
plotting code, not a blocked design question.

## Scripts

- `scripts/plot_wait_times.py` — wait time / total time distributions for a single run
- `scripts/compare_schedulers.py` — cross-algorithm comparison (fairness vs. efficiency)
  across multiple runs in `outputs/`

Each script reads a run's `positions_log.csv` / `passenger_stats.json` and writes PNGs to
`figures/`, which are committed so they can be dropped straight into the README or
presentation slides without regenerating anything.

## Regenerating figures (once implemented)

```
python analysis/scripts/plot_wait_times.py --run outputs/examples/round_robin_scan_stress
python analysis/scripts/compare_schedulers.py --outputs-dir outputs/examples
```

Existing runs to compare against each other today: `round_robin_scan_stress/` vs.
`round_robin_look_stress/`, both against `data/requests/sample_stress.csv` — the ideal
first pair to plug into `compare_schedulers.py` once it exists, since they already
show a clear `estimate_drift` contrast between the two car policies (avg drops from
6.8 to 0.8 ticks — see each run's own `passenger_stats.json` for the current numbers,
which shift whenever either run is regenerated).
