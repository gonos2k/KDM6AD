"""LC05 full-domain all-sky dual CVT analysis runner (v9.2 evidence run).

Produces the P0-3 evidence artifact under the acceptance criteria of the
external review: max_iter >= 8, no caps, Huber, operational ncmin, slot-time
partition, regime-2 routing + pseudo-RH, a-priori all-level qv B, explicit
time-representativeness tolerance — plus a reproducibility manifest (code
SHA/dirty, command, input/output SHA-256, versions).

artifact_role = "pathology_stress": the 00:00 UTC obs is compared against
the 00:05 slot state under a stated 300 s tolerance, so this artifact
evidences hydrometeor SAFETY under deep convergence, not time-aligned DA
performance (that requires a 23:55 frame or R inflation — roadmap).

Usage:
    python oracle/scripts/run_fulldomain_lc05.py OUT_JSON CASE_ROOT
        [--conserving]

--conserving (v10): P1-1 conserving CVT — mass-hydro diagonal sigma zeroed,
species move only through the signed partition channels; the artifact adds
the water-budget split (P_w stage error vs deliberate qv-diagonal change),
the partition v2 record, and the pw_conserved/final_audited gates.
"""
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

_ORACLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ORACLE))
sys.path.insert(0, str(_ORACLE / "tests"))

WRFIN = ("/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/"
         "ss_real_case_20260619_063620/SS/wrfinput_d01")
GK2A = str(_ORACLE.parent / "GK2A")
CAL = str(_ORACLE / "kdm6" / "obs" / "data" /
          "gk2a_ami_cal_202507190000.json")
SLOT = "202507190000"
MAX_ITER = 8


def _sha256(path, cap_bytes=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _git(*args):
    return subprocess.run(["git", "-C", str(_ORACLE.parent), *args],
                          capture_output=True, text=True).stdout.strip()


def build_manifest(cmd, gk2a_files):
    import numpy
    import torch
    return dict(
        code_sha=_git("rev-parse", "HEAD"),
        code_dirty=bool(_git("status", "--porcelain")),
        command=cmd,
        python=platform.python_version(),
        torch=torch.__version__, numpy=numpy.__version__,
        inputs={str(p): _sha256(p) for p in
                [WRFIN, CAL, *map(str, gk2a_files)]})


def main(out_json, case_root, conserving=False):
    from kdm6.da_fulldomain import run_fulldomain_analysis
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from test_rttov_case_writer import (_CHANNELS, _fixture_p_half,
                                        _fixture_tq)

    t0 = time.time()
    fr = read_wrfout_frame(WRFIN, 0)
    cal = load_cal_table(CAL)
    gk2a_files = slot_files(GK2A, SLOT, channels=CLEAN_IR_CHANNELS)
    pl = read_ko_slot(gk2a_files, cal, stride=8)
    co = payload_to_column_obs(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0)
    print(f"[v9.2] load+collocate {time.time() - t0:.0f}s "
          f"n_assigned={co.n_assigned} obs_vt={co.valid_time_utc} "
          f"frame_vt={fr.meta.get('valid_time_utc')}", flush=True)

    tr, qr = _fixture_tq()
    grids = dict(p_lay=fixture_layer_pressure(), p_half=_fixture_p_half(),
                 t_ref=tr, q_ref=qr)
    rep = run_fulldomain_analysis(
        fr, co, grids, case_root, n_workers=8, max_iter=MAX_ITER,
        channels=_CHANNELS, pseudo_rh=True, time_tolerance_s=300.0,
        qv_levels=int(fr.meta["kme"]), conserving=conserving,
        save_fields=out_json + ".fields.npz")

    from kdm6.da_fulldomain import evaluate_artifact_gates

    rep["artifact_role"] = ("conserving_stress" if conserving
                            else "pathology_stress")
    # the runner-known mode is the external gate contract (fail-closed even
    # if every self-declaration marker regressed away)
    rep["gates"] = evaluate_artifact_gates(
        rep, expected_conserving=conserving)      # ENFORCED below
    # record the ACTUAL argv (a reconstructed command would hide typos the
    # parser rejected or normalized)
    rep["manifest"] = build_manifest(
        "python oracle/scripts/run_fulldomain_lc05.py "
        + " ".join(sys.argv[1:]), gk2a_files)
    with open(out_json, "w") as f:
        json.dump(rep, f, indent=1)
    rep["manifest"]["outputs"] = {
        out_json: _sha256(out_json),
        out_json + ".fields.npz": _sha256(out_json + ".fields.npz")}
    with open(out_json + ".manifest.json", "w") as f:
        json.dump(rep["manifest"], f, indent=1)
    tag = "v10" if conserving else "v9.2"
    wb = rep.get("water_budget")
    print(f"[{tag}] DONE wall={rep['wall_s']:.0f}s sub={rep['n_subspace']} "
          f"(mc {rep['n_model_cloudy']} / r2 {rep['n_regime2']} / clr "
          f"{rep['n_clear_operator']}) "
          f"J {rep['j_trace'][0]['total']:.1f}->"
          f"{rep['j_trace'][-1]['total']:.1f} "
          f"O-B {rep['omb']:.3f}K -> O-A {rep['oma']:.3f}K "
          f"audit={rep['n_audit_evals']} "
          + (f"water_budget={wb} " if wb else "")
          + f"gates={rep['gates']}", flush=True)
    if not rep["gates"]["accepted"]:
        failed = [k for k, v in rep["gates"].items() if not v]
        print(f"[{tag}] ARTIFACT REJECTED — failed gates: {failed}",
              flush=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="LC05 full-domain evidence runner")
    ap.add_argument("out_json")
    ap.add_argument("case_root")
    # strict parsing: a --conservng typo must fail loudly, never run
    # silently as non-conserving
    ap.add_argument("--conserving", action="store_true")
    args = ap.parse_args()
    main(args.out_json, args.case_root, conserving=args.conserving)
