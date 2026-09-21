# Elevator System Simulation

A discrete-time, destination-dispatch elevator system simulation (take-home assessment).
Passengers submit `origin -> destination` requests up front; a pluggable **scheduler**
decides which elevator serves each request, a pluggable **car policy** decides how that
elevator moves once it has work to do; the simulation advances one floor of travel at a
time until every request is served.

## Project layout

**Start with [`docs/architecture.html`](docs/architecture.html)** — a one-page visual
tour of how the simulator is built: two pluggable layers (which elevator takes a
request, and how that elevator then moves) over a fixed engine that owns everything
else.

- `src/elevator_sim/core/` — the simulation engine, data model, and I/O. See
  [`core/README.md`](src/elevator_sim/core/README.md).
- `src/elevator_sim/schedulers/` — pluggable "which elevator handles this request"
  algorithms: `round_robin.py` and `destination_dispatch.py` are implemented and wired
  into the CLI, `express.py` is implemented but not wired in, and `zone_based.py` is a
  stub. See [`schedulers/README.md`](src/elevator_sim/schedulers/README.md) and, for
  concise visual walkthroughs,
  [`docs/round_robin.html`](docs/round_robin.html) and
  [`docs/destination_dispatch.html`](docs/destination_dispatch.html); the exact cost
  weights `destination_dispatch` uses, and how to compare settings, are in
  [`docs/cost_weights.html`](docs/cost_weights.html).
- `src/elevator_sim/car_policies/` — pluggable "how does an already-assigned car move"
  algorithms: `scan.py`, `look.py` and `bounded_detour.py` are implemented and wired
  into the CLI; `fcfs.py` is a stub. See
  [`car_policies/README.md`](src/elevator_sim/car_policies/README.md) and, for concise
  visual walkthroughs, [`docs/scan.html`](docs/scan.html),
  [`docs/look.html`](docs/look.html) and
  [`docs/bounded_detour.html`](docs/bounded_detour.html).
- `src/elevator_sim/run_simulation.py` — the CLI entrypoint that wires the above
  together.
- `data/requests/` — sample input request CSVs. See
  [`data/requests/README.md`](data/requests/README.md).
- `outputs/` — generated run outputs; `outputs/runs/` holds a curated, committed
  set for reviewers. See [`outputs/runs/README.md`](outputs/runs/README.md).
- `analysis/` — scripts that turn run outputs into charts. See
  [`analysis/README.md`](analysis/README.md).
- `ui/` — static web app that replays a run's elevator movement tick by tick. See
  [`ui/README.md`](ui/README.md).
- `tests/` — unit tests for the trip estimator, schedulers, and car policies
  (`test_engine.py` is still a TODO stub). See [`tests/README.md`](tests/README.md).

## How to run

### 1. Install dependencies

```
pip install -r requirements.txt
```

The simulation core itself is stdlib-only; `matplotlib` is only needed for
`analysis/` and `pytest` only for `tests/` once those are implemented.

### 2. Run a simulation

The package isn't installed (no `pyproject.toml`/`setup.py`), so `src/` needs to be on
`PYTHONPATH` explicitly:

```
PYTHONPATH=src python -m elevator_sim.run_simulation \
    --requests data/requests/sample_full_day_skyscraper50.csv \
    --elevators 6 --floors 50 --capacity 10 \
    --out outputs/my_run
```

On Windows PowerShell, set the env var separately instead of inline:

```
$env:PYTHONPATH = "src"
python -m elevator_sim.run_simulation --requests data/requests/sample_full_day_skyscraper50.csv --elevators 6 --floors 50 --capacity 10 --out outputs/my_run
```

No `--scheduler` or `--car-policy` there: they default to **`destination_dispatch` +
`bounded_detour`**, the recommended configuration (see `analysis/README.md` for the
sweep it was chosen from). Name a baseline explicitly to compare against it:

```
    --scheduler round_robin --car-policy scan
```

Currently available flag values:

| Flag | Choices | Notes |
| --- | --- | --- |
| `--scheduler` | `round_robin`, **`destination_dispatch`** (default) | `express` is implemented but not wired in; `zone_based` is a stub |
| `--car-policy` | `scan`, `look`, **`bounded_detour`** (default) | `fcfs` exists as a stub file but isn't wired in yet |
| `--requests` | path to a `time,id,source,dest` CSV | see `data/requests/` |
| `--elevators`, `--floors`, `--capacity` | integers | building configuration |
| `--out` | output directory | created if it doesn't exist |

`destination_dispatch`'s cost weights are fixed constants chosen from the sweep, not
flags — see [`docs/cost_weights.html`](docs/cost_weights.html) for what they are and
`analysis/scripts/run_sweep.py --weights` for comparing alternatives.

