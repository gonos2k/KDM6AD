#!/usr/bin/env python3
"""Mean particle mass and column number (owner review §7).

Water-mass closure alone does not make a conservative variant complete. The
interface moves MASS with a rho*dz measure and NUMBER with the legacy dz-only one
(sedimentation_conservative.cpp:91-92 against :109), so §7's arithmetic predicts a
transferred population's mean particle mass shifts by the density ratio:

    dq_l / dn_l = (rho_u / rho_l) (dq_u / dn_u)

Measured against the LEGACY run at the same cell, not against the same run's start:
over 300 s of full microphysics q and n change independently through condensation,
nucleation and aggregation, so a changed q/n within one run is ordinary physics.
The interface is the only difference between the two runs, and the TOP level has no
inflow from above, so its ratio of exactly 1 is the control.

Column number is reported as a CHANGE, not a residual. The G33R refinement stream
these functions read carries only mass precipitation; the surface NUMBER flux is
emitted, but on a different stream -- the `--nflux` diagnostic overlay
(`g33_number_transport.py`) -- and even with it a residual would only DEFINE the
process term, not check it. Calling this a balance would claim a closure whose
source/sink terms are still per-cell locals.

The particle-number basis is intentionally unresolved: the state ``n`` may be
number per dry-air kg or number per volume.  ``rho*dz*n`` is therefore reported
as the operator's measure, with the physical interpretation conditional on that
boundary contract; this tool does not settle the units.

Reads the same G33R streams as g33_refine_analyze.
"""
from __future__ import annotations

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra   # noqa: E402

#: (mass, number) pairs the kernel carries as a two-moment species.
PAIRS = (("qr", "nr"), ("qi", "ni"), ("qc", "nc"))

NUMBER_BASIS = ("UNRESOLVED: n may be #/kg_d or #/m3; rho*dz weighting is "
                "reported as the operator measure only")

#: Below this a species is absent and q/n is meaningless, not extreme.
_EPS = 1.0e-12


def _validate_run_contract(run: dict, path: Path, expected_algorithm: str) -> None:
    """Validate the inputs this standalone budget actually uses.

    ``g33_refine_analyze`` deliberately accepts signed final state values: the
    host can expose intermediate QIB/QG pathology, and this diagnostic must not
    turn that observed state into an input-domain verdict.  The quantities used
    as a column measure are different: rho and delz are positive forcing
    metrics, while pii and xland have the same input contracts when present.
    This is the G33R boundary; it cannot claim the larger G33F ladder validation.
    """
    algo = run.get(("meta", "algorithm"))
    if algo != expected_algorithm:
        raise ra.RefineError(
            f"{path.name}: expected {expected_algorithm} stream, got {algo!r}")
    nsplit = run.get(("meta", "nsplit"))
    if not isinstance(nsplit, int) or nsplit < 1:
        raise ra.RefineError(f"{path.name}: nsplit={nsplit!r} must be positive")
    forcing = {k[1] for k in run if k[0] == "forcing"}
    if ("rho" in forcing) != ("delz" in forcing):
        raise ra.RefineError(
            f"{path.name}: rho and delz must be present together for the column measure")
    if forcing and not {"rho", "delz"} <= forcing:
        raise ra.RefineError(
            f"{path.name}: forcing is present without the rho*delz column measure")
    for name in ("rho", "delz", "pii"):
        for key in (k for k in run if k[0] == "forcing" and k[1] == name):
            value = run[key]
            if not math.isfinite(value) or value <= 0.0:
                raise ra.RefineError(
                    f"{path.name}: forcing {name} at {key[2:]} must be finite and > 0")
    for key in (k for k in run if k[0] == "forcing" and k[1] == "xland"):
        if run[key] not in (1.0, 2.0):
            raise ra.RefineError(
                f"{path.name}: forcing xland at {key[2:]} must be 1 or 2")


def _validate_pair(legacy: dict, conservative: dict,
                   legacy_path: Path, conservative_path: Path) -> None:
    _validate_run_contract(legacy, legacy_path, "legacy")
    _validate_run_contract(conservative, conservative_path, "conservative")
    if legacy[("meta", "mode")] != conservative[("meta", "mode")]:
        raise ra.RefineError(
            f"{legacy_path.name} and {conservative_path.name} use different modes")
    # The final STATE/PREC records are the measured response and are expected to
    # differ. Everything that defines the shared experiment must agree before a
    # difference is attributed to the interface variant: declared time/fixture
    # metadata, INITIAL state, and every declared forcing value. Exact equality is
    # the G33R f32-word contract; a tolerance would permit a changed measure.
    shared_meta = ("nsplit", "delt", "loops", "dtcld", "fixture")
    for name in shared_meta:
        lk, ck = ("meta", name), ("meta", name)
        has_legacy, has_conservative = lk in legacy, ck in conservative
        if has_legacy != has_conservative:
            raise ra.RefineError(
                f"{legacy_path.name} and {conservative_path.name} do not both "
                f"declare meta {name}")
        if has_legacy and legacy[lk] != conservative[ck]:
            raise ra.RefineError(
                f"{legacy_path.name} and {conservative_path.name} differ in "
                f"shared meta {name}: {legacy[lk]!r} vs {conservative[ck]!r}")
    for group in ("forcing", "initial"):
        keys = {k for k in legacy if k[0] == group}
        if keys != {k for k in conservative if k[0] == group}:
            raise ra.RefineError(
                f"{legacy_path.name} and {conservative_path.name} differ in "
                f"shared {group} record coverage")
        for key in sorted(keys):
            if legacy[key] != conservative[key]:
                raise ra.RefineError(
                    f"{legacy_path.name} and {conservative_path.name} differ in "
                    f"shared {group} value {key[1:]}: {legacy[key]!r} vs "
                    f"{conservative[key]!r}")


