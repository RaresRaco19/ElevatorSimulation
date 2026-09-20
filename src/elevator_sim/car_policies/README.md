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
  strictly necessary (see `outputs/examples/round_robin_scan_stress/` for a real example
  of one elevator sweeping the entire building for a single distant drop-off). See
  [`docs/scan.html`](../../../docs/scan.html) for a concise visual walkthrough.

- **`look.py`** (implemented) — like `scan.py`, but reverses as soon as there are no
  more committed stops *further* in the current direction, without running all the way
  to the building's physical end. Closer to what real elevator controllers do, and
  avoids the wasted sweeps `scan.py` is prone to. See
  [`docs/look.html`](../../../docs/look.html) for a concise visual walkthrough.

- **`fcfs.py`** (stub) — serves committed stops strictly in assignment order, ignoring
  direction efficiency entirely (may reverse repeatedly). Intended as a worst-case
  contrast baseline, not a serious policy.

## Coupling with schedulers

No implemented scheduler currently couples its wait-time estimate to a specific car
policy's movement geometry: `round_robin`'s `estimated_wait_time` is plain floor
distance (`abs(elevator.current_floor - request.source)`), independent of whichever
car policy (`scan` or `look`) is active. A future ETA-aware scheduler would need to
account for this — an ETA formula tuned to `scan.py`'s true-SCAN reversal geometry
would need adjusting before it could pair correctly with `look.py`, since `look.py`
reverses earlier than `scan.py` does.
