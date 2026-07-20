#!/usr/bin/env python3
"""G3.3 self-check (§5a): shadow == actual == offline, on real containers.

Runs the instrumented substep chain (one FRESH PROCESS per algorithm) under a
sealed environment, then verifies from the EVIDENCE alone:

  1. container-set completeness — the files on disk are exactly the sealed
     run-index set, and every container reads fail-closed;
  2. shadow == actual — the diagnostic shadow ladder's final f32 equals the
     ACTUAL falk bits, per record (§5a shadow-fidelity);
  3. offline == shadow — an independent NumPy recomputation FROM THE DUMPED
     OPERANDS reproduces every FALK rung bit-for-bit (same IEEE ops, same
     promotion: f32*f32→f32, f32*f64→f64, one final f32 rounding);
  4. producer cross-checks — check_producer_flags per substep (gate law
     n<=mstep, mstep range, floor semantics against qcrmin).

The offline recomputation uses ONLY dumped payloads (q_before, dend_raw,
work1/workn, mstep_native, gate_native) — never the driver's fixture — so a
driver/fixture bug cannot vacuously agree with itself.

    python3 harness/g33_selfcheck.py [--driver /path/to/selfcheck_driver]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_derived as gdv
import g33_dump as gd
import g33_expectation as ge
import g33_run_env as gre

B, K, MSTEPMAX, QCRMIN, DTCLD = 3, 4, 2, 1.0e-9, 20.0   # DTCLD matches selfcheck_driver.cpp

# §7 interface roundoff-residual ceiling in ULP units (see resid/κ below). A
# gross-error tripwire, calibrated above the observed maximum with margin — NOT
# a bit-exact claim. The ρΔz transfer is algebraically conservative but closes
# only to within this measured float32 envelope.
KAPPA_ENVELOPE = 4.0

# Failure CLASSES by exit code — the discrimination a wrapped child cannot
# forge. Driver stdout/stderr is interpolated into failure messages, so child-
# controlled text can become the terminal line; the parent's exit code cannot.
# The kill gate accepts ONLY EXIT_FIDELITY.
EXIT_SKIP, EXIT_DRIVER, EXIT_EVIDENCE, EXIT_FIDELITY = 2, 3, 4, 5


def _die(code: int, msg: str):
    sys.stdout.flush()          # keep merged 2>&1 order deterministic
    print(msg, file=sys.stderr, flush=True)
    raise SystemExit(code)


def _sched(algorithm: str) -> dict:
    return {"case_id": "selfcheck", "pair_id": "selfpair", "backend": "cpp",
            "algorithm": algorithm, "B": B, "K": K, "loops": 1,
            "mstepmax_main": [MSTEPMAX], "mstepmax_ice": [1],
            "species_scope": ["qr", "nr"], "qcrmin": QCRMIN, "dtcld": DTCLD,
            "instrumented_stages": ["substep_pre", "op", "substep_post"]}


def _payload(recs, **key):
    hits = [r for r in recs if all(r.get(k) == v for k, v in key.items())]
    if len(hits) != 1:
        _die(EXIT_EVIDENCE, f"FAIL: {len(hits)} records match {key} (want exactly 1)")
    return hits[0]


def _np(dtype, payload):
    kind = {"f32": ">f4", "f64": ">f8", "i32": ">i4", "u8": ">u1"}[dtype]
    return np.frombuffer(payload, dtype=kind).astype(
        {"f32": np.float32, "f64": np.float64,
         "i32": np.int32, "u8": np.uint8}[dtype])


def _fallacc(records, field):
    """{(species, k): payload} for one FALLACC field across a container — used to
    check the fall accumulator carries continuously from one substep to the next.
    Pure in its arguments, so it lives at module scope (not rebuilt per loop)."""
    out = {}
    for r in records:
        if r["stage"] == "op" and r["op_id"].endswith("_FALLACC") \
                and r["field"] == field:
            out[(r["species"], r["k"])] = r["payload"]
    return out


def _post_map(recs, cid):
    """{field: (dtype, payload)} for the substep_post stage, fail-closed on the
    fields the caller relies on. A truncated/malformed container missing qr or
    nr would otherwise KeyError into a raw traceback; the harness is fail-closed,
    so a missing field must be a clean EXIT_EVIDENCE, not a crash."""
    m = {r["field"]: (r["dtype"], r["payload"])
         for r in recs if r["stage"] == "substep_post"}
    for f in ("qr", "nr"):
        if f not in m:
            _die(EXIT_EVIDENCE, f"FAIL: {cid} substep_post is missing field {f}")
    return m


def _bits(a, dt):
    # container payloads are BIG-endian per element; a native tobytes() would
    # compare LE bytes against BE payloads and fail on identical values
    return a.astype({"f32": ">f4", "f64": ">f8"}[dt]).tobytes()


def interface_kappa_chi(mul_src, inflow, m_src, m_dst):
    """§7 interface residual (κ) and metric condition (χ), per element, f64.

    L = extensive mass LEAVING k-1 (mul_src = dq_out(k-1)*m_src); G = mass
    ARRIVING at k (inflow*m_dst, the f32 product widened). r = f64(G)-f64(L) is
    exact (both f32). κ = |r| / (eps32*(|G|+|L|+tiny)) is the residual in ULP
    units; χ = max(m_src/m_dst, m_dst/m_src) the metric ratio. All inputs are
    f32 ndarrays. Pure, so the formula is unit-testable away from the driver."""
    Lf = mul_src.astype(np.float64)
    Gf = (inflow * m_dst).astype(np.float64)     # f32 op, then widen
    eps32 = np.float64(np.finfo(np.float32).eps)
    tiny = np.float64(np.finfo(np.float32).tiny)
    kappa = np.abs(Gf - Lf) / (eps32 * (np.abs(Gf) + np.abs(Lf) + tiny))
    ms, md = m_src.astype(np.float64), m_dst.astype(np.float64)
    chi = np.maximum(ms / md, md / ms)
    return kappa, chi


def check_algorithm(driver: Path, algorithm: str, workdir: Path) -> dict:
    sched = _sched(algorithm)
    run_uuid = f"selfcheck-{algorithm}-{uuid.uuid4().hex[:12]}"
    env = gre.build_env(sched, workdir, binary=driver,
                        column_map=[[i, 0, i, i] for i in range(B)],
                        run_uuid=run_uuid, column_layout_id="selfcheck-3col")
    r = subprocess.run([str(driver), algorithm], env={**os.environ, **env},
                       capture_output=True, text=True)
    if r.returncode != 0:
        _die(EXIT_DRIVER, f"FAIL: driver rc={r.returncode}\n{r.stdout}{r.stderr}")

    # INDEPENDENT SEAL: the contract is authority only if its bytes match the
    # digest the RUN used (from env, the in-memory authority build_env returned)
    # AND the digest every container sealed into its header. Reading the file
    # and trusting it — as before — let a post-run edit of run_contract.json
    # pass, the self-attestation this whole harness keeps removing.
    contract_bytes = (workdir / "run_contract.json").read_bytes()
    file_sha = hashlib.sha256(contract_bytes).hexdigest()
    env_sha = env["KDM6_G33_RUN_CONTRACT_SHA256"]
    if file_sha != env_sha:
        _die(EXIT_EVIDENCE,
             f"FAIL: run_contract.json edited after the run "
             f"(file {file_sha[:12]} != sealed {env_sha[:12]})")
    contract = json.loads(contract_bytes.decode("utf-8"))
    seal_qcrmin, seal_dtcld = contract["qcrmin"], contract["dtcld"]

    # 1. container-set completeness: exactly the sealed set, nothing else
    index = ge.run_index(sched)
    dump_dir = Path(env["KDM6_G33_DUMP_DIR"])
    on_disk = sorted(p.name for p in dump_dir.glob("*.g33"))
    expected = sorted(c["path"] for c in index["containers"])
    if on_disk != expected:
        _die(EXIT_EVIDENCE,
             f"FAIL container set:\n  disk    {on_disk}\n  sealed  {expected}")

    stats = {"containers": 0, "shadow_actual": 0, "offline_rungs": 0,
             "inflow_rungs": 0, "ladder_rungs": 0, "flags": 0}
    # BRANCH COVERAGE, recomputed from dumped operands (never driver constants):
    # a fixture edited so a branch stops firing must FAIL, not silently pass a
    # ladder that no longer exercises it.
    cov = {"mstep": None, "gate_by_n": {}, "qr_cap": set(), "nr_cap": set(),
           "floor_active": 0}
    stats_links = {"n": 0}
    # §7 interface roundoff residual: the ρΔz transfer is algebraically
    # conservative but NOT bit-exact in f32 (dq_in = fl32(dq_out*m_src/m_dst)),
    # so mass LEAVING k-1 (= mul_src) and mass ARRIVING at k (= inflow*m_dst)
    # differ by a rounding residual r. κ = |r| / (eps32*(|G|+|L|+tiny)) reports
    # it in ULP units; χ = max(m_src/m_dst, m_dst/m_src) flags where the metric
    # ratio (and thus roundoff amplification) is large. Measured, not asserted
    # bit-exact — the honest closure claim.
    resid = {"kappa_max": 0.0, "chi_max": 0.0, "n": 0}
    # cross-substep carry, keyed by (outer_loop, chain): substep_post(n) must
    # equal substep_pre(n+1), and the fall accumulator must be continuous
    # (fall_after(n,k) == fall_before(n+1,k)), WITHIN a chain. Empty until the
    # first substep of each chain has been seen.
    carry = {}
    for c in index["containers"]:
        cont = gd.read_container(dump_dir / c["path"])       # fail-closed
        recs = cont["records"]
        n_sub = c["n"]
        stats["containers"] += 1
        # the container sealed the contract digest INSIDE its (sha256'd) payload
        # frame, so a header edit breaks the footer; requiring header == env_sha
        # ties the three channels together.
        if cont["header"]["run_contract_sha256"] != env_sha:
            _die(EXIT_EVIDENCE,
                 f"FAIL: {c['container_id']} sealed a different run_contract_sha256 "
                 f"than the run used")

        pre = {r["field"]: (r["dtype"], r["payload"])
               for r in recs if r["stage"] == "substep_pre"}
        gdv.check_producer_flags(pre, n_sub, seal_qcrmin, seal_dtcld)
        stats["flags"] += 1

        # valid-metric gate (#6): the ρΔz metric is only meaningful when every
        # density and layer thickness is finite and strictly positive. A zero or
        # negative dend_safe/delz_safe would make the conservative division
        # ill-posed and silently NaN/Inf the transfer — reject the fixture here.
        for fld in ("dend_safe", "delz_raw", "delz_safe"):
            vals = _np(*pre[fld])
            if not (np.isfinite(vals).all() and (vals > 0.0).all()):
                _die(EXIT_EVIDENCE,
                     f"FAIL valid-metric: {c['container_id']} substep_pre.{fld} "
                     f"has a non-finite or non-positive entry — ρΔz ill-posed")

        # cross-substep continuity (#4): this substep's pre-state and incoming
        # fall accumulator must equal the PREVIOUS substep OF THE SAME CHAIN's
        # post-state and outgoing accumulator, bit-for-bit — the chain that
        # carries mass from one CFL sub-step to the next. carry is keyed by
        # (outer_loop, chain) so a future ice chain or a second outer loop in
        # the same run cannot be mis-compared against main-chain state; and the
        # law is enforced BOTH ways: n==1 must have no prior in its key, n>1
        # must have exactly the n-1 prior.
        chain_key = (c["outer_loop"], c["chain"])
        prior = carry.get(chain_key)
        cur_fall_before = _fallacc(recs, "fall_before")
        if n_sub == 1:
            if prior is not None:
                _die(EXIT_EVIDENCE,
                     f"FAIL causal-link: {c['container_id']} is n=1 but chain "
                     f"{chain_key} already carried state from n={prior['n']} "
                     f"(substep numbering broken)")
        else:
            if prior is None or prior["n"] != n_sub - 1:
                _die(EXIT_EVIDENCE,
                     f"FAIL causal-link: {c['container_id']} n={n_sub} has no "
                     f"immediate predecessor n={n_sub - 1} in chain {chain_key}")
            for sp in ("qr", "nr"):
                if pre[sp][1] != prior["post"][sp][1]:
                    _die(EXIT_FIDELITY,
                         f"FAIL causal-link: {c['container_id']} substep_pre.{sp} "
                         f"!= prior substep_post.{sp} (state carry broken)")
                stats_links["n"] += 1
            # 2.4: the accumulator key SETS must match exactly — an extra key on
            # either side means a species/cell appeared or vanished across the
            # boundary, which key-by-key lookup alone would not catch.
            if set(cur_fall_before) != set(prior["fall_after"]):
                _die(EXIT_FIDELITY,
                     f"FAIL causal-link: {c['container_id']} FALLACC key set "
                     f"{sorted(cur_fall_before)} != prior {sorted(prior['fall_after'])}")
            for key, before in cur_fall_before.items():
                if prior["fall_after"][key] != before:
                    sp, kk = key
                    _die(EXIT_FIDELITY,
                         f"FAIL causal-link: {c['container_id']} {sp} k={kk} "
                         f"FALLACC.fall_before != prior FALLACC.fall_after "
                         f"(accumulator discontinuous)")
                stats_links["n"] += 1

        # coverage: decoded mstep (constant across containers) + gate for this n
        mdec = gdv.derive_mstep(*pre["mstep_native"])["decoded_i32"]
        if cov["mstep"] is None:
            cov["mstep"] = mdec
        elif cov["mstep"] != mdec:
            _die(EXIT_EVIDENCE, f"FAIL: mstep changed across containers "
                                f"{cov['mstep']} != {mdec}")
        cov["gate_by_n"][n_sub] = gdv.derive_gate(*pre["gate_native"])["decoded_u8"]
        # floors must be inactive (real-atmosphere / valid_metric policy)
        for fld in ("dend_floor_active", "delz_floor_active"):
            cov["floor_active"] += int(sum(_np(*pre[fld])))
        # cap coverage recomputed with the comparator's own 4-state min() enum,
        # NOT a boolean. dq_out = min(outflow_pre_cap, source_reservoir); the
        # cap BINDS iff the reservoir is strictly smaller (RIGHT_SELECTED) and
        # is UNBOUND iff the natural outflow is strictly smaller (LEFT_SELECTED).
        # `bool(pre_cap > resv)` folded a VALUE_TIE (pre_cap == resv, cap sitting
        # exactly at the reservoir) into "unbound" and a NaN (UNORDERED) into
        # "unbound" too — so a fixture that never truly frees the cap could still
        # read {True, False}. Recording the raw enum keeps ties and NaN distinct.
        for sp, key in (("qr", "qr_cap"), ("nr", "nr_cap")):
            op = f"{sp.upper()}_OUTFLOW"
            for k in range(K):
                hits = [r for r in recs if r["stage"] == "op" and r["k"] == k
                        and r["species"] == sp and r["op_id"] == op]
                if not hits:
                    continue
                pre_cap_p = _payload(recs, stage="op", k=k, species=sp,
                                     op_id=op, field="outflow_pre_cap")["payload"]
                resv_p = _payload(recs, stage="op", k=k, species=sp,
                                  op_id=op, field="source_reservoir")["payload"]
                for br in gdv.classify_min("f32", pre_cap_p, resv_p):
                    cov[key].add(br)

        dend = _np(*pre["dend_raw"]).reshape(B, K)
        w1 = _np(*pre["work1_qr"]).reshape(B, K)
        wn = _np(*pre["workn_qr"]).reshape(B, K)
        mstep = _np(*pre["mstep_native"])
        gate = _np(*pre["gate_native"])

        for k in range(K):
            for sp, op, before_op, before_f in (
                    ("qr", "QR_FALK", "QR_UPDATE", "q_before"),
                    ("nr", "NR_FALK", "NR_UPDATE", "n_before")):
                rec = lambda opid, f: _payload(recs, stage="op", k=k,
                                               species=sp, op_id=opid, field=f)
                entry = _np("f32", rec(before_op, before_f)["payload"])

                # offline FALK ladder from DUMPED operands, IEEE step by step
                if sp == "qr":
                    # overlay computes dend_col(k) * entry — operand order kept
                    s1 = dend[:, k] * entry                       # f32*f32 -> f32
                    s2 = s1 * w1[:, k]                            # f32*f64 -> f64
                    off = [("mul_dend_q", "f32", _bits(s1, "f32"))]
                else:
                    s2 = entry * wn[:, k]                         # f32*f64 -> f64
                    off = []
                s3 = s2 / mstep                                   # f64/f64 -> f64
                s4 = s3 * gate                                    # f64*f32 -> f64
                shadow = s4.astype(np.float32)                    # ONE rounding
                off += [("mul_work1" if sp == "qr" else "mul_workn", "f64", _bits(s2, "f64")),
                        ("div_mstep", "f64", _bits(s3, "f64")),
                        ("falk_precast", "f64", _bits(s4, "f64")),
                        ("shadow_falk_f32", "f32", _bits(shadow, "f32"))]
                for field, dt, want in off:
                    have = rec(op, field)
                    if have["dtype"] != dt or have["payload"] != want:
                        _die(EXIT_FIDELITY,
                             f"FAIL offline!=dumped: {algorithm} {c['container_id']} "
                             f"k={k} {sp} {op}.{field}")
                    stats["offline_rungs"] += 1

                # shadow == actual (§5a)
                sh = rec(op, "shadow_falk_f32")["payload"]
                ac = rec(op, "falk_f32")["payload"]
                if sh != ac:
                    _die(EXIT_FIDELITY,
                         f"FAIL shadow!=actual: {algorithm} {c['container_id']} "
                         f"k={k} {sp}")
                stats["shadow_actual"] += 1

        # conservative QR_INFLOW — the LOAD-BEARING G3.3-M operation (the
        # rho*dz metric conversion that is conservative-only). Recompute
        # src_metric/dst_metric/mul_src/inflow_final from the dumped f32
        # operands, bit-exact, for every interior/bottom cell. FALK proves the
        # shared arithmetic; this proves the conserved transfer the whole gate
        # exists to attribute.
        if algorithm == "conservative":
            def ri(f, cell_k):
                return _payload(recs, stage="op", k=cell_k, species="qr",
                                op_id="QR_INFLOW", field=f)["payload"]
            snap = {f: _np(*pre[f]).reshape(B, K)
                    for f in ("qr", "nr", "dend_safe", "delz_raw", "delz_safe")}

            def op_bits(k_, sp_, opid, field):
                return _payload(recs, stage="op", k=k_, species=sp_,
                                op_id=opid, field=field)["payload"]

            def link(cond, k_, msg):
                if not cond:
                    _die(EXIT_FIDELITY,
                         f"FAIL causal-link: {algorithm} {c['container_id']} "
                         f"k={k_} {msg}")
                stats_links["n"] += 1

            post_rec = _post_map(recs, c["container_id"])
            post_snap = {f: _np(*post_rec[f]).reshape(B, K) for f in ("qr", "nr")}

            # 2.2 — TOP cell (k=0): no inflow, so the whole update is a single
            # subtraction. The interior loop starts at k=1 and would leave the
            # surface-most, simplest rung unverified precisely because it is
            # simple. Pin it: before == snapshot, post == before - dq_out.
            link(op_bits(0, "qr", "QR_UPDATE", "q_before") == _bits(snap["qr"][:, 0], "f32"),
                 0, "top QR_UPDATE.q_before != substep_pre.qr[:, 0]")
            q0b = _np("f32", op_bits(0, "qr", "QR_UPDATE", "q_before"))
            dq0 = _np("f32", op_bits(0, "qr", "QR_OUTFLOW", "dq_out"))
            link(op_bits(0, "qr", "QR_UPDATE", "q_post") == _bits(q0b - dq0, "f32"),
                 0, "top QR_UPDATE.q_post != q_before - dq_out (no inflow at top)")
            link(op_bits(0, "nr", "NR_UPDATE", "n_before") == _bits(snap["nr"][:, 0], "f32"),
                 0, "top NR_UPDATE.n_before != substep_pre.nr[:, 0]")
            n0b = _np("f32", op_bits(0, "nr", "NR_UPDATE", "n_before"))
            dn0 = _np("f32", op_bits(0, "nr", "NR_OUTFLOW", "dn_out"))
            link(op_bits(0, "nr", "NR_UPDATE", "n_post") == _bits(n0b - dn0, "f32"),
                 0, "top NR_UPDATE.n_post != n_before - dn_out (no inflow at top)")

            # §5 — full OUTFLOW + FALLACC offline replay (beyond FALK + INFLOW),
            # every k, from DUMPED operands, bit-exact. This closes the ladder
            # between falk and the capped outflow / fall accumulator that the
            # causal links assume but never recomputed:
            #   qr: pre_cap = falk*dt/dend_safe ; dq_out = min(pre_cap, reservoir)
            #       fall_after = fall_before + dq_out*dend_safe/dt   (ρΔz-metered)
            #   nr: pre_cap = falk*dt ; dn_out = min(pre_cap, reservoir)
            #       fall_after = fall_before + dn_out/dt             (dz-only)
            # dtcld is a double SCALAR, so it does NOT promote the f32 tensor
            # (and 20.0 is exact in f32); the offline op is f32 throughout.
            dt32 = np.float32(seal_dtcld)

            def ladder_eq(sp, op, field, k_, val):
                if op_bits(k_, sp, op, field) != _bits(val, "f32"):
                    _die(EXIT_FIDELITY,
                         f"FAIL offline!=dumped: {algorithm} {c['container_id']} "
                         f"k={k_} {sp} {op}.{field}")
                stats["ladder_rungs"] += 1

            for k in range(K):
                dsafe = snap["dend_safe"][:, k]
                # QR capped-outflow ladder
                qfalk = _np("f32", op_bits(k, "qr", "QR_FALK", "falk_f32"))
                q_mul_dt = qfalk * dt32
                q_precap = q_mul_dt / dsafe
                q_res = _np("f32", op_bits(k, "qr", "QR_OUTFLOW", "source_reservoir"))
                q_dqo = np.minimum(q_precap, q_res)
                ladder_eq("qr", "QR_OUTFLOW", "mul_dt", k, q_mul_dt)
                ladder_eq("qr", "QR_OUTFLOW", "outflow_pre_cap", k, q_precap)
                ladder_eq("qr", "QR_OUTFLOW", "dq_out", k, q_dqo)
                # QR fall accumulator: actual capped-outflow RATE, ρΔz-metered
                q_f1 = q_dqo * dsafe
                q_f2 = q_f1 / dt32
                q_fb = _np("f32", op_bits(k, "qr", "QR_FALLACC", "fall_before"))
                ladder_eq("qr", "QR_FALLACC", "mul_dend_safe", k, q_f1)
                ladder_eq("qr", "QR_FALLACC", "fall_increment", k, q_f2)
                ladder_eq("qr", "QR_FALLACC", "fall_after", k, q_fb + q_f2)
                # NR capped-outflow ladder (no dend anywhere — dz-only measure)
                nfalk = _np("f32", op_bits(k, "nr", "NR_FALK", "falk_f32"))
                n_precap = nfalk * dt32
                n_res = _np("f32", op_bits(k, "nr", "NR_OUTFLOW", "source_reservoir"))
                n_dno = np.minimum(n_precap, n_res)
                ladder_eq("nr", "NR_OUTFLOW", "outflow_pre_cap", k, n_precap)
                ladder_eq("nr", "NR_OUTFLOW", "dn_out", k, n_dno)
                n_f2 = n_dno / dt32
                n_fb = _np("f32", op_bits(k, "nr", "NR_FALLACC", "fall_before"))
                ladder_eq("nr", "NR_FALLACC", "fall_increment", k, n_f2)
                ladder_eq("nr", "NR_FALLACC", "fall_after", k, n_fb + n_f2)

            for k in range(1, K):
                prev = _np("f32", ri("prev_out", k))
                ds_src = _np("f32", ri("dend_safe_src", k))
                dz_src = _np("f32", ri("delz_raw_src", k))
                ds_dst = _np("f32", ri("dend_safe_dst", k))
                dz_dst = _np("f32", ri("delz_safe_dst", k))
                m_src = ds_src * dz_src        # f32*f32 -> f32
                m_dst = ds_dst * dz_dst
                mul = prev * m_src
                inflow = mul / m_dst          # f32/f32 -> f32
                for field, val in (("src_metric", m_src), ("dst_metric", m_dst),
                                   ("mul_src", mul), ("inflow_final", inflow)):
                    if ri(field, k) != _bits(val, "f32"):
                        _die(EXIT_FIDELITY,
                             f"FAIL offline!=dumped: {algorithm} {c['container_id']} "
                             f"k={k} qr QR_INFLOW.{field}")
                    stats["inflow_rungs"] += 1

                # §7 interface roundoff residual (MEASURED, not bit-exact): mass
                # leaving k-1 (mul_src) vs mass arriving at k (inflow*m_dst)
                # differ by a rounding residual; κ reports it in ULP units.
                kappa, chi = interface_kappa_chi(mul, inflow, m_src, m_dst)
                resid["kappa_max"] = max(resid["kappa_max"], float(kappa.max()))
                resid["chi_max"] = max(resid["chi_max"], float(chi.max()))
                resid["n"] += int(kappa.size)

                # ── CROSS-RECORD CAUSAL LINKS (raw-bit) ──────────────────────
                # A single record's arithmetic can be internally consistent yet
                # wire the WRONG neighbour cell or the wrong snapshot column.
                # These bind the inflow to its actual upstream source and the
                # substep_pre metric it must have used.
                # interface link: prev_out(k) is the cell-above's actual dq_out
                link(ri("prev_out", k) == op_bits(k - 1, "qr", "QR_OUTFLOW", "dq_out"),
                     k, "prev_out != QR_OUTFLOW.dq_out(k-1)")
                # metric links: op operands are the whole-K snapshot columns
                link(ri("dend_safe_src", k) == _bits(snap["dend_safe"][:, k - 1], "f32"),
                     k, "dend_safe_src != substep_pre.dend_safe[:, k-1]")
                link(ri("delz_raw_src", k) == _bits(snap["delz_raw"][:, k - 1], "f32"),
                     k, "delz_raw_src != substep_pre.delz_raw[:, k-1]")
                link(ri("dend_safe_dst", k) == _bits(snap["dend_safe"][:, k], "f32"),
                     k, "dend_safe_dst != substep_pre.dend_safe[:, k]")
                link(ri("delz_safe_dst", k) == _bits(snap["delz_safe"][:, k], "f32"),
                     k, "delz_safe_dst != substep_pre.delz_safe[:, k]")
                # state links (QR): the conservative update has NO clamp, so the
                # chain must close entirely from recorded bits —
                #   q_before == substep_pre.qr[:, k]
                #   q_minus_out == q_before - QR_OUTFLOW.dq_out
                #   q_plus_in_preclamp == q_minus_out + inflow_final
                #   q_post == q_plus_in_preclamp   (record equality, no clamp)
                link(op_bits(k, "qr", "QR_UPDATE", "q_before") == _bits(snap["qr"][:, k], "f32"),
                     k, "QR_UPDATE.q_before != substep_pre.qr[:, k]")
                q_before = _np("f32", op_bits(k, "qr", "QR_UPDATE", "q_before"))
                dq_out = _np("f32", op_bits(k, "qr", "QR_OUTFLOW", "dq_out"))
                q_minus = q_before - dq_out
                link(op_bits(k, "qr", "QR_UPDATE", "q_minus_out") == _bits(q_minus, "f32"),
                     k, "QR_UPDATE.q_minus_out != q_before - dq_out")
                q_minus_q = _np("f32", op_bits(k, "qr", "QR_UPDATE", "q_minus_out"))
                inflow_q = _np("f32", op_bits(k, "qr", "QR_INFLOW", "inflow_final"))
                link(op_bits(k, "qr", "QR_UPDATE", "q_plus_in_preclamp")
                     == _bits(q_minus_q + inflow_q, "f32"),
                     k, "QR_UPDATE.q_plus_in_preclamp != q_minus_out + inflow_final")
                link(op_bits(k, "qr", "QR_UPDATE", "q_post")
                     == op_bits(k, "qr", "QR_UPDATE", "q_plus_in_preclamp"),
                     k, "QR_UPDATE.q_post != q_plus_in_preclamp (a clamp appeared)")

                # ── NR chain: interface + dz-only metric + state ────────────────
                # nr transfer is dz-ONLY (the frozen number-moment defect,
                # [[conservative-nr-number-moment-blocker]]): inflow_final =
                # (prev_out_nr * delz_raw_src) / delz_safe_dst — NO density ratio.
                # These links bind that transfer to its upstream cell and columns
                # without endorsing the physics.
                def nri(f):
                    return op_bits(k, "nr", "NR_INFLOW", f)
                link(nri("prev_out_nr") == op_bits(k - 1, "nr", "NR_OUTFLOW", "dn_out"),
                     k, "NR_INFLOW.prev_out_nr != NR_OUTFLOW.dn_out(k-1)")
                link(nri("delz_raw_src") == _bits(snap["delz_raw"][:, k - 1], "f32"),
                     k, "NR_INFLOW.delz_raw_src != substep_pre.delz_raw[:, k-1]")
                link(nri("delz_safe_dst") == _bits(snap["delz_safe"][:, k], "f32"),
                     k, "NR_INFLOW.delz_safe_dst != substep_pre.delz_safe[:, k]")
                nprev = _np("f32", nri("prev_out_nr"))
                ndz_src = _np("f32", nri("delz_raw_src"))
                ndz_dst = _np("f32", nri("delz_safe_dst"))
                n_mul = nprev * ndz_src               # mul_delz_src (dz-only)
                n_inflow = n_mul / ndz_dst            # inflow_final
                link(nri("mul_delz_src") == _bits(n_mul, "f32"),
                     k, "NR_INFLOW.mul_delz_src != prev_out_nr * delz_raw_src")
                link(nri("inflow_final") == _bits(n_inflow, "f32"),
                     k, "NR_INFLOW.inflow_final != mul_delz_src / delz_safe_dst")
                link(op_bits(k, "nr", "NR_UPDATE", "n_before") == _bits(snap["nr"][:, k], "f32"),
                     k, "NR_UPDATE.n_before != substep_pre.nr[:, k]")
                n_before = _np("f32", op_bits(k, "nr", "NR_UPDATE", "n_before"))
                dn_out = _np("f32", op_bits(k, "nr", "NR_OUTFLOW", "dn_out"))
                n_minus = n_before - dn_out
                link(op_bits(k, "nr", "NR_UPDATE", "n_minus_out") == _bits(n_minus, "f32"),
                     k, "NR_UPDATE.n_minus_out != n_before - dn_out")
                link(op_bits(k, "nr", "NR_UPDATE", "n_plus_in_preclamp")
                     == _bits(n_minus + n_inflow, "f32"),
                     k, "NR_UPDATE.n_plus_in_preclamp != n_minus_out + inflow_final")
                link(op_bits(k, "nr", "NR_UPDATE", "n_post")
                     == op_bits(k, "nr", "NR_UPDATE", "n_plus_in_preclamp"),
                     k, "NR_UPDATE.n_post != n_plus_in_preclamp (a clamp appeared)")

            # 2.1 — close the graph to the RETURNED whole-field state. Every
            # per-cell op q_post/n_post proven above is a DIAGNOSTIC record; the
            # value the function actually returns (and dumps as substep_post,
            # which the next substep's pre is checked against) is a separate
            # stack. Without this link a producer could emit a correct per-cell
            # q_post while returning a wrong column, and cross-substep continuity
            # — comparing the wrong post to the wrong next pre — would still pass.
            for k in range(K):
                link(op_bits(k, "qr", "QR_UPDATE", "q_post") == _bits(post_snap["qr"][:, k], "f32"),
                     k, "QR_UPDATE.q_post != substep_post.qr[:, k] (returned state diverged)")
                link(op_bits(k, "nr", "NR_UPDATE", "n_post") == _bits(post_snap["nr"][:, k], "f32"),
                     k, "NR_UPDATE.n_post != substep_post.nr[:, k] (returned state diverged)")

        # store this substep's post-state and outgoing accumulator for the next
        # substep of the SAME chain. _post_map fail-closes on missing qr/nr.
        post = _post_map(recs, c["container_id"])
        carry[chain_key] = {"n": n_sub, "post": post,
                            "fall_after": _fallacc(recs, "fall_after")}

    # branch-coverage verdict — the fixture must actually exercise every branch
    # the ladder claims to test, proven from the evidence, not assumed.
    lo, hi = 1, MSTEPMAX
    if cov["mstep"] is None or not (min(cov["mstep"]) >= lo and max(cov["mstep"]) <= hi):
        _die(EXIT_EVIDENCE, f"FAIL coverage: mstep {cov['mstep']} out of [1,{hi}]")
    # both a gated-off and a gated-on column must appear at the highest n
    top_gate = cov["gate_by_n"].get(MSTEPMAX)
    if not top_gate or 0 not in top_gate or 1 not in top_gate:
        _die(EXIT_EVIDENCE,
             f"FAIL coverage: n={MSTEPMAX} gate {top_gate} does not exercise "
             f"both gated-off (0) and gated-on (1)")
    if cov["floor_active"] != 0:
        _die(EXIT_EVIDENCE,
             f"FAIL coverage: {cov['floor_active']} density/metric floor "
             f"activations — a valid_metric fixture must have zero")
    # strict cap coverage: the fixture must produce at least one STRICTLY-bound
    # (RIGHT_SELECTED: reservoir < pre_cap) AND one STRICTLY-unbound
    # (LEFT_SELECTED: pre_cap < reservoir) element, per species. A VALUE_TIE
    # alone proves nothing (both branches agree on the value), and a NaN
    # (UNORDERED) reaching a cap is a hard FAIL, never coverage.
    for key, label in (("qr_cap", "QR"), ("nr_cap", "NR")):
        seen = cov[key]
        if gdv.BRANCH_UNORDERED in seen:
            _die(EXIT_EVIDENCE,
                 f"FAIL coverage: {label} outflow cap saw an UNORDERED (NaN) "
                 f"operand — a NaN reached min(); the fixture is corrupt")
        if not (gdv.BRANCH_LEFT_SELECTED in seen and gdv.BRANCH_RIGHT_SELECTED in seen):
            _die(EXIT_EVIDENCE,
                 f"FAIL coverage: {label} outflow cap did not exercise BOTH "
                 f"strictly-bound (RIGHT_SELECTED) and strictly-unbound "
                 f"(LEFT_SELECTED) (saw {sorted(seen)}) — a VALUE_TIE does not "
                 f"count; the fixture no longer tests the cap branch")
    # §7 interface residual envelope: the ρΔz transfer closes to within a few
    # ULP of the metric-weighted magnitude. A single fl32(divide)·multiply
    # round-trip gives κ≈0.5; metric amplification (χ) lifts it modestly. The
    # bound is a GROSS-ERROR tripwire (a dropped/wrong metric blows past it),
    # NOT a bit-exact claim — measured max is reported so drift is visible.
    if algorithm == "conservative":
        if resid["n"] == 0:
            _die(EXIT_EVIDENCE, "FAIL: no interface residual sampled — the "
                                "conservative transfer produced no interfaces")
        if resid["kappa_max"] > KAPPA_ENVELOPE:
            _die(EXIT_FIDELITY,
                 f"FAIL interface residual: κ_max {resid['kappa_max']:.3g} > "
                 f"{KAPPA_ENVELOPE} ULP — the ρΔz closure exceeds the roundoff "
                 f"envelope (a dropped/wrong metric, not rounding)")
    stats["coverage"] = (f"mstep {cov['mstep']}, n{MSTEPMAX} gate {top_gate}, "
                         f"floors {cov['floor_active']}, "
                         f"QR/NR cap both strictly bound+unbound, "
                         f"{stats_links['n']} causal links, "
                         f"interface κ_max {resid['kappa_max']:.3g} ULP "
                         f"(≤{KAPPA_ENVELOPE}), χ_max {resid['chi_max']:.3g}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", default="/tmp/g33_selfcheck_build/selfcheck_driver")
    a = ap.parse_args()
    driver = Path(a.driver)
    if not driver.is_file():
        print(f"SKIP: driver not built ({driver}) — run selfcheck_build.sh first")
        return EXIT_SKIP
    # Clean up ONLY on success. A failing run leaves its evidence directory in
    # place for forensics — the same reason build_env keeps a partial run
    # (auto-cleanup would destroy what a mismatch needs to be diagnosed from).
    # _die() exits without returning, so a failure never reaches the rmtree.
    root = Path(tempfile.mkdtemp(prefix="g33_selfcheck."))
    try:
        for algorithm in ("legacy", "conservative"):
            try:
                stats = check_algorithm(driver, algorithm, root / algorithm)
            except gd.G33Corruption as e:
                _die(EXIT_EVIDENCE, f"FAIL evidence: {algorithm}: {e}")
            print(f"{algorithm}: PASS — {stats['containers']} containers, "
                  f"{stats['shadow_actual']} shadow==actual, "
                  f"{stats['offline_rungs']} FALK + {stats['inflow_rungs']} INFLOW + "
                  f"{stats['ladder_rungs']} LADDER offline rungs bit-exact, "
                  f"{stats['flags']} producer cross-checks", flush=True)
            print(f"  coverage: {stats['coverage']}", flush=True)
    except SystemExit as e:
        # ANY failure keeps the evidence and reports where — the forensic
        # contract must not depend on which failure class fired (the fidelity
        # path _die's from inside check_algorithm without root in scope).
        if e.code:
            print(f"(evidence preserved at {root})", file=sys.stderr)
        raise
    shutil.rmtree(root, ignore_errors=True)     # success only
    print("SELF-CHECK PASS: shadow == actual == offline, both algorithms")
    print("  (fixture: valid_metric + arithmetic_synthetic — branch coverage, "
          "NOT a meteorological representativeness claim)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
