#!/usr/bin/env python3
"""Public-CI fail-closed tests for the evidence-bundle reader (P0-2/P0-3/P1-2/P1-3).
Builds COMPLETE, schedule-consistent {algo}-C-evidence trees with G33Writer +
matching SHA manifests (via g33_expectation), so verify_cpp_evidence exercises the
independent record-completeness gate, and verify_cpp_bundle the root attestation.
No torch."""
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_bundle_io as bio        # noqa: E402
import g33_dump as gd              # noqa: E402
import g33_expectation as ge       # noqa: E402
import g33_fixture_v1 as gfx        # noqa: E402
import g33_normalize as nz         # noqa: E402

B, K = 3, 4
DIAG = "d" * 64
COMMIT = "a1" * 20          # a well-formed 40-hex producer commit
CMAP = [[i, 0, i, i] for i in range(B)]


def _sched(algo, substeps=1):
    return {"case_id": "abc-fourcase_v1", "pair_id": f"abc-{algo}", "backend": "cpp",
            "algorithm": algo, "B": B, "K": K, "loops": 1, "mstepmax_main": [substeps],
            "mstepmax_ice": [substeps], "species_scope": ["qr", "nr"], "qcrmin": 1e-9,
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


def _payload(field, dtype, n_elem, lie_mstep, n=1, mstep=1):
    """Emit operands consistent with the producer contract: the mstep vector and the
    gate law gate == (n <= mstep) must recompute correctly from the raw values."""
    if field in ("mstep_input_native", "mstep_native"):
        v = float(mstep) + (0.5 if lie_mstep and field == "mstep_native" else 0.0)
    elif field == "mstep_decoded_i32":
        v = mstep
    elif field in ("gate_native", "gate_decoded_u8", "active_mask"):
        v = 1 if n <= mstep else 0
    else:
        v = _SUBPRE_VAL.get(field, 0)
    return gd.pack_payload(dtype, [v] * n_elem)


def _full_evidence(root: Path, algo: str, omit_container=None, lie_mstep=False,
                   substeps=1, mstep=1, mstep_by_n=None):
    """Write a complete {algo}-C-evidence tree; omit_container drops one container
    (file + descriptor) so it writes cleanly but the record multiset is short,
    exercising the independent completeness gate."""
    sched = _sched(algo, substeps)
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
        header = {"producer_commit": COMMIT, "binary_sha256": DIAG,
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
            n = r["n"] or 1
            m = (mstep_by_n or {}).get(n, mstep)
            w.record(key, r["dtype"], r["shape"],
                     _payload(r["field"], r["dtype"], n_elem, lie_mstep, n, m))
        w.finalize()
    (ev / "schema" / "descriptors.sha256").write_text("\n".join(desc_lines) + "\n")
    return ev


def _probe_stream(algo: str, mstep: int, dtcld=20.0) -> str:
    """A KDM6SCHED stream whose RAW FALL SPEEDS derive exactly `mstep`.

    floor(v * dtcld + 1) == mstep, so v sits in the middle of [m-1, m) / dtcld. The
    verifier recomputes this from the stream, so a bundle cannot simply assert its
    substep count.
    """
    v = (mstep - 0.5) / dtcld

    def hexes(vals):
        return " ".join(struct.pack(">f", float(x)).hex() for x in vals)

    lines = []
    # species_scope is [qr, nr], so only the main chain runs: the ice chain emits no
    # probe records and no containers
    for n in range(1, mstep + 1):
        # the work fields are whole-column [B, K]; mstep and dtcld are [B]
        lines.append(f"KDM6SCHED 1 main {n} work1_qr f32 {B * K} " + hexes([v] * (B * K)))
        for field in ("workn_qr", "work1_qs", "work1_qg"):
            lines.append(f"KDM6SCHED 1 main {n} {field} f32 {B * K} "
                         + hexes([0.0] * (B * K)))
        lines.append(f"KDM6SCHED 1 main {n} mstep_native f32 {B} " + hexes([mstep] * B))
        lines.append(f"KDM6SCHED 1 main {n} dtcld f32 {B} " + hexes([dtcld] * B))
    return "\n".join(lines) + "\n"


def _probe_dir(root: Path, algo: str, mstep: int, schedule=None) -> dict:
    """The probe a multi-substep bundle must ship, plus its lineage record.

    A bundle that declares more than one substep has to show where that number came
    from; the verifier re-derives it from this stream rather than trusting the
    contract. Building it here keeps the synthetic multi-substep bundle honest — it
    used to assert that such a bundle verifies while shipping nothing that could
    establish its own substep count.
    """
    d = root / f"{algo}-probe"
    d.mkdir()
    stream = _probe_stream(algo, mstep)
    (d / "probe.sched").write_text(stream)
    # A real probe writes the WHOLE sealed schedule, and the verifier now requires it
    # to equal the contract the evidence was sealed with — hashing the file only
    # proves it is the one the probe wrote (owner P0-9).
    schedule = json.dumps(schedule, indent=2, sort_keys=True) + "\n"
    (d / "schedule.json").write_text(schedule)
    (d / "probe_manifest.json").write_text(json.dumps({
        "schema_version": 1, "algorithm": algo,
        "fixture_id": gfx.load_manifest()["fixture_id"],
        "fixture_manifest_sha256": gfx.manifest_sha256(gfx.load_manifest()),
        "noninvasiveness_checked": True,
        "diagnostic_driver_sha256": DIAG,
        "probe_stream_sha256": hashlib.sha256(stream.encode()).hexdigest(),
        "schedule_sha256": hashlib.sha256(schedule.encode()).hexdigest(),
    }, indent=2, sort_keys=True) + "\n")
    return {"probe_dir": f"{algo}-probe",
            "probe_stream_sha256": _sha(d / "probe.sched"),
            "schedule_sha256": _sha(d / "schedule.json"),
            "probe_manifest_sha256": _sha(d / "probe_manifest.json")}


def _abc_stdout(algo: str, truncate=False, rain="00000000") -> str:
    """A complete ABC frame: 12 state fields [B,K] + 3 increments [B], all f32."""
    lines = [f"KDM6ABC 1 {algo} fourcase_v1 {B} {K}"]
    for name in gfx.STATE_FIELDS:
        lines.append(f"FIELD {name} f32 2 {B} {K} {B * K} " + " ".join(["3f800000"] * (B * K)))
    for name in ("rain_increment", "snow_increment", "graupel_increment"):
        word = rain if name == "rain_increment" else "00000000"
        lines.append(f"FIELD {name} f32 1 {B} {B} " + " ".join([word] * B))
    if truncate:
        lines = lines[:6]
    lines.append("END")
    return "\n".join(lines) + "\n"


def _bundle(root: Path, truncate_abc=False, rain="00000000", **ev):
    """A full two-leg bundle with manifest + A/B/C stdout for root attestation.
    Fixture/parameter SHAs come from the CHECKED-IN authority, so the bundle is
    bound to the real problem rather than to its own self-consistent manifest."""
    authority = gfx.load_manifest()
    for algo in ("legacy", "conservative"):
        _full_evidence(root, algo, **ev)
        for lane in ("A", "B", "C"):
            d = root / f"{algo}-{lane}"
            d.mkdir()
            (d / "stdout.abc").write_text(_abc_stdout(algo, truncate_abc, rain))
    manifest = {"schema_version": 1, "diagnostic_driver_sha256": DIAG,
                "canonical_driver_sha256": "c" * 64,
                # the real label: the bundle already carries the real SHAs, and the
                # verifier now binds the name to them too
                "fixture_id": authority["fixture_id"],
                "fixture_manifest_sha256": gfx.manifest_sha256(authority),
                "algorithms": {}}
    substeps = ev.get("substeps", 1)
    msteps = list((ev.get("mstep_by_n") or {}).values()) or [ev.get("mstep", 1)]
    declared = (ev.get("mstep_by_n") or {}).get(1, ev.get("mstep", 1))
    for algo in ("legacy", "conservative"):
        sha = _sha(root / f"{algo}-A" / "stdout.abc")
        # A multi-substep contract must ship the probe that establishes it, exactly
        # as a real bundle does.
        probe = (_probe_dir(root, algo, declared, schedule=_sched(algo, substeps))
                 if max(declared, substeps) > 1 else {})
        manifest["algorithms"][algo] = {
            **probe,
            "abc_equal": True, "containers": 4 + substeps,
            "evidence_dir": f"{algo}-C-evidence",
            "fixture_sha256": gfx.fixture_sha256(authority),
            "parameter_sha256": gfx.parameter_sha256(authority),
            "mstep_min": min(msteps), "mstep_max": max(msteps),
            "stdout_sha256": {"A": sha, "B": sha, "C": sha}}
        manifest["algorithms"][algo]["evidence_tree_sha256"] = (
            bio.cpp_evidence_tree_sha256(
                root, f"{algo}-C-evidence", probe.get("probe_dir")))
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


def test_both_legs_sharing_a_WRONG_fixture_rejected(tmp_path):
    # P0-5: leg-vs-leg equality alone would accept this — the wrong-problem bundle.
    root = _bundle(tmp_path)
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    for algo in ("legacy", "conservative"):
        m["algorithms"][algo]["fixture_sha256"] = "d" * 64
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError, match="authority"):
        bio.verify_cpp_bundle(root)


def test_wrong_fixture_manifest_sha_rejected(tmp_path):
    root = _bundle(tmp_path)
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    m["fixture_manifest_sha256"] = "e" * 64
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError, match="authority"):
        bio.verify_cpp_bundle(root)


