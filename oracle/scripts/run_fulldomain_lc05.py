"""LC05 full-domain all-sky dual CVT analysis runner (v9.2/v10 evidence).

Produces the evidence artifact under the acceptance criteria of the external
review: max_iter >= 8, no caps, Huber, operational ncmin, slot-time
partition, regime-2 routing + pseudo-RH, a-priori all-level qv B, explicit
time-representativeness tolerance — plus a full-reproducibility manifest.

artifact_role = "pathology_stress" (default): the 00:00 UTC obs is compared
against the 00:05 slot state under a stated 300 s tolerance, so the artifact
evidences hydrometeor SAFETY under deep convergence, not time-aligned DA
performance (that requires a 23:55 frame or R inflation — roadmap).

Provenance contract (review rounds):
  * snapshot BEFORE the analysis reads anything: code SHA + dirty-content
    digest, every input SHA-256, the RTTOV science assets (fixture trees
    Merkle-hashed, executable/rtcoef/hydrotable resolved exactly like the
    run resolves them, runtime-selection env vars), argv (lossless array),
    cwd, interpreter flags;
  * evidence runs require a CLEAN tree (--allow-dirty is an explicit
    opt-out; the dirty digest is a drift sentinel, NOT reproduction data —
    reproducing a dirty run needs the patch/untracked bundle, roadmap);
  * end-of-run drift re-check over code, inputs, and RTTOV assets; ANY
    start/end mismatch rejects the artifact;
  * a rejected run leaves NOTHING under the canonical approved names —
    every file lands under *.rejected (exit code alone does not protect a
    file-collecting archive step).

Usage:
    python oracle/scripts/run_fulldomain_lc05.py OUT_JSON CASE_ROOT
        [--conserving] [--allow-dirty]

--conserving (v10): P1-1 conserving CVT — mass-hydro diagonal sigma zeroed,
species move only through the signed partition channels; the artifact adds
the water-budget split (P_w stage error vs deliberate qv-diagonal change),
the partition v2 record, and the pw_conserved/final_audited gates.
"""
import hashlib
import json
import os
import platform
import re
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
_RTTOV_ENV = ("AD_RTTOV_HOME", "KDM6_RTTOV_RUNTIME")
# sys.flags fields as of 3.9 — recorded in full so interpreter options that
# change semantics (-O strips asserts, -B, isolation...) are provenance
_PY_FLAGS = ("debug", "inspect", "interactive", "optimize",
             "dont_write_bytecode", "no_user_site", "no_site",
             "ignore_environment", "verbose", "bytes_warning", "quiet",
             "hash_randomization", "isolated", "dev_mode", "utf8_mode")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sha256_safe(path):
    """Missing/unreadable files normalize to a sentinel so an input deleted
    mid-run surfaces as DRIFT (with the rejection manifest still written),
    not as an unhandled exception."""
    try:
        return _sha256(path)
    except OSError:
        return "missing-or-unreadable"