def mean_particle_mass(run: dict, cls: str = "state") -> dict:
    """{(species, col, k): q/n} where both moments are present.

    The units of this quotient remain conditional on the unresolved number
    basis; it is a within-run diagnostic, not an independently settled mass.
    """
    out = {}
    for q, n in PAIRS:
        for key in (k for k in run if k[0] == cls and k[1] == q):
            _, _, c, k = key
            qv, nv = run[key], run[(cls, n, c, k)]
            if qv > _EPS and nv > _EPS:
                out[(q, c, k)] = qv / nv
    return out


def column_number(run: dict, cls: str = "state") -> dict:
    """{(species, col): sum_k rho_k dz_k n_k}, or {} without forcing.

    This is the kernel/operator measure. Calling it a physical column number
    requires an explicit decision whether ``n`` is #/kg_d or #/m3.
    """
    if not any(k[0] == "forcing" for k in run):
        return {}
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    out = {}
    for c in sorted({x for x, _ in cells}):
        ks = [k for cc, k in cells if cc == c]
        for _, n in PAIRS:
            out[(n, c)] = sum(
                run[("forcing", "rho", c, k)] * run[("forcing", "delz", c, k)]
                * run[(cls, n, c, k)] for k in ks)
    return out


def compare(legacy: Path, conservative: Path) -> None:
    """Mean particle mass and column number, conservative against legacy."""
    L, C = ra.read(legacy), ra.read(conservative)
    _validate_pair(L, C, legacy, conservative)
    # NOT ra.require_same_universe: that also demands one algorithm, which is right
    # for members of a refinement chain and wrong here, where comparing the two
    # variants is the point. The record universe must still match.
    kl = {k for k in L if k[0] != "meta"}
    kc = {k for k in C if k[0] != "meta"}
    if kl != kc:
        raise ra.RefineError(f"{legacy.name} and {conservative.name} carry "
                             f"different records ({len(kl ^ kc)} differ)")
    ml, mc = mean_particle_mass(L), mean_particle_mass(C)

    print(f"\n=== {conservative.name} vs legacy ===")
    print("\n  mean particle mass q/n, conservative / legacy   "
          "(§7 predicts rho_u/rho_l per transfer)")
    for key in sorted(set(ml) & set(mc)):
        sp, c, k = key
        top = " <== top level, no inflow" if k == max(
            x[2] for x in ml if x[0] == sp and x[1] == c) else ""
        print(f"    {sp:3} col{c} k{k}   {mc[key] / ml[key]:9.4f}{top}")

    nl, nc = column_number(L), column_number(C)
    if nl:
        print(f"\n  rho*dz column operator measure, conservative / legacy   "
              f"(basis={NUMBER_BASIS}; CHANGE: the surface number flux is not emitted)")
        for key in sorted(nl):
            if nl[key]:
                print(f"    {key[0]:4} col{key[1]}   {nc[key] / nl[key]:9.4f}")


def _members(directory: Path) -> dict[str, Path]:
    """Return the requested member set, refusing absent or non-file members."""
    members = {}
    for path in directory.glob("n*.txt"):
        if not path.is_file():
            raise ValueError(f"member {path} is not a regular file")
        members[path.name] = path
    return members


def _require_matching_members(legacy_dir: Path, conservative_dir: Path):
    if not legacy_dir.is_dir() or not conservative_dir.is_dir():
        raise ValueError("both legacy and conservative paths must be directories")
    legacy, conservative = _members(legacy_dir), _members(conservative_dir)
    if not legacy:
        raise ValueError(f"{legacy_dir} contains no n*.txt members")
    if set(legacy) != set(conservative):
        raise ValueError(
            "legacy/conservative member sets differ: "
            f"missing conservative={sorted(set(legacy) - set(conservative))}, "
            f"extra conservative={sorted(set(conservative) - set(legacy))}")
    return legacy


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        print("usage: g33_number_budget.py <legacy-dir> <conservative-dir>")
        return 2
    a, b = Path(argv[0]), Path(argv[1])
    try:
        members = _require_matching_members(a, b)
        for name in sorted(members):
            compare(members[name], b / name)
    except (OSError, ValueError, ra.RefineError) as exc:
        print(f"number-budget input error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
