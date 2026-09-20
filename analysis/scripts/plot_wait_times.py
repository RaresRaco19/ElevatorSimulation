"""Plot how performance changes across the config grid from
outputs/sweep/manifest.json (produced by run_sweep.py): elevators (1-10) on the X
axis, one trace per capacity (3/5/8/13), Y axis = avg metric.

Two modes:
  --scenario/--scheduler/--car-policy  one scenario's own chart (useful for
                                        diagnosing that specific building's behavior)
  --aggregate                          one chart per (scheduler, car_policy) pair,
                                        averaged across every scenario

Either mode produces two charts -- avg total_time and avg wait_time -- rather than
blending them.

Run with:
    python analysis/scripts/plot_wait_times.py \\
        --scenario sample_full_day_skyscraper50 --scheduler round_robin --car-policy scan
    python analysis/scripts/plot_wait_times.py --aggregate
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "outputs" / "sweep" / "manifest.json"
DEFAULT_OUT_DIR = ROOT / "analysis" / "figures"

CAPACITIES = [3, 5, 8, 13]


def load_manifest(path):
    with open(path) as f:
        return json.load(f)


def filter_records(manifest, scenario, scheduler, car_policy):
    return [
        r
        for r in manifest
        if r["scenario"] == scenario and r["scheduler"] == scheduler and r["car_policy"] == car_policy
    ]


def plot_metric(records, metric, scenario, scheduler, car_policy, out_path):
    fig, ax = plt.subplots(figsize=(8, 5))

    for capacity in CAPACITIES:
        by_elevators = {r["elevators"]: r for r in records if r["capacity"] == capacity}
        elevators_sorted = sorted(by_elevators)
        xs, ys = [], []
        for e in elevators_sorted:
            record = by_elevators[e]
            if not record["converged"]:
                continue
            xs.append(e)
            ys.append(record["stats"][metric]["avg"])
        ax.plot(xs, ys, marker="o", label=f"capacity {capacity}")

    ax.set_xlabel("elevators")
    ax.set_ylabel(f"avg {metric} (ticks)")
    ax.set_title(f"{scenario} -- {scheduler}+{car_policy} -- avg {metric}")
    ax.set_xticks(range(1, 11))
    ax.legend(title="capacity")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def aggregate_records(manifest):
    """Group converged records by (scheduler, car_policy) pair, then by
    (elevators, capacity), collecting every scenario's stats.<metric>.avg into that
    cell so it can be averaged across scenarios -- mirrors compare_schedulers.py's
    unweighted-mean-across-scenarios approach."""
    converged = [r for r in manifest if r["converged"]]
    pairs = sorted(set((r["scheduler"], r["car_policy"]) for r in converged))
    scenario_count = len(set(r["scenario"] for r in converged))

    cells_by_pair = {}
    for pair in pairs:
        cells = defaultdict(lambda: {"total_time": [], "wait_time": []})
        for r in converged:
            if (r["scheduler"], r["car_policy"]) != pair:
                continue
            cell = cells[(r["elevators"], r["capacity"])]
            cell["total_time"].append(r["stats"]["total_time"]["avg"])
            cell["wait_time"].append(r["stats"]["wait_time"]["avg"])
        cells_by_pair[pair] = cells

    return pairs, cells_by_pair, scenario_count


def plot_aggregate_metric(cells, metric, scheduler, car_policy, scenario_count, out_path):
    fig, ax = plt.subplots(figsize=(8, 5))

    for capacity in CAPACITIES:
        xs, ys = [], []
        for elevators in range(1, 11):
            values = cells.get((elevators, capacity), {}).get(metric, [])
            if not values:
                continue
            xs.append(elevators)
            ys.append(sum(values) / len(values))
        ax.plot(xs, ys, marker="o", label=f"capacity {capacity}")

    ax.set_xlabel("elevators")
    ax.set_ylabel(f"avg {metric} (ticks)")
    ax.set_title(f"{scheduler}+{car_policy} -- avg {metric} across {scenario_count} scenarios")
    ax.set_xticks(range(1, 11))
    ax.legend(title="capacity")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Average across all scenarios instead of one; ignores --scenario/--scheduler/--car-policy",
    )
    parser.add_argument("--scenario")
    parser.add_argument("--scheduler")
    parser.add_argument("--car-policy")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    single_args_given = args.scenario or args.scheduler or args.car_policy
    if args.aggregate and single_args_given:
        parser.error("--aggregate cannot be combined with --scenario/--scheduler/--car-policy")
    if not args.aggregate and not (args.scenario and args.scheduler and args.car_policy):
        parser.error("either pass --aggregate, or all of --scenario/--scheduler/--car-policy")

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(
            f"No manifest found at {manifest_path}. Run analysis/scripts/run_sweep.py first."
        )
    manifest = load_manifest(manifest_path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.aggregate:
        pairs, cells_by_pair, scenario_count = aggregate_records(manifest)
        if not pairs:
            raise SystemExit("No converged sweep records found.")
        for scheduler, car_policy in pairs:
            cells = cells_by_pair[(scheduler, car_policy)]
            for metric in ("total_time", "wait_time"):
                out_path = out_dir / f"{scheduler}_{car_policy}_avg_{metric}.png"
                plot_aggregate_metric(cells, metric, scheduler, car_policy, scenario_count, out_path)
                print(f"Wrote {out_path.relative_to(ROOT)}")
        return

    records = filter_records(manifest, args.scenario, args.scheduler, args.car_policy)
    if not records:
        raise SystemExit(
            f"No sweep records for scenario={args.scenario!r} "
            f"scheduler={args.scheduler!r} car_policy={args.car_policy!r}"
        )

    non_converged = sum(1 for r in records if not r["converged"])
    if non_converged:
        print(f"Note: {non_converged}/{len(records)} configs did not converge -- gaps left in traces.")

    for metric in ("total_time", "wait_time"):
        out_path = out_dir / f"{args.scenario}_{args.scheduler}_{args.car_policy}_{metric}.png"
        plot_metric(records, metric, args.scenario, args.scheduler, args.car_policy, out_path)
        print(f"Wrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
