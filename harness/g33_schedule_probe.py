#!/usr/bin/env python3
"""Two-pass C++ substep schedule: probe it, re-derive it in Python, then seal it.

The C++ expectation manifest must declare `loops` and `mstepmax_{chain}[loop]` BEFORE
the run, because that declaration is what makes it independent evidence. But the
per-loop mstep is knowable only BY running: it comes from the fall speeds of that
loop's evolved state.

Three ways out; two are closed:

  * take the numbers from the Fortran leg — REJECTED. If the backends ever computed a
    different mstep (an upstream CFL/fall-speed difference, exactly what G3.3-M exists
    to surface), the C++ contract would have been built from the Fortran answer and
    the disagreement would be masked instead of reported.
  * over-declare the sealed contract to the algorithm's mstep ceiling and let the run
    write fewer containers — DISPROVED BY EXPERIMENT, not by argument. `op_seq_id` is
    a process-global counter and each descriptor line pins it, so loop 2's descriptor
    expects ids after loop 1's DECLARED substeps while the run has only advanced by
    its ACTUAL ones. Observed on the real driver as
    `expected: 21806|surface|... actual: 1968|surface|...`.
  * a separate PROBE CHANNEL that bypasses the sealed machinery entirely — the
    `KDM6SCHED` stdout stream (`sched_emit`, inert unless `KDM6_G33_SCHED_PROBE` is
    set). That is what this module reads.

A probe run carries no run identity, no binary binding and no sealed descriptor, so
it is a SCHEDULE-DISCOVERY artifact and never physics evidence. Nothing here produces
a sealed container, so a probe cannot be mistaken for one: it is a different artifact,
not a flagged one.

The producer is not trusted either: Python re-derives the mstep vector from the raw
fall speeds in the stream and requires the run's own `mstep_native` to match. The
stream carries all FOUR speeds `numdt` maximises over — including `work1_qs` and
`work1_qg`, which the sealed evidence omits and which frequently decide mstep.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_derived as gd            # noqa: E402

class ProbeError(Exception):
    """The probe cannot yield a schedule that can be sealed."""


def derive_mstep(vmax_per_column, dtcld: float) -> list[int]:
    """The substep count Python computes from the raw fall speeds.

    `nint(x + 0.5)` is exactly `floor(x + 1)` for x >= 0 (ties round away from zero),
    which is also what the C++ path computes, so this is the reference relation and
    not a re-spelling of it.
    """
    lo, hi = gd.MSTEP_RANGE
    return [min(hi, max(lo, math.floor(v * dtcld + 1.0))) for v in vmax_per_column]


def _vmax_per_column(rec: dict, columns: int) -> list:
    """max_k over every fall speed numdt maximises over, per column.

    The work fields are whole-column (B, K) payloads in row-major order; mstep is
    (B,). Treating a work field as per-column would read K levels of column 0 and
    call them B columns.
    """
    out = []
    for field in _WORK_FIELDS:
        values = rec[field]
        if len(values) % columns:
            raise ProbeError(f"{field} has {len(values)} values, not a multiple of "
                             f"the {columns} columns")
        levels = len(values) // columns
        per_col = [max(values[c * levels:(c + 1) * levels]) for c in range(columns)]
        out = per_col if not out else [max(a, b) for a, b in zip(out, per_col)]
    return out

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
            entry = seen.setdefault((loop, chain), {"mstep": None, "n_seen": set()})
            entry["n_seen"].add(n)
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
            # EVERY substep, not the furthest one. Comparing max(n) against mx let a
            # probe that emitted only {1, 9} seal a nine-substep schedule: the gap is
            # exactly where a producer that skipped work would hide.
            ran = set(entry["n_seen"])
            if ran != set(range(1, mx + 1)):
                gaps = sorted(set(range(1, mx + 1)) - ran)
                raise ProbeError(
                    f"loop {loop} chain {chain}: mstep implies substeps 1..{mx} but "
                    f"the probe ran {sorted(ran)}"
                    + (f" — never {gaps}" if gaps else " — and more besides"))
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

#: every fall speed `numdt` maximises over (module_mp_kdm6.F:1126). The sealed
#: evidence carries only the first two, which is why a probe is the only place the
#: substep count can be re-derived from ALL of its own inputs.
_WORK_FIELDS = ("work1_qr", "workn_qr", "work1_qs", "work1_qg")

_SCHED_TAG = "KDM6SCHED"

#: The probe's lineage record, written beside schedule.json and copied into the
#: bundle. Named here because the producer and the verifier both need it: a bundle
#: that ships a schedule without the stream it came from can only be taken on trust.
PROBE_MANIFEST = "probe_manifest.json"
PROBE_STREAM = "probe.sched"
PROBE_SCHEDULE = "schedule.json"

#: Exactly what a probe scope may carry. Closed, because the stream's whole purpose
#: is to become a sealed container universe.
_PROBE_FIELDS = frozenset((*_WORK_FIELDS, "mstep_native", "dtcld"))


def parse_sched_stream(raw) -> dict:
    """(loop, chain, n) -> {field: [decoded values]} from a KDM6SCHED stdout stream.

    Strict: a malformed line is a broken probe, not a line to skip. Silently
    tolerating one would let a truncated stream seal a schedule built from whatever
    survived.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="strict")
    out: dict = {}
    for line in raw.splitlines():
        if not line.startswith(_SCHED_TAG + " "):
            continue
        tok = line.split()
        if len(tok) < 7:
            raise ProbeError(f"malformed probe line: {line!r}")
        _, loop, chain, n, field, dtype, count = tok[:7]
        words = tok[7:]
        try:
            scope = (int(loop), chain, int(n))
            n_el = int(count)
        except ValueError:
            raise ProbeError(f"non-integer scope in probe line: {line!r}") from None
        if len(words) != n_el:
            raise ProbeError(f"probe line declares {n_el} values, carries "
                             f"{len(words)}: {line!r}")
        width = {"f32": 8, "f64": 16, "i32": 8}.get(dtype)
        if width is None or any(len(w) != width for w in words):
            raise ProbeError(f"probe line has bad dtype/word width: {line!r}")
        if field not in _PROBE_FIELDS:
            raise ProbeError(f"unknown probe field {field!r}: the stream builds a "
                             f"sealed contract, so its schema is closed")
        payload = bytes.fromhex("".join(words))
        rec = out.setdefault(scope, {})
        if field in rec:
            # last-wins is never right here: the survivor would seal the contract
            raise ProbeError(f"duplicate {field!r} record for {scope}")
        rec[field] = list(gd.unpack_values(dtype, payload))
    if not out:
        raise ProbeError("probe stream carries no KDM6SCHED records")
    return out


