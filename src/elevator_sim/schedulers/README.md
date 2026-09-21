# schedulers/

Answers exactly one question: **which elevator should handle this request?** Nothing
here decides how that elevator subsequently moves (that's `car_policies/`), and
capacity itself is enforced by `core/engine.py` at boarding time, not here.

## Interface (`base.py`)

```python
class Scheduler(ABC):
    def assign(self, request, elevators, current_time, floors) -> tuple[str, int]:
        """Return (elevator_id, estimated_wait_time) for this request."""
```

A scheduler owns its own `estimated_wait_time` guess — the engine just records
whatever comes back. This matters: a naive scheduler and a well-informed one can
report very different numbers for the same request, and that gap is itself useful
signal (see `outputs/runs/README.md`'s `estimate_drift`).

## Implementations

- **`round_robin.py`** (implemented) — the deliberately naive fairness baseline.
  Cycles elevators in a fixed rotation with zero awareness of any elevator's actual
  position, remaining stop queue, or capacity. Its one concession: requests arriving
  in the *same tick* and heading the *same direction* are bucketed onto the same
  elevator instead of each claiming a fresh one off the rotation — otherwise a burst
  of simultaneous compatible requests would pointlessly occupy every car at once. Its
  `estimated_wait_time` is always the naive `abs(elevator.current_floor -
  request.source)`.

- **`express.py`** (implemented, not yet wired in) — express cars restricted to a
  stride-based `serviceable_floors` subset; see the module docstring for the
  eligibility/fallback rule and its no-transfer limitation. `run_simulation.py`'s
  `SCHEDULERS` registry doesn't build express fleets yet — that's a separate pass.
  Note that `destination_dispatch` treats the fleet as homogeneous and does not consult
  `serviceable_floors`, so the two shouldn't be combined without teaching it that rule.

- **`destination_dispatch.py`** (implemented, wired into the CLI) — the cost-aware
  scheduler, and the only one that actually uses the destination the passenger gave at
  request time. Scores every candidate car on three exact quantities from
  `core/trip_estimator.py` and takes the cheapest:

  ```
  cost = W_WAIT     * ticks_to_pickup                        how long this passenger waits
       + W_TRAVEL   * (ticks_to_dropoff - ticks_to_pickup)   how long they then ride
       + W_FAIRNESS * delta_imposed_on_existing              what it costs everyone else
  ```

  The third term is what destination knowledge buys: a trip that fits inside a sweep a
  car is already committed to costs nobody anything, while one that pushes that car's
  reversal point further out makes everyone waiting behind it wait longer — and you
  cannot tell those apart without knowing where the passenger is going.

  Two structural details worth knowing before editing it:

  - It keeps a **pledge ledger**. `core/engine.py` only adds a destination to a car's
    `stop_queue` at *boarding*, so a lobby car with eight people assigned and none
    aboard reads as completely idle. The ledger holds promised-but-not-yet-handed-over
    destinations and is pruned from observable car state alone, so it cannot drift.
  - It assigns a whole tick's requests as a **batch** (`assign_batch`, see `base.py`),
    because simultaneous requests interact: committing one to a car changes what the
    next one costs there. Free (non-extending) requests are committed straight away,
    then the rest go by cheapest insertion — repeatedly commit the single cheapest
    (request, car) pair available right now and re-score what is left against the state
    that produced. A batch of one reduces to plain "pick the cheapest car", which is
    exactly what `assign()` promises.

  Unlike `round_robin`, its `estimated_wait_time` is a real ETA rather than a distance
  guess, which is what finally makes `estimate_drift` (see `outputs/runs/README.md`)
  measure something: on `sample_full_day` at 4 cars / capacity 8 it drops from
  `round_robin`+`look`'s avg 5.4 / max 50 to avg 0.1 / max 2. See
  [`docs/destination_dispatch.html`](../../../docs/destination_dispatch.html) for a
  visual walkthrough.

- **`zone_based.py`** (stub) — bonus algorithm, not yet implemented. See its header
  comment for the intended design.

## Coupling with car policies

Most schedulers here are independent of how cars move. `destination_dispatch` is not,
and cannot be: its estimates are only exact if it knows where a car reverses, and that
is the car policy's rule. `core/engine.py` hands the active policy to the scheduler via
`Scheduler.bind_car_policy()` (a no-op on the ABC, so the naive schedulers are
unaffected), and the scheduler reads two things off it — the policy's
`reversal_geometry`, and, if the policy offers one, its `detour_limits()`. Both are
duck-typed, so no scheduler imports any car policy.