### 3. Inspect the output

Each run writes five files into `--out`: `config.json`, `positions_log.csv`,
`requests.csv`, `passenger_log.csv`, `passenger_stats.json`. See
[`outputs/runs/README.md`](outputs/runs/README.md) for the exact schema of
each.

### 4. Watch it play back in the browser

1. Serve the **repository root** (not `ui/` itself) with any static file server:
   ```
   python -m http.server 8000
   ```
2. Open `http://localhost:8000/ui/` in a browser. The **Runs** tab (default) picks
   up any run under `outputs/` or `outputs/runs/` automatically, including the one
   you just generated with `--out`. The **Config Explorer** tab instead browses the
   full config sweep — run `python analysis/scripts/run_sweep.py` first, then use its
   four dropdowns (Scenario, Scheduler+CarPolicy, Elevators, Capacity) to pick a run.
   See `ui/README.md` for details.

### 5. Run the tests

```
PYTHONPATH=src pytest
```

On Windows PowerShell, `$env:PYTHONPATH = "src"` first, then `pytest`. See
[`tests/README.md`](tests/README.md) for what each file covers.

### 6. Regenerate analysis figures

```
python analysis/scripts/run_sweep.py
python analysis/scripts/compare_schedulers.py
python analysis/scripts/plot_wait_times.py --aggregate
```

The sweep runs every scenario across elevators 1-10 x capacity {3, 5, 8, 13} for all six
(scheduler, car policy) pairs — about 2640 configs in half a minute. See
[`analysis/README.md`](analysis/README.md) for the full set of commands and what the
current figures show.

## Time spent

TODO

## Assumptions, simplifications, trade-offs

- One time unit = one floor of travel; boarding and alighting are instantaneous — no
  door-open delay is modeled, so multiple passengers can board an elevator at the same
  floor in the same tick at no time cost.
- Capacity is only enforced at *boarding* time (`core/engine.py`): if an elevator is
  already full when it reaches a pickup floor, that passenger simply keeps waiting.
- `car_policies/scan.py` implements **true SCAN**: an elevator continues to floor 1 or
  the top floor before reversing, even if it has no remaining requests in that
  direction. This was a deliberate simplification for the first working version,
  before `look.py` (reverses as soon as no further requests remain that way) exists
  for comparison.
- `schedulers/round_robin.py` batches requests that arrive in the same tick and travel
  the same direction onto one elevator (so a burst of compatible simultaneous requests
  doesn't needlessly occupy every car), but it otherwise remains fully naive — it has
  no notion of any elevator's actual position, remaining stop queue, or capacity.
- Zero dwell time is what makes `core/trip_estimator.py` exact rather than approximate:
  with no door delay, the time to reach any floor is pure geometry, so
  `schedulers/destination_dispatch.py` can score a candidate car with arithmetic instead
  of simulating it. Adding a boarding delay would make those closed forms approximations
  and is the assumption most worth revisiting first.
- `core/engine.py` only adds a passenger's destination to a car's `stop_queue` at
  *boarding*, not at assignment, so a car's queue understates what it is committed to.
  `destination_dispatch` compensates with its own pledge ledger rather than changing the
  engine, which would have altered every existing run's behaviour.
- `schedulers/destination_dispatch.py` treats the fleet as homogeneous: it doesn't
  consult `Elevator.serviceable_floors`, so it shouldn't be paired with an express fleet
  (that eligibility rule lives in `express.py`).
- `car_policies/bounded_detour.py`'s three bounds (D, k, F) are module constants rather
  than CLI flags — they describe how the policy behaves, not what a given run does.

## What I'd improve with more time

- Implement the `fcfs.py` car policy and the `zone_based.py` scheduler stub, and wire
  `express.py` into the CLI, for a fuller fairness/efficiency comparison.
- Teach `destination_dispatch` about `serviceable_floors` so it can dispatch a mixed
  express/regular fleet.
- Model door/boarding delay, so simultaneous pickups aren't free and capacity
  constraints bite more realistically. This is the change that would cost
  `trip_estimator` its exactness, so it wants doing deliberately.
- Write `tests/test_engine.py`, the one test file still a TODO comment.
- Adapt the cost weights to the traffic. `1.0 / 0.25 / 0.25` was chosen from the
  sweep, but it is the strongest setting on some scenarios and mid-table on others
  (see [`docs/cost_weights.html`](docs/cost_weights.html)) — a scheduler that retuned
  itself to the pattern it was seeing would beat any single fixed choice.
- Package the project properly (`pyproject.toml`) so `PYTHONPATH=src` isn't required.
