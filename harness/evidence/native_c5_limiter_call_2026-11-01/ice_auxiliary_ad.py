"""Conditional ice DSD auxiliary response on the two captured native cells.

QI/NI enter at the captured post-freeze, pre-C3 working coordinate. The slope
and intercept are recomputed while all other producer inputs remain fixed.
This is a local branch interior test, not a host or unit-contract derivative.
"""

import json
import math
from pathlib import Path
import struct

import torch

from oracle.kdm6 import fconst
from oracle.kdm6.constants import LAMDAIMAX, LAMDAIMIN
from .combined_replay import combined, read
from .replay import bits

ROOT = Path(__file__).resolve().parent
EXPONENT = struct.unpack("<f", struct.pack("<f", 1.0 / 3.0))[0]


def rows_for(level):
    packet = json.loads((ROOT / "selected_packet.json").read_bytes())
    return {(r["stage"], r["field"]): r for r in packet["selected_rows"]
            if r["k_zero"] == str(level)}


def auxiliaries(qi, ni, density):
    """Executed slope then block-B intercept order on the smooth ice branch."""
    ratio = torch.clamp(
        fconst.PIDNI * ni / torch.clamp(qi * density, min=1e-30), min=1e-30)
    lam = torch.exp(torch.log(ratio) * EXPONENT)
    rslope = torch.clamp(1.0 / lam, min=1.0 / LAMDAIMAX,
                         max=1.0 / LAMDAIMIN)
    rslope2 = rslope * rslope
    n0i = ni * torch.clamp(lam, min=LAMDAIMIN, max=LAMDAIMAX)
    return n0i, rslope2, lam


def branch_signature(audit):
    return (audit["producers"]["signature"], audit["branches"],
            tuple((g["group"], g["active"], g["binding"], g["factor"])
                  for g in audit["limiter"]))


def diagnose(level, h=2e-4):
    rows = rows_for(level)
    q0 = read(rows, "c4_in", "state.qi")
    n0 = read(rows, "c3_in", "state.ni")
    den = read(rows, "c3_in", "forcing.dend")
    density = torch.tensor([den], dtype=torch.float64)

    def auxiliary_map(q, n, *, check=False, audit=None):
        n0i, slope2, lam = auxiliaries(q, n, density)
        return combined(rows, q, n, check=check, audit=audit,
                        ice_aux=(n0i, slope2)), lam

    q = torch.tensor([q0], dtype=torch.float64)
    n = torch.tensor([n0], dtype=torch.float64)
    n0i, slope2, lam = auxiliaries(q, n, density)
    if not (q0 > 1e-14 and n0 > 0 and LAMDAIMIN < lam.item() < LAMDAIMAX):
        raise ValueError("ice auxiliary smooth branch")
    if bits(n0i[0]) != bits(read(rows, "c4_in", "n0i")):
        raise ValueError("captured ice intercept raw bits")
    if bits(slope2[0]) != bits(read(rows, "c4_in", "s.rslope2_i")):
        raise ValueError("captured ice slope raw bits")
    baseline_audit = {}
    baseline, _ = auxiliary_map(q, n, check=True, audit=baseline_audit)
    signature = branch_signature(baseline_audit)
    pidep = read(rows, "c4_out", "depsub.pidep")
    dt = read(rows, "c5_in", "dtcld")

    def flat_map(x, *, moving):
        qx, nx = x[:1], x[1:]
        if moving:
            return auxiliary_map(qx, nx)[0]
        return combined(rows, qx, nx)

    x = torch.tensor([q0, n0], dtype=torch.float64, requires_grad=True)
    findings = {}
    for name, direction, coefficient in (
        ("relative_qi", torch.tensor([q0, 0.0], dtype=torch.float64), EXPONENT),
        ("relative_ni", torch.tensor([0.0, n0], dtype=torch.float64), 1.0 - EXPONENT),
    ):
        moving = lambda z: flat_map(z, moving=True)
        frozen = lambda z: flat_map(z, moving=False)
        _, jvp = torch.autograd.functional.jvp(moving, x, direction)
        _, frozen_jvp = torch.autograd.functional.jvp(frozen, x, direction)
        extra = (jvp - frozen_jvp).detach()
        expected = dt * coefficient * pidep
        if not math.isclose(extra[0].item(), expected, rel_tol=2e-6, abs_tol=2e-15):
            raise ValueError("ice auxiliary C4 chain derivative")
        if abs(extra[1].item()) > 1e-8:
            raise ValueError("ice auxiliary number derivative")
        cotangent = torch.tensor([1.0, 0.125], dtype=torch.float64)
        _, vjp = torch.autograd.functional.vjp(moving, x, cotangent)
        dual = torch.dot(vjp, direction)
        primal = torch.dot(jvp, cotangent)
        if not math.isclose(dual.item(), primal.item(), rel_tol=2e-10, abs_tol=1e-10):
            raise ValueError("ice auxiliary JVP/VJP duality")

        plus = x.detach() + h * direction
        minus = x.detach() - h * direction
        audits = []
        for endpoint in (plus, minus):
            qe, ne = endpoint[:1], endpoint[1:]
            _, _, le = auxiliaries(qe, ne, density)
            if not (qe.item() > 1e-14 and ne.item() > 0 and
                    LAMDAIMIN < le.item() < LAMDAIMAX):
                raise ValueError("ice auxiliary endpoint branch")
            audit = {}
            auxiliary_map(qe, ne, audit=audit)
            if branch_signature(audit) != signature:
                raise ValueError("ice producer/limiter endpoint branch")
            audits.append(audit)
        actual_direction = (plus - minus) / (2 * h)
        _, actual_jvp = torch.autograd.functional.jvp(moving, x, actual_direction)
        fd = (moving(plus) - moving(minus)) / (2 * h)
        findings[name] = {
            "actual_direction": actual_direction.tolist(),
            "jvp": jvp.tolist(), "actual_direction_jvp": actual_jvp.tolist(),
            "vjp_dual_error": (dual - primal).item(),
            "finite_difference": fd.tolist(),
            "fd_minus_actual_jvp": (fd - actual_jvp).tolist(),
            "extra_qi_from_auxiliary": extra[0].item(),
            "independent_extra_qi": expected,
        }
    return {"level_zero": int(level), "baseline": baseline.tolist(),
            "n0i": n0i.item(), "rslope2_i": slope2.item(),
            "lambda_i": lam.item(), "h": h, "directions": findings,
            "status": "conditional branch interior; scientific status INCONCLUSIVE"}


if __name__ == "__main__":
    print(json.dumps({level: diagnose(level) for level in (20, 22)}, indent=2))
