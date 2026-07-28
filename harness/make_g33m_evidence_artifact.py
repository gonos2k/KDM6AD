#!/usr/bin/env python3
"""Emit the committed dt=300 evidence summary from the bundles, deterministically.

The previous artifact was assembled by an ad-hoc script that no longer exists, so the
committed JSON could not be regenerated from the bundles it claims to describe — and
a summary nobody can reproduce is a claim, not evidence. This is that generator.

It also fixes what the artifact PROVED about the outer-loop carry. The old check
compared the NUMBER of differing records at loop L's post-micro against loop L+1's
pre-sed:

    count(L1 outer_post_micro) == count(L2 outer_pre_sed)

Equal counts of entirely different cells pass that. The carry is now proven by a
digest over the differing records' (field, column, level) identities AND their raw
bits, so the two ends must differ in the same places by the same amounts.

    make_g33m_evidence_artifact.py --evidence DIR --fixture-id ID \
        [--gate-a-report PATH] --out harness/evidence/g33m_dt300_result.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))
import g33_bundle_io as bio            # noqa: E402
import g33_fixture_v1 as gfx           # noqa: E402
import g33_fortran_dump as fd          # noqa: E402
import g33_normalize as nz             # noqa: E402
import g33_schedule_probe as gsp       # noqa: E402

#: Constants, NOT the model's Lv(T)/cpm(q). Recorded in the artifact so the residual
#: is read as a constant-coefficient diagnostic and not as a bound.
LV_CONST, CP_CONST = 2.5e6, 1004.0
STAGE_ORDER = ("outer_pre_sed", "substep_pre", "surface",
               "outer_post_sed", "outer_post_micro", "final_output")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _f32(bits) -> float:
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def _git(*args, default="unknown") -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True, cwd=ROOT.parent).stdout.strip()
    except Exception:
        return default


def _key(rec):
    return (rec["stage"], rec["loop"], rec["chain"], rec["n"], rec["col"],
            rec["k"], rec["field"])


def _digest(pairs) -> str:
    """A digest over (identity, f_bits, c_bits), so it pins WHERE and BY HOW MUCH."""
    h = hashlib.sha256()
    for ident, fb, cb in sorted(pairs):
        h.update(f"{ident}|{fb:08x}|{cb:08x}\n".encode())
    return h.hexdigest()


def _carry_proof(diff, loops):
    """The carry, proven by identity and bits rather than by counting.

    outer_post_micro(L) and outer_pre_sed(L+1) are the same state observed twice, so
    the SAME cells must differ by the SAME amounts. Equal counts of different cells
    is what the previous check accepted.
    """
    out = {}
    for loop in loops[:-1]:
        post = {(k[6], k[4], k[5]): v for k, v in diff.items()
                if k[0] == "outer_post_micro" and k[1] == loop}
        pre = {(k[6], k[4], k[5]): v for k, v in diff.items()
               if k[0] == "outer_pre_sed" and k[1] == loop + 1}
        out[f"L{loop}->L{loop + 1}"] = {
            "post_micro_digest": _digest((str(i), f, c) for i, (f, c) in post.items()),
            "pre_sed_digest": _digest((str(i), f, c) for i, (f, c) in pre.items()),
            "identical": post == pre,
            "records": len(post),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--fixture-id", default="arithmetic_multisubcycle_v1")
    ap.add_argument("--gate-a-report", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    EV = a.evidence
    _, auth = gfx.load_fixture(a.fixture_id)
    bundle = bio.verify_cpp_bundle(EV / "cpp-bundle",
                                   expected_fixture_id=a.fixture_id)

    per_algo, closure, first_div, carry = {}, [], {}, {}
    for algo in ("legacy", "conservative"):
        raw = (EV / f"fortran-{algo}" / "C" / "stdout.g33f").read_text()
        F = nz.from_fortran_run(fd.parse_fortran_run(raw, algo, auth["K"], auth["B"]))
        C = nz.from_cpp_evidence(bundle["algorithms"][algo],
                                 require_verdict_ready=False)
        fk = {_key(s): s["bits"] for s in F["stages"]}
        ck = {_key(s): s["bits"] for s in C["stages"]}
        shared = set(fk) & set(ck)
        diff = {k: (fk[k], ck[k]) for k in shared if fk[k] != ck[k]}
        loops = sorted({k[1] for k in shared if k[1] > 0})
        cnt = Counter((k[1], k[0]) for k in diff)

        # final_output carries loop=0 meaning "not loop-scoped", so ordering by the
        # raw loop number puts the WHOLE-STEP result before loop 1. It sorts last,
        # as it does in the comparator — otherwise the artifact would name a
        # different first divergence than the gate that produced the verdict.
        _LAST = 1 << 30
        earliest = min(diff, key=lambda k: (_LAST if k[0] == "final_output" else k[1],
                                            STAGE_ORDER.index(k[0]), k[3], k[4],
                                            k[5], k[6]), default=None)
        if earliest is not None:
            fb, cb = diff[earliest]
            first_div[algo] = {
                "identity": list(earliest),
                "f_bits": f"{fb:#010x}", "c_bits": f"{cb:#010x}",
                "f_value": _f32(fb), "c_value": _f32(cb),
            }
        per_algo[algo] = {
            "fortran_manifest_sha256": _sha(EV / f"fortran-{algo}" / "abc_manifest.json"),
            "shared_stage_records": len(shared),
            "differing_stage_records": len(diff),
            "differing_by_loop_and_stage": {
                f"L{lp}/{st}": cnt[(lp, st)] for lp in loops for st in STAGE_ORDER
                if cnt.get((lp, st))},
            "differing_digest": _digest(
                (str(k), f, c) for k, (f, c) in diff.items()),
            "mstep_range": list(bundle["algorithms"][algo].mstep_range or ()),
            "probe_lineage": dict(bundle["algorithms"][algo].probe_lineage or {}),
        }
        carry[algo] = _carry_proof(diff, loops)

        if algo == "legacy":
            # EVERY cell where the condensation triple actually differs, not the
            # column the first divergence happens to sit in — those need not be the
            # same place, and pinning the closure to the latter reported zeros.
            cells = sorted({(k[4], k[5]) for k in diff
                            if k[0] == "outer_post_micro" and k[1] == 1
                            and k[6] in ("qv", "qc", "t")})
            for col, k in cells:
                try:
                    g = lambda f: (_f32(fk[("outer_post_micro", 1, "-", 0, col, k, f)]),
                                   _f32(ck[("outer_post_micro", 1, "-", 0, col, k, f)]))
                    (qv_f, qv_c), (qc_f, qc_c), (t_f, t_c) = g("qv"), g("qc"), g("t")
                except KeyError:
                    continue
                dqv, dqc, dT = qv_c - qv_f, qc_c - qc_f, t_c - t_f
                closure.append({
                    "col": col, "k": k,
                    "delta_qv_abs_kg_kg": dqv, "delta_qc_abs_kg_kg": dqc,
                    "delta_qv_rel": dqv / qv_f if qv_f else None,
                    "delta_qc_rel": dqc / qc_f if qc_f else None,
                    "delta_T_K": dT, "delta_T_rel": dT / t_f if t_f else None,
                    "Lv_J_kg": LV_CONST, "cp_J_kg_K": CP_CONST,
                    "latent_predicted_delta_T_K": LV_CONST / CP_CONST * dqc,
                    "closure_residual_q_kg_kg": dqv + dqc,
                    "closure_residual_T_K": dT - LV_CONST / CP_CONST * dqc,
                })

    result = json.loads((EV / "result.json").read_text())
    art = {
        "schema_version": 2,
        "what": f"Gate B / G3.3-M four-case run at {a.fixture_id}",
        "generated_by": "harness/make_g33m_evidence_artifact.py",
        "verdict": result["verdict"],
        "attested": result["attested"],
        "reason": result["reason"],
        "verifier_commit": _git("rev-parse", "HEAD"),
        "verifier_tree_dirty": bool(_git("status", "--porcelain", default="?")),
        "producer_commit": json.loads(
            (EV / "fortran-legacy" / "abc_manifest.json").read_text())["repo_commit"],
        "fixture": {
            "id": a.fixture_id,
            "manifest_sha256": gfx.manifest_sha256(auth),
            "dt_s": struct.unpack(">f", bytes.fromhex(
                auth["common_parameters"]["dt"]))[0],
            "B": auth["B"], "K": auth["K"],
            "outer_loops": gsp.step_schedule(auth)[0],
            "dtcld_s": gsp.step_schedule(auth)[1],
        },
        "cpp_manifest_sha256": _sha(EV / "cpp-bundle" / "cpp_abc_manifest.json"),
        "gate_a_report_sha256": _sha(a.gate_a_report) if a.gate_a_report else None,
        "first_divergence": first_div,
        "per_algorithm": per_algo,
        # identity + bits, not counts: equal numbers of different cells used to pass
        "carry_proof": carry,
        "condensation_closure": {
            "note": "Lv and cp are CONSTANTS here, not the model's Lv(T) and cpm(q). "
                    "The residual is a constant-coefficient DIAGNOSTIC, not a bound. "
                    "This is saturation-adjustment-CONSISTENT, not a proof of the "
                    "operator.",
            "t_is": "temperature (CoordinatorState::t, documented absolute [K]); the "
                    "returned STATE carries `th` separately, so no Exner factor is "
                    "applied",
            "levels": closure,
        },
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix(a.out.suffix + ".tmp")
    tmp.write_text(json.dumps(art, indent=2, sort_keys=True) + "\n")
    tmp.replace(a.out)
    print(f"wrote {a.out}")
    print(f"  verdict {art['verdict']} | attested {art['attested']} | "
          f"dirty {art['verifier_tree_dirty']}")
    for algo, c in carry.items():
        for span, v in c.items():
            print(f"  carry {algo:13s} {span}: identical={v['identical']} "
                  f"({v['records']} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
