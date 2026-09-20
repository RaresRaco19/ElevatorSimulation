# TODO: one test class per policy in src/elevator_sim/car_policies/
# (scan, look, fcfs) — each should at minimum verify every committed stop on an
# elevator is eventually visited (no starvation) and that direction only reverses
# when that policy's rule says it should (e.g. scan.py only reverses at a terminal
# floor with no further stops in the current direction; look.py reverses as soon as
# there are no more stops further in the current direction).
