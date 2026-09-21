# car_policies/

Answers exactly one question: **once an elevator has committed stops, which direction
should it move next, and when should it reverse?** Nothing here decides which requests
get assigned to a car (that's `schedulers/`), and capacity isn't this layer's concern
either.

## Interface (`base.py`)

```python
class CarMovementPolicy(ABC):
    def next_direction(self, elevator, current_time, floors) -> Direction:
        """UP / DOWN / IDLE. Called once per tick per elevator by core/engine.py."""
```

`floors` (the building's top floor) is passed explicitly because a policy's reversal
rule generally needs to know the building's bounds, not just the elevator's own state.

## Implementations

- **`scan.py`** (implemented) — true SCAN: continue in the current direction, serving
  every committed stop along the way, until reaching floor 1 or the top floor — then
  reverse, even with no remaining requests in that direction. Chosen as the first,
  simplest policy to implement; it means an elevator can take a much longer route than
  strictly necessary (see `outputs/runs/round_robin_scan_stress/` for a real example
  of one elevator sweeping the entire building for a single distant drop-off). See
  [`docs/scan.html`](../../../docs/scan.html) for a concise visual walkthrough.

- **`look.py`** (implemented) — like `scan.py`, but reverses as soon as there are no
  more committed stops *further* in the current direction, without running all the way
  to the building's physical end. Closer to what real elevator controllers do, and
  avoids the wasted sweeps `scan.py` is prone to. See
  [`docs/look.html`](../../../docs/look.html) for a concise visual walkthrough.

- **`bounded_detour.py`** (implemented) — `look.py` plus the ability to turn back for
  one stop the car has already passed, then resume the sweep exactly where it left off.
  Plain LOOK is unfair to anyone standing behind a car that has just gone by: they wait
  out the whole remaining sweep plus the return leg, however close the car actually is.
  This policy lets the car double back, but only inside three hard bounds, so the fix
  can't become the thrashing `fcfs` would produce:

  | | |
  | --- | --- |
  | `MAX_DETOUR_DISTANCE` (D) | how far back the car may divert from where it stands |
  | `MAX_DETOURS_PER_SWEEP` (k) | how many diversions one sweep may spend |
  | `MAX_FAIRNESS_DELAY` (F) | how much one diversion may delay those already aboard |

  Together these bound the worst case at exactly **`k * 2D` extra ticks per sweep** for
  every passenger aboard — a real guarantee rather than a tendency, since every quantity
  involved is exact (`core/trip_estimator.py`), and one `tests/test_car_policies.py`
  checks directly. The bounds are module constants rather than CLI flags: they describe
  how the policy behaves, not what an individual run does, so the CLI is unchanged.

  Its effect is mostly on the *tail*, which is what it's for: on `sample_full_day` at
  4 cars / capacity 8 with `destination_dispatch`, max wait drops from 30 to 19 ticks.
  See [`docs/bounded_detour.html`](../../../docs/bounded_detour.html) for a visual
  walkthrough.

- **`fcfs.py`** (stub) — serves committed stops strictly in assignment order, ignoring
  direction efficiency entirely (may reverse repeatedly). Intended as a worst-case
  contrast baseline, not a serious policy.

## Coupling with schedulers

A policy's reversal rule is not just its own business: any scheduler that estimates
travel time has to know where cars turn around, and an ETA formula tuned to `scan.py`'s
run-to-the-end geometry is simply wrong for `look.py`, which reverses earlier.

Each policy therefore declares its rule as a `reversal_geometry` attribute (`base.py`,
defaulting to LOOK — only `scan.py` overrides it), and `core/engine.py` hands the active
policy to the scheduler through `Scheduler.bind_car_policy()`. `core/trip_estimator.py`
takes that geometry as a parameter, so one set of formulas stays exact for both
policies. `bounded_detour.py` additionally exposes `detour_limits()`, which is how a
scheduler learns it may price a behind-the-car pickup at the cost of a diversion rather
than a full reversal.

The naive schedulers are untouched by any of this: `round_robin`'s `estimated_wait_time`
is still plain floor distance, and `bind_car_policy()` is a no-op it inherits.