def test_truncated_abc_stdout_rejected(tmp_path):
    # P0-6: all three lanes truncated identically — hashes still agree, so only a
    # full protocol re-parse catches it.
    with pytest.raises(bio.BundleError, match="stdout"):
        bio.verify_cpp_bundle(_bundle(tmp_path, truncate_abc=True))


def test_two_substep_bundle_verifies(tmp_path):
    out = bio.verify_cpp_bundle(_bundle(tmp_path, substeps=2, mstep=2))
    assert out["algorithms"]["legacy"].mstep_range == (2, 2)


def test_mstep_exceeding_declared_substeps_rejected(tmp_path):
    # P0-2: the columns really need n=2, but the schedule declares one substep — the
    # bundle is complete against its OWN contract while the n=2 evidence is absent.
    with pytest.raises(bio.BundleError, match="mstep max"):
        bio.verify_cpp_bundle(_bundle(tmp_path, substeps=1, mstep=2))


def _anchors(root):
    _, authority = gfx.load_fixture(gfx.DEFAULT_FIXTURE_ID)
    return {"expected_manifest_sha256": _sha(root / "cpp_abc_manifest.json"),
            "expected_repo_commit": COMMIT,
            "expected_fixture_id": gfx.DEFAULT_FIXTURE_ID,
            # the fixture BYTES, not just its name
            "expected_fixture_manifest_sha256": gfx.manifest_sha256(authority)}


