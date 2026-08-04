#!/usr/bin/env python3
"""What the 9-15% is a percentage OF (owner §11).

The headline number is

    R_N / F_surface

the number-creation residual over the surface number outflow. It is the natural
denominator for *"is the transport accounting closed"*, and it is the wrong one
for almost every sentence a reader is tempted to write next. It does **not** say

    the column gained 9-15% more particles
    the mean particle diameter fell 3-5%
    reflectivity dropped 10%
    precipitation changed by 9-15%

so the same residual is reported here against every denominator that means
something, side by side, with the mean particle mass beside it. A number with one
denominator invites the reader to supply their own.

    R / F_surface     closure -- is the transport accounting closed
    R / N_initial     what fraction of what the column STARTED with was invented
    R / N_final       what fraction of what it ENDED with is spurious
    R / N_transported what fraction of what MOVED was invented

    python g33_defect_magnitude.py <driver---nflux> <nsplit> [out.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_cap_interface as ci  # noqa: E402
import g33_matched_closure as mc  # noqa: E402

#: chain -> (mass species, number species): mean particle mass is q/N.
PAIRS = {"main": ("qr", "nr"), "ice": ("qi", "ni")}


def _ratio(num, den):
    return num / den if den else None


def _eps(d):
    """Spurious fraction of the FINAL column number."""
    return _ratio(d["residual"], d["final"])


def _defect_mass_bias(d):
    """Mean particle mass q/N is deflated by 1/(1+eps) when N carries eps
    spurious. Mass is unaffected -- its control closes -- so all of it lands on
    the ratio."""
    e = _eps(d)
    return None if e is None or e <= -1 else 1.0 / (1.0 + e) - 1.0


def _defect_diameter_bias(d):
    """A characteristic diameter goes as (q/N)^(1/3), so the same eps moves it by
    a cube root -- which is why a 15%-sounding number is not a 3-5% diameter
    change."""
    e = _eps(d)
    return None if e is None or e <= -1 else (1.0 + e) ** (-1.0 / 3.0) - 1.0


def analysis(stream: str, basis: str = "operator") -> dict:
    acc = mc.closures(stream, basis)
    # Interface throughput: how much number CROSSED an interface,
    # which is what the creation is a fraction of. The surface
    # transfer alone is already R/F_surface.
    iface = ci.interfaces(stream)
    ctrl = {(ch, col): mc.usable(d) for (ch, sp, col), d in acc.items()
            if sp.startswith("q")}
    rows = {}
    for (ch, sp, col), d in sorted(acc.items()):
        if sp.startswith("q"):
            continue
        ok, why = ctrl.get((ch, col), (False, "no_mass_control_for_this_chain"))
        if not ok:
            rows[f"{ch}/{sp}/{col}"] = {"usable": False, "reason": why}
            continue
        mass = acc.get((ch, PAIRS[ch][0], col))
        rows[f"{ch}/{sp}/{col}"] = {
            "usable": True,
            "residual": d["residual"],
            "of_surface_flux": _ratio(d["residual"], d["out"]),
            "of_initial_column": _ratio(d["residual"], d["start"]),
            "of_final_column": _ratio(d["residual"], d["final"]),
            "of_interface_throughput": _ratio(
                d["residual"], iface.get((ch, col), {}).get("number_transported")),
            # Mean particle mass, from the SAME rows: q/N is what a size-dependent
            # diagnostic (fall speed, reflectivity, diameter) actually responds to,
            # and a number error moves it only through this ratio.
            "mean_particle_mass_initial": _ratio(mass["start"], d["start"])
                                          if mass else None,
            "mean_particle_mass_final": _ratio(mass["final"], d["final"])
                                        if mass else None,
            # The TOTAL change in mean particle mass across the segment. This
            # is NOT the defect's effect: sedimentation genuinely size-sorts,
            # because large particles fall faster, so most of this is physics.
            "mean_particle_mass_change_total": (
                _ratio(mass["final"], d["final"]) / _ratio(mass["start"], d["start"]) - 1.0
                if mass and d["start"] and d["final"] and mass["start"] else None),
            # The part attributable to the DEFECT, which is the only part a
            # reflectivity or fall-speed argument may use. Number inflated by
            # eps = R/N_final deflates q/N by 1/(1+eps), and a characteristic
            # DIAMETER goes as (q/N)^(1/3).
            "defect_mean_mass_bias": _defect_mass_bias(d),
            "defect_diameter_bias": _defect_diameter_bias(d),
        }
    return {"rows": rows,
            "note": "R/F_surface is a CLOSURE statistic. It is not a column "
                    "increase, a diameter change, a reflectivity change or a "
                    "precipitation change."}


def report(stream: str) -> None:
    a = analysis(stream)
    print("  The same residual against every denominator that means something.\n")
    f = lambda x: f"{100*x:10.4f}%" if x is not None else "          -"
    print(f"  {'row':12} {'/F_surface':>11} {'/N_initial':>11} {'/N_final':>11} "
          f"{'/throughput':>11}")
    for k, r in a["rows"].items():
        if not r["usable"]:
            print(f"  {k:12}  unusable — {r['reason'][:52]}")
            continue
        if r["of_surface_flux"] is None:
            continue
        print(f"  {k:12} {f(r['of_surface_flux'])} {f(r['of_initial_column'])} "
              f"{f(r['of_final_column'])} {f(r['of_interface_throughput'])}")
    print("\n  What the defect does to PARTICLE SIZE — the only route by which a")
    print("  number error reaches reflectivity or fall speed. The total column is")
    print("  NOT the defect: sedimentation genuinely size-sorts.\n")
    print(f"  {'row':12} {'total d(q/N)':>13} {'defect d(q/N)':>14} "
          f"{'defect d(diameter)':>19}")
    for k, r in a["rows"].items():
        if not r["usable"] or r["defect_mean_mass_bias"] is None:
            continue
        print(f"  {k:12} {f(r['mean_particle_mass_change_total'])[:-1]:>13} "
              f"{f(r['defect_mean_mass_bias'])[:-1]:>14} "
              f"{f(r['defect_diameter_bias'])[:-1]:>19}")
    print("\n  " + a["note"])


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
