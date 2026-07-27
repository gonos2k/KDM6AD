#!/usr/bin/env python3
"""Two-pass C++ substep schedule: discover it, derive it in Python, then seal it.

The C++ expectation manifest must declare `loops` and `mstepmax_{chain}[loop]` BEFORE
the run, because that declaration is what makes it independent evidence. But the
per-loop mstep is only knowable by running: it comes from the fall speeds of that
loop's evolved state.

Three ways out were considered and two rejected:

  * take the numbers from the Fortran leg — REJECTED. If the backends ever computed a
    different mstep (an upstream CFL/fall-speed difference, exactly what G3.3-M exists
    to surface), the C++ contract would have been built from the Fortran answer and
    the disagreement would be masked instead of reported.
  * let the run DISCOVER its containers — IMPOSSIBLE. The sink refuses any container
    whose id has no pre-sealed op-seq entry and descriptor (g33_op_trace.h), so an
    undeclared substep aborts the run rather than revealing itself.
  * PRE-DECLARE every container the run could possibly need, bounded by the
    algorithm's own ceiling (`MSTEP_RANGE`), and read the schedule back out of what
    the run actually wrote. That is this module.

The probe is a SCHEDULE-DISCOVERY artifact, not G3.3 physics evidence: its case id
carries a probe marker and `assert_not_evidence()` refuses to let one be adjudicated.
Nothing derived here is trusted from the producer either — Python recomputes the mstep
vector from the raw operands and requires the producer's own claim to match.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_derived as gd            # noqa: E402

PROBE_MARKER = "schedparse"          # appears in the probe run's case id


class ProbeError(Exception):
    """The probe cannot yield a schedule that can be sealed."""


def probe_case_id(case_name: str) -> str:
    """A probe's case id is visibly not an evidence case id."""
    return f"{case_name}-{PROBE_MARKER}"


def is_probe(case_id: str) -> bool:
    return str(case_id).endswith(f"-{PROBE_MARKER}")


def assert_not_evidence(case_id: str) -> None:
    """Refuse to treat a probe artifact as physics evidence."""
    if is_probe(case_id):
        raise ProbeError(
            f"{case_id!r} is a schedule-discovery probe, not G3.3 evidence — it is "
            f"produced under an over-declared contract whose container set is "
            f"deliberately incomplete, so it can never support a verdict")


def probe_schedule(base: dict, loops: int) -> dict:
    """A contract that pre-declares every container the run could reach.

    The cap is the algorithm's OWN contract ceiling, not a guess and not a number
    borrowed from the other backend: a run needing more than `MSTEP_RANGE[1]`
    substeps is already an invalid run by `check_producer_flags`.
    """
    cap = gd.MSTEP_RANGE[1]
    if loops < 1:
        raise ProbeError(f"loops must be >= 1, got {loops}")
    return dict(base, case_id=probe_case_id(base["case_id"]), loops=loops,
                mstepmax_main=[cap] * loops, mstepmax_ice=[cap] * loops)


def derive_mstep(vmax_per_column, dtcld: float) -> list[int]:
    """The substep count Python computes from the raw fall speeds.

    `nint(x + 0.5)` is exactly `floor(x + 1)` for x >= 0 (ties round away from zero),
    which is also what the C++ path computes, so this is the reference relation and
    not a re-spelling of it.
    """
    lo, hi = gd.MSTEP_RANGE
    return [min(hi, max(lo, math.floor(v * dtcld + 1.0))) for v in vmax_per_column]


def read_probe(containers: dict) -> dict:
    """(loop, chain) -> {"mstep": [...], "n_seen": int} from a probe run's output.

    The mstep vector is read from the FIRST substep of each (loop, chain): the runtime
    computes it once before the substep loop, so n=1 always carries the whole vector
    even though the loop's substep count is what we are trying to learn.
    """
    seen: dict = {}
    for cid, c in containers.items():
        for r in c["records"]:
            # the scope lives on the RECORD, not the container header
            loop, chain, n = r.get("outer_loop"), r.get("chain"), r.get("n")
            if not isinstance(n, int) or n < 1 or chain in (None, "-"):
                continue                   # outer_* snapshots carry no substep
            entry = seen.setdefault((loop, chain), {"mstep": None, "n_seen": 0})
            entry["n_seen"] = max(entry["n_seen"], n)
            if n == 1 and r.get("stage") == "substep_pre" \
                    and r["field"] == "mstep_decoded_i32":
                entry["mstep"] = list(gd.unpack_values(r["dtype"], r["payload"]))
    missing = sorted(k for k, v in seen.items() if not v["mstep"])
    if not seen or missing:
        raise ProbeError(f"probe has no n=1 mstep vector for {missing or 'any scope'}")
    return seen


def sealed_schedule(base: dict, probe: dict) -> dict:
    """The EXACT contract implied by a probe run: mstepmax_{chain}[loop] = max_c mstep.

    Also requires the run to have executed exactly the substeps its own mstep implies —
    a probe that stopped early would otherwise seal a schedule the evidence run cannot
    reproduce.
    """
    loops = sorted({loop for loop, _chain in probe})
    if loops != list(range(1, len(loops) + 1)):
        raise ProbeError(f"probe outer loops are not 1..N: {loops}")
    out = dict(base, case_id=base["case_id"], loops=len(loops))
    for chain in ("main", "ice"):
        observed = {loop for loop, ch in probe if ch == chain}
        if not observed:
            # A chain with no in-scope species emits nothing at all (the ice chain
            # under species_scope=[qr, nr]). Declaring the neutral 1 matches what the
            # expectation builder emits for it: no containers either way. Deriving a
            # larger number would be inventing evidence that does not exist.
            out[f"mstepmax_{chain}"] = [1] * len(loops)
            continue
        if observed != set(loops):
            raise ProbeError(f"chain {chain!r} appears in loops {sorted(observed)}, "
                             f"not all of {loops} — a partial chain cannot be sealed")
        maxima = []
        for loop in loops:
            entry = probe[(loop, chain)]
            mx = max(entry["mstep"])
            if entry["n_seen"] != mx:
                raise ProbeError(
                    f"loop {loop} chain {chain}: ran {entry['n_seen']} substeps but "
                    f"its own mstep implies {mx} — the probe did not complete")
            maxima.append(mx)
        out[f"mstepmax_{chain}"] = maxima
    return out


def assert_reproduced(probe: dict, evidence: dict) -> None:
    """The sealed evidence run must reproduce the probe's schedule EXACTLY.

    Without this the seal would rest on one run while the verdict rested on another,
    and a schedule that drifts between two runs of the same fixture is a finding, not
    a detail to reconcile.
    """
    if set(probe) != set(evidence):
        raise ProbeError(f"probe scopes {sorted(probe)} != evidence {sorted(evidence)}")
    for scope in sorted(probe):
        want, got = probe[scope]["mstep"], evidence[scope]["mstep"]
        if want != got:
            raise ProbeError(f"{scope}: probe mstep {want} != evidence {got}")