def test_verdict_ready_requires_external_anchors(tmp_path):
    root = _bundle(tmp_path)
    leg = bio.verify_cpp_bundle(root)["algorithms"]["legacy"]
    assert leg.root_attested and not leg.verdict_ready      # internal-only
    full = bio.verify_cpp_bundle(root, **_anchors(root))["algorithms"]["legacy"]
    assert full.verdict_ready


@pytest.mark.parametrize("drop", ["expected_manifest_sha256", "expected_repo_commit",
                                  "expected_fixture_id",
                                  "expected_fixture_manifest_sha256"])
def test_no_single_anchor_can_be_omitted_at_the_API(tmp_path, drop):
    # The CLI requires all three, but a Python caller reaches this function directly.
    # If the fixture defaulted here, omitting it would still mint a verdict-ready leg
    # — the CLI would be anchored while the API it calls was not.
    root = _bundle(tmp_path)
    kw = {k: v for k, v in _anchors(root).items() if k != drop}
    leg = bio.verify_cpp_bundle(root, **kw)["algorithms"]["legacy"]
    assert not leg.verdict_ready


def test_mstep_vector_drift_between_substeps_rejected(tmp_path):
    # P0-4: each substep is internally consistent (gate law holds for both), so only
    # the cross-substep continuity check sees that the vector changed.
    with pytest.raises(bio.BundleError, match="mstep"):
        bio.verify_cpp_bundle(_bundle(tmp_path, substeps=2, mstep_by_n={1: 2, 2: 3}))


