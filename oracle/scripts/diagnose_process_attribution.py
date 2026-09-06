#!/usr/bin/env python3
"""Write a finite cap-aware process attribution coverage matrix.

Run from the repository root or from oracle/.  The matrix deliberately reports
inactive process/regime pairs as explicit zeros and keeps the distinction
between a fixed-topology local derivative and an admissible process control.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kdm6.process_attribution import coverage_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path,
        default=Path("graphify-out/goal-resolution-20260906-2307/process"),
        help="artifact directory (default: %(default)s)",
    )
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument("--epsilon", type=float, default=1.0e-4)
    parser.add_argument("--dt", type=float, default=20.0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    matrix = coverage_matrix(alpha=args.alpha, epsilon=args.epsilon, dt=args.dt)
    serial = {regime: {process: result.as_dict()
                       for process, result in row.items()}
              for regime, row in matrix.items()}
    payload = {
        "contract": "dimensionless ProcessControls alpha; paired rates and existing donor caps",
        "derivative": "alpha JVP and independent central FD at fixed tapped topology",
        "dt": args.dt, "alpha": args.alpha, "epsilon": args.epsilon,
        "matrix": serial,
    }
    (args.out / "attribution.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n")

    lines = [
        "# Cap-aware process attribution",
        "",
        f"alpha={args.alpha:g}, epsilon={args.epsilon:g}, dt={args.dt:g}s; "
        "all controls use existing ProcessControls and donor caps.",
        "",
        "| regime | process | status | active | state effect | tapped masks/subcycles | water FD/AD | temperature FD/AD |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for regime, row in matrix.items():
        for process, result in row.items():
            lines.append(
                f"| {regime} | {process} | {result.status} | "
                f"{int(result.active)} | {int(result.nonzero_state_effect)} | "
                f"{int(result.tapped_topology_fixed)} | {result.water_fd:.6g}/{result.water_ad:.6g} | "
                f"{result.temperature_fd:.6g}/{result.temperature_ad:.6g} |"
            )
    lines.extend([
        "", "Inactive pairs are explicit zero/unresolved coverage, not evidence of process independence.",
        "Rate derivatives are for the named admissible alpha group; raw rates were not independently perturbed.",
    ])
    (args.out / "attribution.md").write_text("\n".join(lines) + "\n")
    print(args.out / "attribution.json")
    print(args.out / "attribution.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
