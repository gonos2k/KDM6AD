#!/usr/bin/env python3
"""The same closure under both measures, side by side (owner §9).

`den` passed to the kernel is MOIST-air density,

    rho_m = rho_d (1 + qv)          (module_big_step_utilities_em.F:4856)

while `nr` and the `q` fields are mixing ratios per DRY-air kg. So there are two
different column integrals and they are not the same quantity:

    operator measure   sum_k rho_m,k dz_k x_k     what the operator's own budget is
    physical measure   sum_k rho_d,k dz_k x_k     what is physically conserved

Reporting one of them makes a statement about the OPERATOR read as a statement
about the ATMOSPHERE. Both are reported, always, so a reader cannot pick up the
wrong one by accident.

## The claim this exists to test

"Absolute values shift with the basis but RATIOS are unaffected" is only true if
rho_m/rho_d = 1+qv is vertically CONSTANT (owner §9.3). It is not: qv varies with
height, and in a real case it varies a great deal. So the divergence between the
two ratios is MEASURED here rather than argued.

    python g33_dual_ledger.py <driver---nflux> <nsplit> [out.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_matched_closure as mc  # noqa: E402
import g33_number_transport as nt  # noqa: E402


def humidity(stream: str) -> dict:
    """Per column: the spread of 1+qv, and whether sedimentation moved qv.

    The basis conversion is exactly `1+qv`, so its VERTICAL SPREAD is what decides
    whether the two ratios can differ. A column where it is constant is one where
    the basis genuinely cancels -- which is a property of the fixture, not a
    property of the operator, and must not be generalised.
    """
    out = {}
    for call in nt.calls(stream):
        for lp in sorted(call["loops"]):
            pre, post = call["outer_pre_sed"], call["outer_post_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                f = [1.0 + pre[(lp, col, k)]["qv"] for k in ks]
                d = out.setdefault(col, {"min": min(f), "max": max(f),
                                         "max_qv_change": 0.0})
                d["min"], d["max"] = min(d["min"], min(f)), max(d["max"], max(f))
                # Sedimentation moves hydrometeors, not vapour. Using the pre-sed
                # density at both endpoints is only sound if that holds, and both
                # endpoints carry qv, so it is checked rather than assumed.
                d["max_qv_change"] = max(
                    d["max_qv_change"],
                    max(abs(post[(lp, col, k)]["qv"] - pre[(lp, col, k)]["qv"])
                        for k in ks))
    for d in out.values():
        d["spread"] = d["max"] - d["min"]
    return out


def analysis(stream: str) -> dict:
    """Every row under both measures, with the ratio divergence between them."""
    both = {b: mc.analysis(stream, b) for b in mc.MEASURES}
    rows = {}
    for key in sorted(both["operator"]):
        o, p = both["operator"][key], both["physical"][key]
        ro, rp = o["number_result"], p["number_result"]
        rows[key] = {
            "operator": {"surface_out": o["surface_out"],
                         "residual": o["residual"], "usable": o["usable"],
                         "ratio": ro},
            "physical": {"surface_out": p["surface_out"],
                         "residual": p["residual"], "usable": p["usable"],
                         "ratio": rp},
            # The §9.3 question, as a number: how far apart are the two ratios?
            "ratio_divergence": (abs(ro - rp) / abs(ro)
                                 if ro not in (None, 0.0) and rp is not None
                                 else None),
        }
    return {"rows": rows, "humidity": humidity(stream),
            "basis_note": "operator = rho_m*dz (what the kernel budgets); "
                          "physical = rho_d*dz (what is conserved). rho_d = "
                          "rho_m/(1+qv)."}


def report(stream: str) -> None:
    a = analysis(stream)
    print("  Both measures, always. operator = rho_m*dz, physical = rho_d*dz.\n")
    print(f"  {'row':14} {'operator ratio':>15} {'physical ratio':>15} "
          f"{'divergence':>11}")
    for k, r in a["rows"].items():
        o, p = r["operator"]["ratio"], r["physical"]["ratio"]
        if o is None and p is None:
            continue
        dv = (f"{100*r['ratio_divergence']:.4f}%"
              if r["ratio_divergence"] is not None else "-")
        print(f"  {k:14} {100*o:14.4f}% {100*p:14.4f}% {dv:>11}")
    print("\n  The basis conversion is 1+qv. Its VERTICAL SPREAD is what decides")
    print("  whether the two ratios can differ at all:")
    for col, h in sorted(a["humidity"].items()):
        print(f"    col {col}: 1+qv in [{h['min']:.6f}, {h['max']:.6f}], "
              f"spread {h['spread']:.3e}, max |dqv| across sed {h['max_qv_change']:.3e}")


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    r = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    report(r.stdout)
    if len(argv) == 3:
        Path(argv[2]).write_text(
            json.dumps(analysis(r.stdout), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