def test_verified_leg_is_deep_frozen(tmp_path):
    leg = bio.verify_cpp_bundle(_bundle(tmp_path))["algorithms"]["legacy"]
    cid = next(iter(leg.containers))
    with pytest.raises(TypeError):        # forging after verification must not work
        leg.containers[cid]["records"][0]["payload"] = b"forged"


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
    root = _bundle(tmp_path)
    res = bio.verify_cpp_bundle(root, **_anchors(root))          # fully attested
    run = nz.from_cpp_evidence(res["algorithms"]["legacy"])
    assert run["algorithm"] == "legacy" and run["B"] == B and run["K"] == K
    import g33_fourcase_comparator as cmp
    events = cmp._events(run)          # schema order + range + dtype + identity
    assert events and run["ops"]


def test_cpp_leg_declares_the_kernel_boundary(tmp_path):
    """The port implements kdm62D and has no wrapper, so it must SAY `kernel`.

    With the field absent on the C++ side, `SedimentationIdentity`'s default would
    make a Fortran wrapper leg and a Fortran kernel leg both compare equal against
    it, and the four-way boundary check would agree with whatever it was handed.
    That silent agreement is what let the dt=300 run compare a wrapper Fortran leg
    against a kernel C++ leg and report the resulting nccn mismatch as a physics
    divergence."""
    root = _bundle(tmp_path)
    res = bio.verify_cpp_bundle(root, **_anchors(root))
    run = nz.from_cpp_evidence(res["algorithms"]["legacy"])
    assert run["problem"]["entry_boundary"] == "kdm62d_kernel_entry_v1"


def test_unattested_leg_refused_by_normalizer(tmp_path):
    leg = bio.verify_cpp_evidence(_full_evidence(tmp_path, "legacy"), "legacy")
    with pytest.raises(nz.NormalizeError):          # root_attested is False
        nz.from_cpp_evidence(leg)


def test_internally_verified_but_unanchored_leg_is_not_verdict_ready(tmp_path):
    # P0-3: verify_cpp_bundle without the external anchors gives root_attested=True
    # but NOT verdict_ready — the decision path must refuse it.
    leg = bio.verify_cpp_bundle(_bundle(tmp_path))["algorithms"]["legacy"]
    assert leg.root_attested and not leg.verdict_ready
    with pytest.raises(nz.NormalizeError, match="verdict_ready"):
        nz.from_cpp_evidence(leg)
    nz.from_cpp_evidence(leg, require_verdict_ready=False)      # debug path only


def test_falsely_exact_mstep_flag_rejected(tmp_path):
    # P0-1: producer reports mstep_exact_integer=1 but mstep_native=1.5 — the
    # INDEPENDENT recomputation from the raw operand rejects the lie at verify time.
    tree = _full_evidence(tmp_path, "legacy", lie_mstep=True)
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(tree, "legacy")


# ── external anchors (the bundle cannot self-attest) ─────────────────────────
def test_external_manifest_anchor_enforced(tmp_path):
    root = _bundle(tmp_path)
    good = _sha(root / "cpp_abc_manifest.json")
    bio.verify_cpp_bundle(root, expected_manifest_sha256=good)      # matching anchor
    with pytest.raises(bio.BundleError, match="external anchor"):
        bio.verify_cpp_bundle(root, expected_manifest_sha256="f" * 64)


def test_external_repo_commit_anchor_enforced(tmp_path):
    root = _bundle(tmp_path)
    bio.verify_cpp_bundle(root, expected_repo_commit=COMMIT)
    with pytest.raises(bio.BundleError, match="producer_commit"):
        bio.verify_cpp_bundle(root, expected_repo_commit="b2" * 20)


def test_non_commit_producer_rejected(tmp_path):
    ev = _full_evidence(tmp_path, "legacy")
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy", expected_repo_commit="b2" * 20)


