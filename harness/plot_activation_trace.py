"""Plot the two measured block22 activation calls; no model execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def plot_trace(analysis, output, *, baseline_call=1, candidate_call=2, level_bottom0=17):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("activation figure requires a new path")
    if analysis.get("schema") != "kdm6.block22_activation_analysis.v1":
        raise ValueError("unsupported activation analysis")
    calls = {item["call"]: item for item in analysis["calls"]}
    targets = []
    for call in (baseline_call, candidate_call):
        matches = [item for item in calls[call]["targets"] if item["level_bottom0"] == level_bottom0]
        if len(matches) != 1:
            raise ValueError("requested call/level is not unique in the captured analysis")
        targets.append(matches[0]["stage_values"])
    sw = np.asarray([item["activation_fraction"]["sw_percent"] for item in targets])
    fraction = np.asarray([item["activation_fraction"]["activated_fraction"] for item in targets])
    if not np.isfinite(sw).all() or not np.all(sw > 0) or not np.isfinite(fraction).all():
        raise ValueError("this figure requires two finite positive-supersaturation endpoints")

    import matplotlib.pyplot as plt

    labels = ["Baseline", "Alpha 0.25"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    axes[0, 0].bar(labels, sw, color=["#557d9b", "#d49a45"])
    axes[0, 0].set(yscale="log", ylabel="Percent supersaturation", title="Actual activation-entry supersaturation")
    axes[0, 0].axhline(0.48, color="black", linestyle=":", label="Activation fraction reaches 1 at 0.48%")
    axes[0, 0].legend(fontsize=8)
    for i, value in enumerate(sw):
        axes[0, 0].text(i, value * 1.15, f"{value:.8g}%", ha="center", fontsize=9)
    axes[0, 0].set_ylim(min(sw) / 2, max(sw) * 2)
    axes[0, 1].bar(labels, fraction, color=["#557d9b", "#d49a45"])
    axes[0, 1].set(ylim=(0, 1.15), ylabel="Activated fraction", title="Captured activation fraction")
    for i, value in enumerate(fraction):
        axes[0, 1].text(i, value + 0.025, f"{value:.8g}", ha="center", fontsize=9)

    stages = ["Entry", "Post activation", "Post satadj\nraw NCCN", "Post NCCN\nclamp", "Post DSD"]
    for axis, target, label in zip(axes[1], targets, labels):
        nc = np.asarray([target["activation_entry"]["nc"], target["post_activation"]["nc_pp"],
                         target["post_satadj"]["nc_final"], target["post_satadj"]["nc_final"],
                         target["post_final_dsd"]["nc"]]) / 1e6
        nn = np.asarray([target["activation_entry"]["nccn"], target["post_activation"]["nccn_pp"],
                         target["post_satadj"]["nccn_final_raw"], target["post_satadj"]["nccn_final"],
                         target["post_final_dsd"]["nccn"]]) / 1e6
        if not np.isfinite(nc).all() or not np.isfinite(nn).all():
            raise ValueError("nonfinite captured number coordinates")
        axis.bar(stages, nc, label="NC", color="#557d9b")
        axis.bar(stages, nn, bottom=nc, label="NCCN", color="#d49a45")
        axis.axhline(nc[0] + nn[0], color="black", linestyle=":", linewidth=1)
        axis.set(title=label + ": captured NC/NCCN stages", ylabel="Legacy raw coordinates / 1e6")
        axis.set_ylim(0, max(nc + nn) * 1.18)
        axis.tick_params(axis="x", labelsize=8)
        axis.legend(loc="upper center", ncol=2, fontsize=8)
        for i, value in enumerate(nc + nn):
            axis.text(i, value + max(nc + nn) * 0.025, f"{value:.2f}", ha="center", fontsize=8)
    fig.suptitle(f"Original B512 block22, native (167,50,{level_bottom0+1}): actual observed activation stages\n"
                 "NC moves before the NCCN floor is restored; raw-coordinate accounting is not physical-unit certification")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        fig.savefig(stream, format="png", dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("activation figure requires a new path")
    plot_trace(json.loads(args.analysis.read_text()), args.output)
    print(json.dumps({"analysis_sha256": hashlib.sha256(args.analysis.read_bytes()).hexdigest(),
                      "plotter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "figure_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