def probe_from_stream(raw) -> dict:
    """A probe reading, with the producer's own mstep INDEPENDENTLY re-derived.

    Returns the same shape `sealed_schedule` consumes. The derivation is the point:
    reading `mstep_native` alone would seal whatever the producer claimed, so the
    vector is recomputed from the fall speeds and the two must agree exactly.
    """
    parsed = parse_sched_stream(raw)
    seen: dict = {}
    for (loop, chain, n), rec in sorted(parsed.items()):
        entry = seen.setdefault((loop, chain), {"mstep": None, "n_seen": set()})
        entry["n_seen"].add(n)
        if n != 1:
            continue                      # mstep is fixed before the substep loop
        missing = [f for f in (*_WORK_FIELDS, "mstep_native", "dtcld")
                   if f not in rec]
        if missing:
            raise ProbeError(f"loop {loop} chain {chain}: probe is missing "
                             f"{missing} — the substep count cannot be re-derived")
        dtcld = rec["dtcld"]
        if len(set(dtcld)) != 1:
            raise ProbeError(f"loop {loop} chain {chain}: dtcld differs across "
                             f"columns: {sorted(set(dtcld))}")
        if not (math.isfinite(dtcld[0]) and dtcld[0] > 0):
            raise ProbeError(f"loop {loop} chain {chain}: dtcld {dtcld[0]!r} is not "
                             f"a positive finite timestep")
        # ADMISSIBILITY, not arithmetic. derive_mstep clamps a negative speed to 1,
        # which is the right formula and the wrong conclusion: a negative or
        # non-finite fall speed is a broken measurement, not a one-substep run.
        for field in _WORK_FIELDS:
            for i, v in enumerate(rec[field]):
                if not math.isfinite(v) or v < 0:
                    raise ProbeError(
                        f"loop {loop} chain {chain}: {field}[{i}] = {v!r} is outside "
                        f"the fall-speed domain (finite, >= 0)")
        vmax = _vmax_per_column(rec, len(rec["mstep_native"]))
        derived = derive_mstep(vmax, dtcld[0])
        claimed = []
        for v in rec["mstep_native"]:
            if float(v) != int(v):
                raise ProbeError(f"loop {loop} chain {chain}: mstep_native {v} is "
                                 f"not integral")
            claimed.append(int(v))
        if derived != claimed:
            raise ProbeError(
                f"loop {loop} chain {chain}: the run used mstep {claimed} but its "
                f"own fall speeds give {derived} — the producer's schedule is not "
                f"what its operands imply")
        entry["mstep"] = derived
    missing = sorted(k for k, v in seen.items() if not v["mstep"])
    if missing:
        raise ProbeError(f"probe has no n=1 record for {missing}")
    return seen


def switch_margin(raw) -> dict:
    """(loop, chain, column) -> distance to the nearest mstep switch.

    A mechanism fixture must not sit near one: if delta is small a sub-ULP
    fall-speed difference between backends flips the substep count, and the
    comparison is then about scheduling rather than arithmetic. Computable only
    here, because it needs the two fall speeds the sealed evidence omits.
    """
    parsed = parse_sched_stream(raw)
    out: dict = {}
    for (loop, chain, n), rec in sorted(parsed.items()):
        if n != 1 or "dtcld" not in rec:
            continue
        dt = rec["dtcld"][0]
        vmax = _vmax_per_column(rec, len(rec["mstep_native"]))
        for col, v in enumerate(vmax):
            x = v * dt
            m = derive_mstep([v], dt)[0]
            out[(loop, chain, col + 1)] = min(x - (m - 1), m - x)
    return out