def test_the_runs_actual_returned_output_is_preserved(tmp_path):
    # Structural A/B/C equality alone threw the returned values away, so the decision
    # compared a harness re-derivation instead of what the runtime handed back.
    out = bio.verify_cpp_bundle(_bundle(tmp_path, rain="3f800000"))
    leg = out["algorithms"]["legacy"]
    assert leg.actual_final_output["rain"] == (0x3F800000,) * B
    assert leg.actual_final_output["snow"] == (0,) * B


def test_the_actual_output_is_read_from_the_evidence_not_assumed(tmp_path):
    out = bio.verify_cpp_bundle(_bundle(tmp_path, rain="40000000"))
    assert out["algorithms"]["legacy"].actual_final_output["rain"] == (0x40000000,) * B


# ── completeness has no opt-out ───────────────────────────────────────────────
# The abandoned container-discovery mode used to let a probe-marked case write fewer
# containers than it declared. It is gone: a schedule now comes from the KDM6SCHED
# stream, so nothing needs a switch that turns the completeness gate off.

def test_a_real_case_still_needs_every_declared_container(tmp_path):
    ev = _full_evidence(tmp_path, "legacy", omit_container="L1_outer_post_sed")
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


# ── probe lineage: the schedule must be traceable to a run of THIS binary ──────
# The reproduce gate lives in g33_fourcase_fixture_check, but it runs at PRODUCTION
# time and the probe stream never travelled with the bundle. A later reader had the
# producer's word and nothing else.

def test_a_multi_substep_bundle_without_a_probe_is_refused(tmp_path):
    root = _bundle(tmp_path, substeps=2, mstep=2)
    shutil.rmtree(root / "legacy-probe")
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    for key in ("probe_dir", "probe_stream_sha256", "schedule_sha256",
                "probe_manifest_sha256"):
        m["algorithms"]["legacy"].pop(key)
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError, match="no probe lineage"):
        bio.verify_cpp_bundle(root)


def test_a_probe_of_a_DIFFERENT_binary_is_refused(tmp_path):
    # the schedule would then describe one build's substep decisions and the sealed
    # containers another's — the exact thing the two-pass design exists to rule out
    root = _bundle(tmp_path, substeps=2, mstep=2)
    pm = root / "legacy-probe" / "probe_manifest.json"
    doc = json.loads(pm.read_text())
    doc["diagnostic_driver_sha256"] = "9" * 64
    pm.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    m["algorithms"]["legacy"]["probe_manifest_sha256"] = _sha(pm)
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError, match="the evidence came from"):
        bio.verify_cpp_bundle(root)


def test_a_probe_stream_that_derives_a_DIFFERENT_schedule_is_refused(tmp_path):
    """The bundle ships a real stream, but its fall speeds imply one substep while the
    evidence was sealed with two. Re-deriving offline is the only thing that can see
    this: every hash in the bundle still agrees with every other."""
    root = _bundle(tmp_path, substeps=2, mstep=2)
    d = root / "legacy-probe"
    slow = _probe_stream("legacy", mstep=1)          # v placed in [0, 1)/dtcld
    (d / "probe.sched").write_text(slow)
    pm = d / "probe_manifest.json"
    doc = json.loads(pm.read_text())
    doc["probe_stream_sha256"] = hashlib.sha256(slow.encode()).hexdigest()
    pm.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    m["algorithms"]["legacy"]["probe_stream_sha256"] = _sha(d / "probe.sched")
    m["algorithms"]["legacy"]["probe_manifest_sha256"] = _sha(pm)
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    with pytest.raises(bio.BundleError, match="but the evidence was sealed with"):
        bio.verify_cpp_bundle(root)


def test_a_tampered_probe_stream_is_refused(tmp_path):
    root = _bundle(tmp_path, substeps=2, mstep=2)
    f = root / "legacy-probe" / "probe.sched"
    f.write_text(f.read_text() + "KDM6SCHED 1 main 1 dtcld f32 1 41a00000\n")
    with pytest.raises(bio.BundleError, match="probe.sched sha256"):
        bio.verify_cpp_bundle(root)


