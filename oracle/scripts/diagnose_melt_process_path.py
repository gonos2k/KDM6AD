"""Targeted total-control process path: cold riming -> D5 graupel melt."""
from __future__ import annotations

import json
import math
from pathlib import Path
import torch
from torch.autograd import forward_ad

from kdm6.process_attribution import _run, melt_fixture


def _forward_mode_pgeml(state, forcing) -> tuple[float, float]:
    """Evaluate the scalar total-riming path with genuine torch forward AD."""
    zero = torch.zeros((), dtype=state.qc.dtype)
    one = torch.ones_like(zero)
    with forward_ad.dual_level():
        alpha = forward_ad.make_dual(zero, one)
        _, trace, handle = _run(state, forcing, "riming", alpha, dt=20.0, graph=False)
        try:
            primal, tangent = forward_ad.unpack_dual(
                trace.by_name("d5_melt")[0].rates.pgeml.reshape(-1)[0])
            return float(primal.detach()), float(tangent.detach())
        finally:
            handle.close()


def run_probe():
    state, forcing = melt_fixture()
    alpha = torch.tensor(0.0, dtype=torch.float64, requires_grad=True)
    out, trace, handle = _run(state, forcing, "riming", alpha, dt=20.0, graph=True)
    try:
        # D5 is generated before conservation limiting.  The causal source
        # record is therefore the controlled cold bundle, while
        # ``cold_limited`` is a later applied-rate record and must not be
        # presented as upstream of D5.
        cold = trace.by_name("cold")[0].rates
        d5 = trace.by_name("d5_melt")[0].rates
        ad = torch.autograd.grad(d5.pgeml.reshape(-1)[0], alpha, retain_graph=True)[0]
        forward_pgeml, forward_jvp = _forward_mode_pgeml(state, forcing)
        forward_relative_error = abs(forward_jvp - float(ad.detach())) / max(
            abs(forward_jvp), abs(float(ad.detach())))
        eps_rows = []
        for epsilon in (0.01, 0.03, 0.1):
            hp = hm = None
            try:
                plus, tp, hp = _run(state, forcing, "riming", epsilon, dt=20.0, graph=False)
                minus, tm, hm = _run(state, forcing, "riming", -epsilon, dt=20.0, graph=False)
                fd = (tp.by_name("d5_melt")[0].rates.pgeml -
                      tm.by_name("d5_melt")[0].rates.pgeml) / (2.0 * epsilon)
                eps_rows.append({
                    "epsilon": epsilon,
                    "fd_pgeml": float(fd.reshape(-1)[0]),
                    "relative_error": float(((fd.reshape(-1)[0] - ad).abs() /
                                              torch.maximum(fd.reshape(-1)[0].abs(), ad.abs())).detach()),
                    "same_tapped_topology": trace.signature() == tp.signature() == tm.signature()
                    and trace.subcycles == tp.subcycles == tm.subcycles,
                })
            finally:
                if hp is not None:
                    hp.close()
                if hm is not None:
                    hm.close()
        return {
            "status": "verified_total_riming_to_d5_path" if math.isfinite(float(ad.detach()))
            and math.isfinite(forward_jvp) and forward_relative_error < 1.0e-12 and all(
                row["same_tapped_topology"] and row["relative_error"] < 0.01
                and math.isfinite(row["fd_pgeml"]) for row in eps_rows)
                else "unresolved_path",
            "process": "riming", "source_stage": "cold",
            "source_rate": "riming ProcessControls group", "consumer_stage": "d5_melt",
            "consumer_rate": "pgeml",
            "raw_controlled_paacw_adj_example_rate": float(cold.paacw_adj.detach()),
            "d5_baseline_rate": float(d5.pgeml.detach()), "alpha_vjp_pgeml": float(ad.detach()),
            "alpha_forward_jvp_pgeml": forward_jvp,
            "forward_jvp_primal_pgeml": forward_pgeml,
            "forward_vjp_relative_error": forward_relative_error,
            "eps": eps_rows,
            "interpretation": "admissible total riming ProcessControls intervention -> pre-conservation cold rates -> D5 pgeml; scalar alpha derivative is a VJP, not individual paacw_adj attribution",
        }
    finally:
        handle.close()


def main(out: Path):
    # Bounded inventory denominator: 6 named controls × 3 existing fixtures.
    result = run_probe()
    result["coverage_basis"] = {
        "named_control_fixture_pairs": 18,
        "downstream_path_probed": "total riming control -> D5 pgeml",
        "local_edge_denominator": "not enumerated; no individual paacw_adj causal claim",
        "claim": "bounded representative coverage; not a complete process graph",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main(args.out)
