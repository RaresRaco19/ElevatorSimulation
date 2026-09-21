"""Compare (scheduler, car_policy) pairs by aggregating an overall performance score
across the config sweep (every scenario x every elevator count x every capacity, by
default) in outputs/sweep/manifest.json, produced by run_sweep.py.

Reports two separate scores per pair -- avg total_time and avg wait_time -- as two
bar charts, rather than blending them into one weighted number.

--weights switches to the other question: holding the scheduler fixed at
destination_dispatch, how do its *cost weights* compare? That reads
outputs/weights/manifest.json (run_sweep.py --weights) and draws a grouped chart --
one x-axis group per weight preset, one bar per car policy -- because weights and the
movement rule interact and a flat bar per combination would be unreadable at 15 of them.

Both modes share the same aggregation; only the grouping key and the plot layout differ.

Run with: python analysis/scripts/compare_schedulers.py
Or, restricted to better-resourced configs: python analysis/scripts/compare_schedulers.py --min-elevators 4
Or, comparing cost weights: python analysis/scripts/compare_schedulers.py --weights
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
WEIGHTS_MANIFEST = ROOT / "outputs" / "weights" / "manifest.json"
DEFAULT_OUT_DIR = ROOT / "analysis" / "figures"

# One colour per car policy in --weights mode, taken from the palette docs/*.html uses.
POLICY_COLORS = {"scan": "#5a7a8c", "look": "#b5622f", "bounded_detour": "#6b655d"}


def load_manifest(path):
    with open(path) as f:
        return json.load(f)


def aggregate(manifest, key=lambda record: (record["scheduler"], record["car_policy"])):
    """Return {group: {"total_time": avg, "wait_time": avg, "converged": n, "total": n}}.

    `key` picks what a group is. It defaults to the (scheduler, car_policy) pair; the
    --weights mode passes (preset, car_policy) instead, so both modes share one
    aggregation rather than keeping two copies in step."""
    groups = defaultdict(lambda: {"total_time": [], "wait_time": [], "converged": 0, "total": 0})
    for record in manifest:
        group = key(record)
        groups[group]["total"] += 1
        if not record["converged"]:
            continue
        groups[group]["converged"] += 1
        groups[group]["total_time"].append(record["stats"]["total_time"]["avg"])
        groups[group]["wait_time"].append(record["stats"]["wait_time"]["avg"])

    scores = {}
    for group, data in groups.items():
        if not data["converged"]:
            # Every config in this group failed -- possible once --min/--max-elevators
            # narrows the sweep. Drop it rather than dividing by zero.
            continue
        scores[group] = {
            "total_time": sum(data["total_time"]) / len(data["total_time"]),
            "wait_time": sum(data["wait_time"]) / len(data["wait_time"]),
            "converged": data["converged"],
            "total": data["total"],
        }
    return scores


def first_seen(values):
    """Distinct values in first-appearance order -- keeps presets in the order
    run_sweep.py declares them, so `default` anchors the left edge instead of sorting
    alphabetically into the middle."""
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def plot_weight_metric(scores, metric, presets, policies, out_path, title_suffix):
    """Grouped bars: one x-axis group per weight preset, one bar per car policy."""
    fig, ax = plt.subplots(figsize=(max(1.9 * len(presets), 8), 5))

    width = 0.8 / len(policies)
    for index, policy in enumerate(policies):
        offsets, values = [], []
        for position, preset in enumerate(presets):
            score = scores.get((preset, policy))
            if score is None:
                continue
            offsets.append(position - 0.4 + width * (index + 0.5))
            values.append(score[metric])
        bars = ax.bar(offsets, values, width, label=policy, color=POLICY_COLORS.get(policy))
        ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=7)

    ax.set_xticks(range(len(presets)))
    ax.set_xticklabels(presets)
    ax.set_xlabel("destination_dispatch cost weights")
    ax.set_ylabel(f"avg {metric} (ticks)")
    ax.set_title(f"Cost-weight comparison\navg {metric} {title_suffix}")
    ax.legend(title="car policy")
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


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
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--weights",
        action="store_true",
        help="Compare destination_dispatch's cost weight presets instead of "
        "scheduler/car-policy pairs. Reads outputs/weights/manifest.json "
        "(run_sweep.py --weights first) and writes weight_comparison_<metric>.png.",
    )
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

    default_manifest = WEIGHTS_MANIFEST if args.weights else DEFAULT_MANIFEST
    manifest_path = Path(args.manifest) if args.manifest else default_manifest
    if not manifest_path.exists():
        hint = "run_sweep.py --weights" if args.weights else "run_sweep.py"
        raise SystemExit(
            f"No manifest found at {manifest_path}. Run analysis/scripts/{hint} first."
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

    if args.weights:
        scores = aggregate(manifest, key=lambda r: (r["preset"], r["car_policy"]))
        presets = first_seen(r["preset"] for r in manifest)
        policies = first_seen(r["car_policy"] for r in manifest)
        preset_weights = {r["preset"]: r["weights"] for r in manifest}

        for metric in ("total_time", "wait_time"):
            out_path = out_dir / f"weight_comparison_{metric}{suffix}.png"
            plot_weight_metric(scores, metric, presets, policies, out_path, title_suffix)
            print(f"Wrote {out_path.relative_to(ROOT)}")

        print()
        for preset in presets:
            w = preset_weights[preset]
            print(f"{preset}  (wait {w['wait']} / travel {w['travel']} / fairness {w['fairness']})")
            for policy in policies:
                s = scores.get((preset, policy))
                if s is None:
                    continue
                print(
                    f"    +{policy}: total_time={s['total_time']:.1f}, "
                    f"wait_time={s['wait_time']:.1f} ({s['converged']}/{s['total']} converged)"
                )
        return

    scores = aggregate(manifest)
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