def _git(*args):
    r = subprocess.run(["git", "-C", str(_ORACLE.parent), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # a failed git call recorded as empty-SHA/dirty=False would forge
        # clean provenance — fail loudly instead
        raise RuntimeError(f"git {' '.join(args)} failed "
                           f"(rc={r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip()


def _git_bytes(*args):
    """Raw-bytes variant — non-UTF-8 filenames in porcelain/diff output
    would raise UnicodeDecodeError under text=True."""
    r = subprocess.run(["git", "-C", str(_ORACLE.parent), *args],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={r.returncode}): "
            f"{r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def _untracked_paths(porcelain_z):
    """Untracked paths from `status --porcelain -z` (bytes): entries are
    NUL-separated 'XY path'; rename/copy entries carry ONE extra
    NUL-separated origin record that must be skipped."""
    toks = porcelain_z.split(b"\0")
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t:
            if t[:2] == b"??":
                out.append(os.fsdecode(t[3:]))
            elif t[:1] in (b"R", b"C"):
                i += 1                        # skip the origin record
        i += 1
    return out


def _code_state():
    """(sha, dirty, dirty_digest) — the digest hashes the dirty CONTENT
    (porcelain + tracked diff + untracked file bytes), because a Boolean
    alone misses drift within a dirty tree. Bypass guards (review P1-3):
    untracked-files=all + ignore-submodules=none defeat a
    status.showUntrackedFiles=no config, and assume-unchanged /
    skip-worktree index hints (which blank status/diff for modified files)
    are detected via ls-files -v and rejected."""
    sha = _git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError(f"malformed git SHA: {sha!r}")
    hinted = [ln for ln in _git_bytes("ls-files", "-v").split(b"\n")
              if ln[:1].islower() or ln[:1] == b"S"]
    if hinted:
        raise RuntimeError(
            "assume-unchanged/skip-worktree index hints present — they "
            "blank status/diff for modified files, forging clean "
            f"provenance: {[os.fsdecode(x) for x in hinted[:5]]!r}")
    porcelain = _git_bytes("status", "--porcelain", "-z",
                           "--untracked-files=all",
                           "--ignore-submodules=none")
    if not porcelain:
        return sha, False, None
    h = hashlib.sha256(porcelain)
    h.update(_git_bytes("diff", "HEAD"))
    # untracked content: porcelain only NAMES these paths and git diff
    # does not carry their bytes — hash the files themselves
    for path in _untracked_paths(porcelain):
        root = _ORACLE.parent / path
        files = (sorted(q for q in root.rglob("*") if q.is_file())
                 if root.is_dir() else [root])
        for q in files:
            h.update(str(q).encode(errors="surrogateescape"))
            h.update(_sha256(q).encode() if q.is_file() else b"|missing|")
    return sha, True, h.hexdigest()


def _tree_merkle(root):
    """sha256 over sorted (relpath, file sha256) of every file under root."""
    root = Path(root)
    h = hashlib.sha256()
    for q in sorted(root.rglob("*")):
        if q.is_file():
            h.update(str(q.relative_to(root)).encode(
                errors="surrogateescape"))
            h.update(_sha256_safe(q).encode())
    return h.hexdigest()


def _hashed(p):
    return dict(path=str(p), sha256=_sha256_safe(p))


def rttov_provenance(fixtures=None):
    """Resolve + hash every RTTOV science asset the analysis consumes
    (review P1-1): the fixture trees (Merkle), the executable named by each
    fixture's run.sh, the rtcoef and hydrotable resolved exactly like the
    run resolves them (coef_prefix + f_coef/f_hydrotable), and the
    runtime-selection env vars. Resolution happens ONCE here."""
    if fixtures is None:
        from kdm6.obs.rttov_case_writer import (cloud_fixture_case_dir,
                                                default_fixture_case_dir)
        fixtures = {"clear_fixture": default_fixture_case_dir(),
                    "cloud_fixture": cloud_fixture_case_dir()}
    rt = dict(env={k: os.environ.get(k) for k in _RTTOV_ENV})
    for name, root in fixtures.items():
        root = Path(root).resolve()
        m = re.search(r"(\S+\.exe)", (root / "out" / "run.sh").read_text())
        if m is None or not Path(m.group(1)).is_file():
            raise RuntimeError(f"{name}: run.sh names no existing RTTOV exe")
        nl = (root / "out" / "rttov_test.txt").read_text()
        mp = re.search(r"(?m)^\s*defn%coef_prefix\s*=\s*'([^']*)'", nl)
        names = dict(re.findall(r"(?m)^\s*defn%(f_\w+)\s*=\s*'([^']*)'",
                                (root / "in" / "coef.txt").read_text()))
        if mp is None or not names.get("f_coef", "").strip():
            raise RuntimeError(f"{name}: cannot resolve the rtcoef path")
        prefix = Path(mp.group(1))
        entry = dict(path=str(root), tree_sha256=_tree_merkle(root),
                     exe=_hashed(m.group(1)),
                     coef=_hashed(prefix / names["f_coef"]))
        ht = names.get("f_hydrotable", "").strip()
        entry["hydrotable"] = _hashed(prefix / ht) if ht else None
        rt[name] = entry
    return rt


def _rttov_recheck(rt):
    """End-of-run re-verification of every recorded RTTOV asset — content
    drift in the exe/coefs/hydrotable/fixture tree or a change in the
    runtime-selection env rejects the artifact."""
    drift = {}
    if "env" in rt:
        env_now = {k: os.environ.get(k) for k in _RTTOV_ENV}
        if env_now != rt["env"]:
            drift["rttov:env"] = (rt["env"], env_now)
    for name, e in rt.items():
        if not isinstance(e, dict) or "path" not in e:
            continue
        if _tree_merkle(e["path"]) != e["tree_sha256"]:
            drift[f"rttov:{name}:tree"] = e["path"]
        for part in ("exe", "coef", "hydrotable"):
            rec = e.get(part)
            if rec is not None and _sha256_safe(rec["path"]) != rec["sha256"]:
                drift[f"rttov:{name}:{part}"] = rec["path"]
    return drift


def snapshot_provenance(gk2a_files, *, allow_dirty=False):
    """START-of-run provenance: taken BEFORE the analysis reads anything,
    so the hashes describe the code/inputs the run actually consumes.
    Evidence runs require a clean tree: the dirty digest is a drift
    sentinel, not reproduction data (it cannot restore the patch or the
    untracked files, and it hashes absolute paths) — --allow-dirty is an
    explicit, recorded opt-out."""
    import shlex

    import numpy
    import torch
    sha, dirty, dirty_digest = _code_state()
    if dirty and not allow_dirty:
        raise RuntimeError(
            "evidence runs require a clean tree (code_dirty=False) — the "
            "dirty digest is a drift sentinel, not reproduction data; "
            "pass --allow-dirty to record a dirty run explicitly")
    argv = [sys.executable, *sys.argv]
    return dict(
        code_sha=sha, code_dirty=dirty, code_dirty_sha256=dirty_digest,
        allow_dirty=allow_dirty,
        # argv array is the authoritative LOSSLESS record; command is the
        # shlex-quoted display form (splits back to the exact argv).
        # process_argv keeps interpreter options when the interpreter
        # provides sys.orig_argv (3.10+); python_flags/xoptions record the
        # semantic interpreter state (-O assert-stripping etc.) everywhere.
        argv=argv,
        command=shlex.join(argv),
        process_argv=(list(sys.orig_argv)
                      if hasattr(sys, "orig_argv") else None),
        python_optimize=int(sys.flags.optimize),
        python_flags={f: int(getattr(sys.flags, f)) for f in _PY_FLAGS
                      if hasattr(sys.flags, f)},
        python_xoptions={k: (v if isinstance(v, (str, bool)) else str(v))
                         for k, v in sys._xoptions.items()},
        cwd=str(Path.cwd()),
        python=platform.python_version(),
        torch=torch.__version__, numpy=numpy.__version__,
        rttov=rttov_provenance(),
        inputs={str(p): _sha256(p) for p in
                [WRFIN, CAL, *map(str, gk2a_files)]})


def check_provenance_drift(manifest):
    """END-of-run re-check: code SHA/dirty content, every input hash, and
    every RTTOV asset must match the start snapshot. Returns {} when clean;
    the runner REJECTS (and quarantines) the artifact otherwise."""
    drift = {}
    sha, dirty, dirty_digest = _code_state()
    if sha != manifest["code_sha"]:
        drift["code_sha"] = (manifest["code_sha"], sha)
    if dirty != manifest["code_dirty"]:
        drift["code_dirty"] = (manifest["code_dirty"], dirty)
    if dirty_digest != manifest["code_dirty_sha256"]:
        drift["code_dirty_sha256"] = (manifest["code_dirty_sha256"],
                                      dirty_digest)
    changed = [p for p, h in manifest["inputs"].items()
               if _sha256_safe(p) != h]
    if changed:
        drift["inputs_changed"] = changed
    drift.update(_rttov_recheck(manifest.get("rttov") or {}))
    return drift


def _assert_disjoint(out_paths, in_paths):
    """Output/case paths must not equal, contain, or live inside any input
    path — the run must be unable to overwrite its own provenance inputs."""
    for o in out_paths:
        ro = Path(o).resolve()
        for i in in_paths:
            ri = Path(i).resolve()
            if ro == ri or ro in ri.parents or ri in ro.parents:
                raise ValueError(
                    f"output path {o} is not disjoint from input {i} — "
                    "the run could overwrite its own provenance inputs")


def finalize_artifact(rep, manifest, drift, out_json, staging_npz):
    """Gate + place the artifact: provenance stability joins the gate set,
    accepted is recomputed over ALL gates, and a rejected run leaves
    NOTHING under the canonical approved names — every file lands under
    *.rejected (review P1-2: the exit code alone does not protect a
    file-collecting archive step). Returns the final accepted verdict."""
    manifest["provenance_drift"] = drift or None
    rep["manifest"] = manifest
    rep["gates"]["provenance_stable"] = not bool(drift)
    rep["gates"]["accepted"] = all(
        v for k, v in rep["gates"].items() if k != "accepted")
    accepted = rep["gates"]["accepted"]
    sfx = "" if accepted else ".rejected"
    json_path = out_json + sfx
    npz_path = out_json + ".fields.npz" + sfx
    man_path = out_json + ".manifest.json" + sfx
    Path(staging_npz).rename(npz_path)
    with open(json_path, "w") as f:
        json.dump(rep, f, indent=1)
    manifest["outputs"] = {json_path: _sha256(json_path),
                           npz_path: _sha256(npz_path)}
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=1)
    return accepted


def main(out_json, case_root, conserving=False, allow_dirty=False):
    from kdm6.da_fulldomain import (evaluate_artifact_gates,
                                    run_fulldomain_analysis)
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from test_rttov_case_writer import (_CHANNELS, _fixture_p_half,
                                        _fixture_tq)

    t0 = time.time()
    # snapshot provenance BEFORE any input is read (slot_files only lists
    # the directory; the frame/cal/L1B reads all happen after the hashes)
    gk2a_files = slot_files(GK2A, SLOT, channels=CLEAN_IR_CHANNELS)
    manifest = snapshot_provenance(gk2a_files, allow_dirty=allow_dirty)
    _assert_disjoint(
        [out_json, case_root],
        [WRFIN, CAL, GK2A] + [e["path"] for e in manifest["rttov"].values()
                              if isinstance(e, dict) and "path" in e])
    fr = read_wrfout_frame(WRFIN, 0)
    cal = load_cal_table(CAL)
    pl = read_ko_slot(gk2a_files, cal, stride=8)
    co = payload_to_column_obs(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0)
    print(f"[run] load+collocate {time.time() - t0:.0f}s "
          f"n_assigned={co.n_assigned} obs_vt={co.valid_time_utc} "
          f"frame_vt={fr.meta.get('valid_time_utc')}", flush=True)

    tr, qr = _fixture_tq()
    grids = dict(p_lay=fixture_layer_pressure(), p_half=_fixture_p_half(),
                 t_ref=tr, q_ref=qr)
    staging_npz = out_json + ".fields.npz.staging"
    rep = run_fulldomain_analysis(
        fr, co, grids, case_root, n_workers=8, max_iter=MAX_ITER,
        channels=_CHANNELS, pseudo_rh=True, time_tolerance_s=300.0,
        qv_levels=int(fr.meta["kme"]), conserving=conserving,
        save_fields=staging_npz)

    rep["artifact_role"] = ("conserving_stress" if conserving
                            else "pathology_stress")
    # the runner-known mode is the external gate contract (fail-closed even
    # if every self-declaration marker regressed away)
    rep["gates"] = evaluate_artifact_gates(rep,
                                           expected_conserving=conserving)
    drift = check_provenance_drift(manifest)
    accepted = finalize_artifact(rep, manifest, drift, out_json, staging_npz)

    tag = "v10" if conserving else "v9.2"
    if not accepted:
        failed = [k for k, v in rep["gates"].items() if not v]
        print(f"[{tag}] ARTIFACT REJECTED (quarantined under *.rejected) — "
              f"failed gates: {failed}"
              + (f"; provenance drift: {drift}" if drift else ""),
              flush=True)
        sys.exit(1)
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


if __name__ == "__main__":
    import argparse
    # allow_abbrev=False: --conserv must not silently expand
    ap = argparse.ArgumentParser(
        description="LC05 full-domain evidence runner", allow_abbrev=False)
    ap.add_argument("out_json")
    ap.add_argument("case_root")
    # strict parsing: a --conservng typo must fail loudly, never run
    # silently as non-conserving
    ap.add_argument("--conserving", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="record a dirty-tree run explicitly (the dirty "
                         "digest is a drift sentinel, not reproduction "
                         "data)")
    args = ap.parse_args()
    main(args.out_json, args.case_root, conserving=args.conserving,
         allow_dirty=args.allow_dirty)
