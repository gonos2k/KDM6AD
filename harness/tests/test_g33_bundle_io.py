#!/usr/bin/env python3
"""Public-CI fail-closed tests for the evidence-bundle reader (P0-2/P0-3/P1-2/P1-3).
Builds COMPLETE, schedule-consistent {algo}-C-evidence trees with G33Writer +
matching SHA manifests (via g33_expectation), so verify_cpp_evidence exercises the
independent record-completeness gate, and verify_cpp_bundle the root attestation.
No torch."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_bundle_io as bio        # noqa: E402
import g33_dump as gd              # noqa: E402
import g33_expectation as ge       # noqa: E402
import g33_normalize as nz         # noqa: E402

B, K = 3, 4
DIAG = "d" * 64
CMAP = [[i, 0, i, i] for i in range(B)]


def _sched(algo):
    return {"case_id": "abc-fourcase_v1", "pair_id": f"abc-{algo}", "backend": "cpp",
            "algorithm": algo, "B": B, "K": K, "loops": 1, "mstepmax_main": [1],
            "mstepmax_ice": [1], "species_scope": ["qr", "nr"], "qcrmin": 1e-9,
            "dtcld": 20.0, "instrumented_stages": ["outer_pre_sed", "substep_pre",
            "op", "surface", "outer_post_sed", "outer_post_micro"]}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Valid raw operands for a substep_pre group, so the independent producer-flag
# recomputation (g33_derived.check_producer_flags) passes: mstep=1 exact, gate=1
# exact/active, unfloored positive metrics, sealed qcrmin/dtcld.
_SUBPRE_VAL = {
    "mstep_input_native": 1.0, "mstep_native": 1.0, "mstep_decoded_i32": 1,
    "mstep_exact_integer": 1, "gate_native": 1.0, "gate_decoded_u8": 1,
    "gate_exact_01": 1, "active_mask": 1, "dend_raw": 1.0, "dend_safe": 1.0,
    "dend_floor_active": 0, "delz_raw": 1.0, "delz_safe": 1.0,
    "delz_floor_active": 0, "qcrmin_effective": 1e-9, "dtcld_effective": 20.0,
    "qr": 0.5, "nr": 100.0, "work1_qr": 0.1, "workn_qr": 0.1,
}


def _payload(field, dtype, n_elem, lie_mstep):
    v = _SUBPRE_VAL.get(field, 0)
    if lie_mstep and field == "mstep_native":
        v = 1.5                       # non-integer, but the flag still claims exact
    return gd.pack_payload(dtype, [v] * n_elem)


def _full_evidence(root: Path, algo: str, omit_container=None, lie_mstep=False):
    """Write a complete {algo}-C-evidence tree; omit_container drops one container
    (file + descriptor) so it writes cleanly but the record multiset is short,
    exercising the independent completeness gate."""
    sched = _sched(algo)
    recs = list(ge.expected_records(sched))
    index = ge.run_index(sched)["containers"]
    by_cid: dict[str, list] = {}
    for r in recs:
        by_cid.setdefault(ge.container_id(r), []).append(r)

    ev = root / f"{algo}-C-evidence"
    (ev / "dump").mkdir(parents=True)
    (ev / "schema").mkdir()
    contract = {"schedule": sched, "containers": index, "version": 1,
                "binary_sha256": DIAG, "case_id": sched["case_id"]}
    (ev / "run_contract.json").write_text(json.dumps(contract, sort_keys=True))
    csha = _sha(ev / "run_contract.json")
    (ev / "run_contract.sha256").write_text(f"{csha}  run_contract.json\n")

    desc_lines = []
    for spec in index:
        cid = spec["container_id"]
        if cid == omit_container:
            continue
        (ev / "schema" / f"{cid}.desc").write_text(f"desc {cid}\n")
        dsha = _sha(ev / "schema" / f"{cid}.desc")
        desc_lines.append(f"{dsha}  {cid}.desc")
        crecs = sorted(by_cid.get(cid, []), key=lambda r: r["op_seq_id"])
        first = spec["first_op_seq_id"]
        header = {"producer_commit": "c", "binary_sha256": DIAG,
                  "resolved_binary_path": "/x", "resolved_binary_sha256": DIAG,
                  "case_id": sched["case_id"], "pair_id": sched["pair_id"],
                  "backend": "cpp", "algorithm": algo, "B": B, "K": K,
                  "column_layout_id": "l", "column_index_map": CMAP,
                  "canonical_k_order": "top-first", "run_uuid": "u", "process_id": 1,
                  "owner_thread_id": "2", "container_id": cid,
                  "descriptor_sha256": dsha, "run_contract_sha256": csha,
                  "global_op_seq_start": first, "global_op_seq_end": spec["last_op_seq_id"],
                  "record_count_expected": spec["record_count"]}
        w = gd.G33Writer(ev / "dump" / f"cpp_{algo}_{cid}.g33", header)
        for r in crecs:
            n_elem = 1
            for s in r["shape"]:
                n_elem *= s
            key = {**r, "seq_no": r["op_seq_id"] - first}
            w.record(key, r["dtype"], r["shape"], _payload(r["field"], r["dtype"], n_elem, lie_mstep))
        w.finalize()
    (ev / "schema" / "descriptors.sha256").write_text("\n".join(desc_lines) + "\n")
    return ev


def _bundle(root: Path):
    """A full two-leg bundle with manifest + A/B/C stdout for root attestation."""
    for algo in ("legacy", "conservative"):
        _full_evidence(root, algo)
        for lane in ("A", "B", "C"):
            d = root / f"{algo}-{lane}"
            d.mkdir()
            (d / "stdout.abc").write_text(f"KDM6ABC 1 {algo} fourcase_v1 {B} {K}\nEND\n")
    manifest = {"schema_version": 1, "diagnostic_driver_sha256": DIAG,
                "canonical_driver_sha256": "c" * 64, "fixture_id": "f", "algorithms": {}}
    for algo in ("legacy", "conservative"):
        sha = _sha(root / f"{algo}-A" / "stdout.abc")
        manifest["algorithms"][algo] = {
            "abc_equal": True, "containers": 5, "evidence_dir": f"{algo}-C-evidence",
            "fixture_sha256": "a" * 64, "parameter_sha256": "b" * 64,
            "mstep_min": 1, "mstep_max": 1,
            "stdout_sha256": {"A": sha, "B": sha, "C": sha}}
    (root / "cpp_abc_manifest.json").write_text(json.dumps(manifest))
    return root


# ── P0-2 completeness ─────────────────────────────────────────────────────────
def test_complete_evidence_verifies(tmp_path):
    ev = _full_evidence(tmp_path, "legacy")
    out = bio.verify_cpp_evidence(ev, "legacy")
    assert set(out.containers) >= set(bio.COMPARATOR_CONTAINERS)
    assert out.root_attested is False          # not root-attested from evidence alone


def test_incomplete_evidence_rejected(tmp_path):
    # omit a non-comparator container: writes cleanly, but the record multiset is
    # short of the schedule -> the completeness gate (not read_container) catches it.
    ev = _full_evidence(tmp_path, "legacy", omit_container="L1_outer_post_sed")
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


def test_tampered_contract_rejected(tmp_path):
    ev = _full_evidence(tmp_path, "legacy")
    (ev / "run_contract.json").write_text('{"schedule": {}, "tampered": true}')
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


def test_unlisted_extra_file_rejected(tmp_path):
    ev = _full_evidence(tmp_path, "legacy")
    (ev / "schema" / "sneak.desc").write_text("x\n")
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


def test_stray_file_in_dump_rejected(tmp_path):
    ev = _full_evidence(tmp_path, "legacy")
    (ev / "dump" / "leftover.g33.tmp").write_text("x\n")   # stale/partial write
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


# ── P0-3 root attestation ─────────────────────────────────────────────────────
def test_full_bundle_verifies(tmp_path):
    out = bio.verify_cpp_bundle(_bundle(tmp_path))
    assert set(out["algorithms"]) == {"legacy", "conservative"}


def test_missing_algorithm_leg_rejected(tmp_path):
    root = _bundle(tmp_path)
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    del m["algorithms"]["conservative"]
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_bundle(root)


def test_mismatched_fixture_across_legs_rejected(tmp_path):
    root = _bundle(tmp_path)
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    m["algorithms"]["conservative"]["fixture_sha256"] = "c" * 64  # valid hex, differs
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_bundle(root)


def test_tampered_stdout_rejected(tmp_path):
    root = _bundle(tmp_path)
    (root / "legacy-B" / "stdout.abc").write_text("different\n")
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_bundle(root)


def test_manifest_duplicate_json_key_rejected(tmp_path):
    root = _bundle(tmp_path)
    (root / "cpp_abc_manifest.json").write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_bundle(root)


# ── P1-2 C++ normalize on synthetic evidence ──────────────────────────────────
def test_cpp_evidence_normalizes_and_events_build(tmp_path):
    res = bio.verify_cpp_bundle(_bundle(tmp_path))     # root-attested leg
    run = nz.from_cpp_evidence(res["algorithms"]["legacy"])
    assert run["algorithm"] == "legacy" and run["B"] == B and run["K"] == K
    import g33_fourcase_comparator as cmp
    events = cmp._events(run)          # schema order + range + dtype + identity
    assert events and run["ops"]


def test_unattested_leg_refused_by_normalizer(tmp_path):
    leg = bio.verify_cpp_evidence(_full_evidence(tmp_path, "legacy"), "legacy")
    with pytest.raises(nz.NormalizeError):          # root_attested is False
        nz.from_cpp_evidence(leg)


def test_falsely_exact_mstep_flag_rejected(tmp_path):
    # P0-1: producer reports mstep_exact_integer=1 but mstep_native=1.5 — the
    # INDEPENDENT recomputation from the raw operand rejects the lie at verify time.
    tree = _full_evidence(tmp_path, "legacy", lie_mstep=True)
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(tree, "legacy")