def test_lineage_is_recorded_on_the_verified_leg(tmp_path):
    leg = bio.verify_cpp_bundle(_bundle(tmp_path, substeps=2, mstep=2))["algorithms"]["legacy"]
    assert leg.probe_lineage["diagnostic_driver_sha256"] == DIAG
    with pytest.raises(TypeError):                    # frozen like the rest of the leg
        leg.probe_lineage["diagnostic_driver_sha256"] = "0" * 64


def test_a_single_substep_bundle_needs_no_probe(tmp_path):
    # nothing to derive: the contract declares one loop of one substep
    leg = bio.verify_cpp_bundle(_bundle(tmp_path))["algorithms"]["legacy"]
    assert leg.probe_lineage is None


# ── the WHOLE schedule, and the fixture the probe was of (owner P0-9) ──────────

def _repoint(root, algo="legacy", **probe_edit):
    """Edit the shipped probe manifest/schedule and re-anchor every hash, so the
    bundle stays self-consistent — which is the point: these forgeries are invisible
    to any check that only re-hashes files."""
    d = root / f"{algo}-probe"
    for name, edit in probe_edit.items():
        f = d / name.replace("__", ".")
        doc = json.loads(f.read_text())
        edit(doc)
        f.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    pm = d / "probe_manifest.json"
    doc = json.loads(pm.read_text())
    doc["schedule_sha256"] = _sha(d / "schedule.json")
    doc["probe_stream_sha256"] = _sha(d / "probe.sched")
    pm.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    m = json.loads((root / "cpp_abc_manifest.json").read_text())
    m["algorithms"][algo].update(
        schedule_sha256=_sha(d / "schedule.json"),
        probe_manifest_sha256=_sha(pm),
        probe_stream_sha256=_sha(d / "probe.sched"))
    (root / "cpp_abc_manifest.json").write_text(json.dumps(m))
    return root


def test_a_schedule_matching_only_in_mstepmax_is_refused(tmp_path):
    """qcrmin, dtcld, B/K, species_scope, instrumented_stages and the case/pair ids
    could all differ while the substep counts agreed, and the evidence would have
    been sealed against a contract the probe never produced."""
    root = _repoint(_bundle(tmp_path / "b", substeps=2, mstep=2),
                    schedule__json=lambda d: d.update(qcrmin=1.0))
    with pytest.raises(bio.BundleError, match="not the schedule the probe derived"):
        bio.verify_cpp_bundle(root)


def test_a_schedule_differing_in_species_scope_is_refused(tmp_path):
    root = _repoint(_bundle(tmp_path / "b", substeps=2, mstep=2),
                    schedule__json=lambda d: d.update(species_scope=["qr"]))
    with pytest.raises(bio.BundleError, match=r"differ on \['species_scope'\]"):
        bio.verify_cpp_bundle(root)


def test_a_probe_of_a_DIFFERENT_fixture_is_refused(tmp_path):
    root = _repoint(_bundle(tmp_path / "b", substeps=2, mstep=2),
                    probe_manifest__json=lambda d: d.update(fixture_id="other_v1"))
    with pytest.raises(bio.BundleError, match="probe is for fixture"):
        bio.verify_cpp_bundle(root)


def test_a_probe_whose_fixture_hash_differs_is_refused(tmp_path):
    root = _repoint(
        _bundle(tmp_path / "b", substeps=2, mstep=2),
        probe_manifest__json=lambda d: d.update(fixture_manifest_sha256="0" * 64))
    with pytest.raises(bio.BundleError, match="fixture manifest sha"):
        bio.verify_cpp_bundle(root)


def test_a_probe_that_skipped_the_noninvasiveness_check_is_refused(tmp_path):
    # a probe that perturbed the run it measured would seal a schedule for a
    # different execution than the one under test
    root = _repoint(
        _bundle(tmp_path / "b", substeps=2, mstep=2),
        probe_manifest__json=lambda d: d.update(noninvasiveness_checked=False))
    with pytest.raises(bio.BundleError, match="non-invasiveness"):
        bio.verify_cpp_bundle(root)
