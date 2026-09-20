"""Compare (scheduler, car_policy) pairs by aggregating an overall performance score
across the config sweep (every scenario x every elevator count x every capacity, by
default) in outputs/sweep/manifest.json, produced by run_sweep.py.

Reports two separate scores per pair -- avg total_time and avg wait_time -- as two
bar charts, rather than blending them into one weighted number.

Run with: python analysis/scripts/compare_schedulers.py
Or, restricted to better-resourced configs: python analysis/scripts/compare_schedulers.py --min-elevators 4
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


def load_manifest(path):
    with open(path) as f:
        return json.load(f)


def aggregate(manifest):
    """Return {(scheduler, car_policy): {"total_time": avg, "wait_time": avg,
    "converged": n, "total": n}}."""
    groups = defaultdict(lambda: {"total_time": [], "wait_time": [], "converged": 0, "total": 0})
    for record in manifest:
        pair = (record["scheduler"], record["car_policy"])
        groups[pair]["total"] += 1
        if not record["converged"]:
            continue
        groups[pair]["converged"] += 1
        groups[pair]["total_time"].append(record["stats"]["total_time"]["avg"])
        groups[pair]["wait_time"].append(record["stats"]["wait_time"]["avg"])

    scores = {}
    for pair, data in groups.items():
        scores[pair] = {
            "total_time": sum(data["total_time"]) / len(data["total_time"]),
            "wait_time": sum(data["wait_time"]) / len(data["wait_time"]),
            "converged": data["converged"],
            "total": data["total"],
        }
    return scores


def plot_metric(scores, metric, out_path, title_suffix):
    pairs = sorted(scores)
    labels = [f"{scheduler}\n+{car_policy}" for scheduler, car_policy in pairs]
    values = [scores[pair][metric] for pair in pairs]

    fig, ax = plt.subplots(figsize=(max(2.2 * len(pairs), 6), 5))
    bars = ax.bar(labels, values, color="#5a7a8c")
    ax.set_ylabel(f"avg {metric} (ticks)")
    ax.set_title(f"Scheduler/car-policy comparison\navg {metric} {title_suffix}")
    ax.bar_label(bars, fmt="%.1f", padding=3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--min-elevators",
        type=int,
        default=None,
        help="Only include configs with MORE than this many elevators (elevators > N, exclusive). "
        "Default: no filter, uses the entire sweep. Combinable with --max-elevators.",
    )
    parser.add_argument(
        "--max-elevators",
        type=int,
        default=None,
        help="Only include configs with AT MOST this many elevators (elevators <= N, inclusive). "
        "Default: no filter, uses the entire sweep. Combinable with --min-elevators.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(
            f"No manifest found at {manifest_path}. Run analysis/scripts/run_sweep.py first."
        )

    manifest = load_manifest(manifest_path)
    if args.min_elevators is not None:
        manifest = [r for r in manifest if r["elevators"] > args.min_elevators]
    if args.max_elevators is not None:
        manifest = [r for r in manifest if r["elevators"] <= args.max_elevators]
    if (args.min_elevators is not None or args.max_elevators is not None) and not manifest:
        raise SystemExit(
            f"--min-elevators {args.min_elevators} / --max-elevators {args.max_elevators} "
            "excludes every record in the manifest -- check them against the sweep's "
            "actual elevator range."
        )

    scores = aggregate(manifest)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix_parts = []
    if args.min_elevators is not None:
        suffix_parts.append(f"min_elevators_{args.min_elevators}")
    if args.max_elevators is not None:
        suffix_parts.append(f"max_elevators_{args.max_elevators}")
    suffix = "" if not suffix_parts else "_" + "_".join(suffix_parts)

    if args.min_elevators is not None and args.max_elevators is not None:
        title_suffix = f"({args.min_elevators} < elevators <= {args.max_elevators})"
    elif args.min_elevators is not None:
        title_suffix = f"(elevators > {args.min_elevators})"
    elif args.max_elevators is not None:
        title_suffix = f"(elevators <= {args.max_elevators})"
    else:
        title_suffix = "across full sweep"

    for metric in ("total_time", "wait_time"):
        out_path = out_dir / f"scheduler_comparison_{metric}{suffix}.png"
        plot_metric(scores, metric, out_path, title_suffix)
        print(f"Wrote {out_path.relative_to(ROOT)}")

    print()
    for pair in sorted(scores):
        s = scores[pair]
        print(
            f"{pair[0]}+{pair[1]}: total_time={s['total_time']:.1f}, "
            f"wait_time={s['wait_time']:.1f} ({s['converged']}/{s['total']} converged)"
        )


if __name__ == "__main__":
    main()
