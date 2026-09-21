# Elevator playback UI

A single, dependency-free, dark-themed page that replays a completed simulation run: an
SVG line chart with time on the X axis and floor on the Y axis, one colored line per
elevator. A **Runs / Config Explorer** toggle in the top-right corner switches
between two ways of picking a run (see "Picking a run" below). An always-visible Run Summary shows passenger
count and min/avg/max wait & total time for the whole run. You can toggle individual
elevators on/off, press **Run** to play through the log tick by tick, or drag the
scrubber to jump straight to any timestamp. A Requests log at the bottom fills in with
every request whose time has been reached (including which elevator served it), and a
"Passenger Times" panel below it fills in with each passenger's waiting time and total
time once their trip completes (dropoff).

No build step, no libraries — plain HTML/CSS/JS.

## Running it

`app.js` fetches files from a sibling `outputs/` directory, so serve the **repository
root** (not the `ui/` folder itself) with a simple static server:

```
python -m http.server 8000
```

then open `http://localhost:8000/ui/`.

## Picking a run

**Runs mode** (default): `app.js` discovers every run directory under `outputs/`
and `outputs/runs/` by parsing the directory-listing pages `python -m http.server`
serves for them, keeping only entries that actually contain a `config.json` — no
manifest file to keep in sync, any run you generate shows up automatically. Pick one
from the dropdown in the top-right corner to load it. This only works when the static
server emits a directory listing; if it doesn't, the page falls back to a single
hardcoded default run (`DEFAULT_RUN_DIR` in `app.js`).

**Config Explorer mode**: switch the toggle to browse the full config sweep produced
by `analysis/scripts/run_sweep.py` (see `analysis/README.md`) — run that script first
if you haven't yet. Four cascading dropdowns — Scenario, Scheduler+CarPolicy,
Elevators, Capacity — are built entirely from `outputs/sweep/manifest.json`, filtered
at each level to combinations that actually converged; picking all four loads that run
exactly like Runs mode does. If the sweep hasn't been run yet (`manifest.json`
404s), the dropdowns are replaced with a message telling you to run `run_sweep.py`
first, rather than erroring.

## Expected input

Each run folder needs:

- `config.json` — `{ scheduler, car_policy, floors, elevators: [...ids], capacity }`.
  `car_policy` is shown in the run-info line when present; older runs generated before
  this field existed simply omit it there.
- `positions_log.csv` — wide format, one row per time step, one column per elevator id
  (e.g. `time,E1,E2,E3`), written by `src/elevator_sim/core/io.py`
- `requests.csv` — same `time,id,source,dest` schema as `data/requests/*.csv`, copied
  into the run's output folder so this page only needs to read one directory
- `passenger_log.csv` — one row per passenger: `id, source, dest, request_time, elevator,
  estimated_wait_time, pickup_time, actual_wait_time, dropoff_time, travel_time,
  total_time`. The UI only displays `elevator` (in the Requests table) and
  `actual_wait_time`/`total_time`/`elevator` (as "Waiting Time"/"Total Time"/"Elevator"
  in the Passenger Times panel) — `estimated_wait_time` is logged and still used for
  `passenger_stats.json`'s `estimate_drift`, but isn't shown in this UI. See
  `src/elevator_sim/schedulers/README.md` for how it's computed — each scheduler owns
  its own number, so it means quite different things run to run: `round_robin` reports a
  naive `|elevator_floor - source|` guess, while `destination_dispatch` reports a real
  computed arrival. Comparing two runs' `estimate_drift` in the Run Summary's source
  file is the quickest way to see that difference.
- `passenger_stats.json` — aggregate over `passenger_log.csv` (`core/metrics.py`'s
  `compute_passenger_stats`): count, `wait_time`/`total_time` `{min, max, avg}`, and
  `estimate_drift`. Rendered once at load into the always-visible Run Summary card.
