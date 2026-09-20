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
signal (see `outputs/examples/README.md`'s `estimate_drift`).

## Implementations

- **`round_robin.py`** (implemented) — the deliberately naive fairness baseline.
  Cycles elevators in a fixed rotation with zero awareness of any elevator's actual
  position, remaining stop queue, or capacity. Its one concession: requests arriving
  in the *same tick* and heading the *same direction* are bucketed onto the same
  elevator instead of each claiming a fresh one off the rotation — otherwise a burst
  of simultaneous compatible requests would pointlessly occupy every car at once. Its
  `estimated_wait_time` is always the naive `abs(elevator.current_floor -
  request.source)`.

- **`express.py`**, **`zone_based.py`** (stubs) — bonus algorithms, not yet
  implemented. See each file's header comment for the intended design.

## Not implemented yet: a cost/lookahead-aware scheduler

`round_robin` is the only implemented scheduler so far, and it's deliberately naive —
not meant to be the final "intelligent" scheduler for this project. A lookahead/cost-aware
scheduler that accounts for an elevator's actual position, committed stops, and
capacity is being designed separately and isn't started yet.
