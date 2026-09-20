# Sample request files

Input format (per the assignment spec), one request per row:

```
time,id,source,dest
0,passenger1,1,51
0,passenger2,1,37
10,passenger3,20,1
```

- `time` — integer time step the request is made (simulation must not peek ahead of this)
- `id` — unique passenger ID
- `source` — origin floor
- `dest` — destination floor

## Files

Recommended run config (`--elevators`/`--floors`/`--capacity`) is given for each file
below — building size/fleet is a CLI flag, not part of the CSV, so any of these can be
re-run with a different configuration to see how it changes the outcome.

- `sample_basic.csv` (3 / 20 / 8) — small hand-crafted scenario (the example from the
  assignment PDF): 3 requests, 2 of them simultaneous at t=0.
- `sample_stress.csv` (6 / 60 / 8) — 10 requests spread across t=0..30, exercising:
  multiple simultaneous requests at t=0 (some same-direction, some opposite), pickups
  that fall along an elevator's already-committed path (mid-route stops), and requests
  that force an elevator to reverse across most of the building. Used throughout this
  project's scheduler/car-policy comparisons — see
  `outputs/examples/round_robin_scan_stress/` and
  `outputs/examples/round_robin_look_stress/`.
- `sample_full_day.csv` (4 / 35 / 8) — 44 requests modeling a full simulated day:
  morning up-peak lobby surge (capacity stress), contradictory same-floor/same-tick
  pairs, a mid-service trickle with reversal-forcing long hauls, a lunch cluster of
  round-trip pairs, a 65-tick idle gap, an afternoon down-peak, and a sparse tail.
- `sample_small_office_day.csv` (2 / 10 / 6) — small-building full day: morning
  up-peak, scattered daytime meetings (including a same-floor contradictory pair),
  lunch dip and return, an idle afternoon gap, then an evening down-peak. 22 requests.
- `sample_quiet_intermittent.csv` (2 / 10 / 6) — off-peak/low-traffic period: 8
  requests, mostly isolated singles or simultaneous pairs, separated by long
  25–50-tick idle stretches — the "almost nothing happening" case.
- `sample_lunch_rush.csv` (3 / 20 / 8) — pure lunch-hour pattern: 12 passengers head
  down to floor 1 within a few staggered ticks, a 43-tick idle gap (lunch itself),
  then the same 12 return to their original floors as reverse trips. 24 requests.
- `sample_uppeak_highrise30.csv` (4 / 30 / 10) — classic morning up-peak: one source
  (floor 1, the lobby), many scattered destinations, 26 requests clustered into four
  arrival ticks — the hardest single-source dispatch case.
- `sample_downpeak_highrise40.csv` (5 / 40 / 10) — classic evening down-peak: many
  scattered sources across the building, one destination (floor 1), 28 requests
  clustered into four arrival ticks — the hardest many-source sweep case.
- `sample_full_day_skyscraper50.csv` (6 / 50 / 10) — flagship "biggest and busiest"
  scenario: 62 requests spanning a full business day at skyscraper scale — up-peak,
  contradictory pairs, mid-service reversals, a lunch cluster, an 85-tick idle window,
  down-peak, and a sparse tail.
- `sample_capacity_overload.csv` (2 / 15 / 4) — pure capacity stress: three separate
  ticks where one floor gets 9-10 simultaneous same-direction requests against a
  fleet capacity of only 8, forcing return trips. 28 requests.
- `sample_contradictory_conflicts.csv` (2 / 15 / 6) — pure contradiction stress:
  nothing but same-floor/same-tick opposite-direction pairs (10 of them) plus a few
  immediate-reversal single sequences, minimal other noise. 24 requests.
- `sample_single_elevator_bottleneck.csv` (**1** / 15 / 6) — fairness/starvation
  check: 20 requests realistically paced across a full day, meant to be run with only
  one elevator to see how wait times grow under a genuine bottleneck.

Add new scenario files here as needed.
