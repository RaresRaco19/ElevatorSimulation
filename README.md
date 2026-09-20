# Elevator System Simulation

A discrete-time, destination-dispatch elevator system simulation (take-home assessment).
Passengers submit `origin -> destination` requests up front; a pluggable **scheduler**
decides which elevator serves each request, a pluggable **car policy** decides how that
elevator moves once it has work to do; the simulation advances one floor of travel at a
time until every request is served.

## Project layout

- `src/elevator_sim/core/` — the simulation engine, data model, and I/O. See
  [`core/README.md`](src/elevator_sim/core/README.md).
- `src/elevator_sim/schedulers/` — pluggable "which elevator handles this request"
  algorithms: `round_robin.py` is implemented; `express.py` and
  `zone_based.py` are stubs. See [`schedulers/README.md`](src/elevator_sim/schedulers/README.md)
  and, for a concise visual walkthrough of the round-robin algorithm,
  [`docs/round_robin.html`](docs/round_robin.html).
- `src/elevator_sim/car_policies/` — pluggable "how does an already-assigned car move"
  algorithms: `scan.py` and `look.py` are implemented and wired into the CLI; `fcfs.py`
  is a stub. See
  [`car_policies/README.md`](src/elevator_sim/car_policies/README.md) and, for concise
  visual walkthroughs, [`docs/scan.html`](docs/scan.html) and
  [`docs/look.html`](docs/look.html).
- `src/elevator_sim/run_simulation.py` — the CLI entrypoint that wires the above
  together.
- `data/requests/` — sample input request CSVs. See
  [`data/requests/README.md`](data/requests/README.md).
- `outputs/` — generated run outputs; `outputs/examples/` holds a curated, committed
  set for reviewers. See [`outputs/examples/README.md`](outputs/examples/README.md).
- `analysis/` — scripts that turn run outputs into charts (still TODO stubs). See
  [`analysis/README.md`](analysis/README.md).
- `ui/` — static web app that replays a run's elevator movement tick by tick. See
  [`ui/README.md`](ui/README.md).
- `tests/` — unit tests for the engine, schedulers, and car policies (still TODO
  stubs, nothing runnable yet). See [`tests/README.md`](tests/README.md).

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
    --scheduler round_robin --car-policy scan \
    --requests data/requests/sample_basic.csv \
    --elevators 3 --floors 60 --capacity 8 \
    --out outputs/round_robin_scan_sample_basic
```

On Windows PowerShell, set the env var separately instead of inline:

```
$env:PYTHONPATH = "src"
python -m elevator_sim.run_simulation --scheduler round_robin --car-policy scan --requests data/requests/sample_basic.csv --elevators 3 --floors 60 --capacity 8 --out outputs/round_robin_scan_sample_basic
```

Currently available flag values:

| Flag | Choices | Notes |
| --- | --- | --- |
| `--scheduler` | `round_robin` | `express`, `zone_based` exist as stub files but aren't wired in yet |
| `--car-policy` | `scan`, `look` | `fcfs` exists as a stub file but isn't wired in yet |
| `--requests` | path to a `time,id,source,dest` CSV | see `data/requests/` |
| `--elevators`, `--floors`, `--capacity` | integers | building configuration |
| `--out` | output directory | created if it doesn't exist |

### 3. Inspect the output

Each run writes five files into `--out`: `config.json`, `positions_log.csv`,
`requests.csv`, `passenger_log.csv`, `passenger_stats.json`. See
[`outputs/examples/README.md`](outputs/examples/README.md) for the exact schema of
each.

### 4. Watch it play back in the browser

1. Open `ui/app.js` and point the `RUN_DIR` constant at your run's output folder,
   relative to `ui/` (e.g. `"../outputs/round_robin_scan_sample_basic"`).
2. Serve the **repository root** (not `ui/` itself) with any static file server:
   ```
   python -m http.server 8000
   ```
3. Open `http://localhost:8000/ui/` in a browser.

### 5. Run the tests

Not runnable yet — `tests/*.py` are currently TODO comments, not test code. Once
implemented, the intent is:

```
PYTHONPATH=src pytest
```

### 6. Regenerate analysis figures

Also not runnable yet — `analysis/scripts/*.py` are currently TODO comments. The
output schema they'll read (`passenger_stats.json`, `positions_log.csv`) is already
finalized, so this is just unwritten plotting code, not a blocked design question.

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

## What I'd improve with more time

- Implement `look.py` and `fcfs.py` car policies, and a cost/lookahead-aware scheduler
  that isn't tied to one specific car policy's movement geometry (currently in design).
- Implement the `zone_based.py` and `express.py` scheduler stubs for a fuller
  fairness/efficiency comparison.
- Model door/boarding delay, so simultaneous pickups aren't free and capacity
  constraints bite more realistically.
- Write the actual unit tests described in `tests/*.py`'s TODO comments.
- Package the project properly (`pyproject.toml`) so `PYTHONPATH=src` isn't required.
