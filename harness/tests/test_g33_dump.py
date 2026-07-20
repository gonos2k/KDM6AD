#!/usr/bin/env python3
"""Synthetic fail-closed tests for the G3.3-M dump container + expectation manifest
(protocol §7). No physics, no build — pure Python. Proves the reader/comparator
REJECT corrupt / missing / duplicate / stale / provenance-drift evidence, so a
buggy or tampered dump can never read as valid.
"""
import json
import re
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_derived as gdv
import g33_dump as gd
import g33_expectation as ge

SCHED = {"case_id": "closure3-C3.3", "pair_id": "conservative", "backend": "cpp",
         "algorithm": "conservative", "B": 3, "K": 4, "loops": 1,
         "mstepmax_main": [1], "mstepmax_ice": [2], "species_scope": ["qr", "nr"],
         "qcrmin": 1e-9,
         "instrumented_stages": ["substep_pre", "op", "surface", "outer_pre_sed",
                                 "outer_post_sed", "outer_post_micro",
                                 "reslope_input", "reslope_output", "substep_post"]}


def _header(**over):
    h = {"producer_commit": "deadbeef", "binary_sha256": "0" * 64,
         "resolved_binary_path": "/fixtures/libkdm6ad.dylib",
         "resolved_binary_sha256": "0" * 64,
         "case_id": SCHED["case_id"], "pair_id": SCHED["pair_id"],
         "backend": SCHED["backend"], "algorithm": SCHED["algorithm"],
         "B": SCHED["B"], "K": SCHED["K"], "column_layout_id": "lc05-3col",
         "column_index_map": [[i, 0, i, i] for i in range(SCHED["B"])],
         "canonical_k_order": "top-first",
         "run_uuid": "uuid-1", "process_id": 111, "owner_thread_id": "222",
         "container_id": "L1_main_n1", "descriptor_sha256": "a" * 64,
         "global_op_seq_start": 0, "global_op_seq_end": 0,
         "record_count_expected": 0}
    h.update(over)
    return h


def _write_valid(path, records=None):
    recs = records if records is not None else ge.expected_records(SCHED)
    w = gd.G33Writer(path, _header(record_count_expected=len(recs),
                                   global_op_seq_end=len(recs) - 1))
    for r in recs:
        n_elem = 1
        for s in r["shape"]:
            n_elem *= s
        payload = gd.pack_payload(r["dtype"], [1] * n_elem)
        w.record(r, r["dtype"], r["shape"], payload)
    w.finalize()
    return recs


# ── happy path ───────────────────────────────────────────────────────────────
def test_roundtrip_valid(tmp_path):
    p = tmp_path / "c.g33"
    recs = _write_valid(p)
    out = gd.read_container(p)
    assert out["footer"]["complete"] is True
    assert len(out["records"]) == len(recs)
    # observed keys == INDEPENDENT expectation
    observed = {ge.record_key(r) for r in out["records"]}
    assert observed == ge.expected_key_set(SCHED)


# ── structural corruption ─────────────────────────────────────────────────────
def test_bad_magic(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    b = bytearray(p.read_bytes()); b[0:4] = b"XXXX"; p.write_bytes(b)
    with pytest.raises(gd.G33Corruption, match="magic"):
        gd.read_container(p)


def test_truncated_no_footer(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    b = p.read_bytes(); p.write_bytes(b[: len(b) // 2])  # cut mid-stream
    with pytest.raises(gd.G33Corruption):
        gd.read_container(p)


def test_payload_sha_tamper(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    b = bytearray(p.read_bytes())
    # walk to the FIRST record's payload and flip a byte there -> the JSON still
    # parses but payload_sha256 must mismatch (genuine payload-tamper path).
    off = 12
    hlen = struct.unpack_from("<I", b, off)[0]; off += 4 + hlen
    off += 4                                     # REC sentinel
    klen = struct.unpack_from("<I", b, off)[0]; off += 4 + klen
    plen = struct.unpack_from("<I", b, off)[0]; off += 4
    assert plen > 0
    b[off] ^= 0xFF                               # first payload byte
    p.write_bytes(b)
    with pytest.raises(gd.G33Corruption, match="sha256"):
        gd.read_container(p)


def test_footer_not_at_eof(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    p.write_bytes(p.read_bytes() + b"trailing")
    with pytest.raises(gd.G33Corruption, match="EOF|trailing"):
        gd.read_container(p)


def test_wrong_version(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    b = bytearray(p.read_bytes())
    struct.pack_into("<I", b, 8, 999)  # version right after 8-byte magic
    p.write_bytes(b)
    with pytest.raises(gd.G33Corruption, match="version"):
        gd.read_container(p)


# ── writer contract (§7e) ─────────────────────────────────────────────────────
def test_refuse_overwrite(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    with pytest.raises(gd.G33Corruption, match="overwrite"):
        gd.G33Writer(p, _header())


def test_stale_tmp(tmp_path):
    p = tmp_path / "c.g33"
    (tmp_path / "c.g33.tmp").write_bytes(b"stale")
    with pytest.raises(gd.G33Corruption, match="stale"):
        gd.G33Writer(p, _header())


def test_duplicate_seq(tmp_path):
    # seq_no must be EXACTLY its record index, so a repeat is a gap, not merely a
    # duplicate: a monotonicity-only rule would accept 0,1,1 losing one record.
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 0, "op_seq_id": 0, "outer_loop": 1, "chain": "main", "n": 1,
         "cell_role": "TOP", "species": "qr", "op_id": "QR_FALK", "stage": "op",
         "field": "falk_f32"}
    w.record(r, "f32", [1], gd.pack_payload("f32", [1]))
    with pytest.raises(gd.G33Corruption, match="seq_no"):
        w.record({**r, "op_seq_id": 1}, "f32", [1], gd.pack_payload("f32", [1]))


def test_nonmonotone_seq(tmp_path):
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    base = {"outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
            "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    with pytest.raises(gd.G33Corruption, match="seq_no"):
        w.record({**base, "seq_no": 10, "op_seq_id": 10}, "f32", [1],
                 gd.pack_payload("f32", [1]))


def test_op_seq_id_obeys_the_exact_window_law(tmp_path):
    # op_seq_id == global_op_seq_start + seq_no, exactly. "Strictly increasing
    # and inside the window" let [100,105] hold only 100,102,105 — gaps INSIDE
    # the window were structurally invisible. Repeats, gaps and offsets are all
    # the same violation of one equation.
    base = {"outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
            "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    w = gd.G33Writer(tmp_path / "a.g33", _header(global_op_seq_start=100,
                                                 global_op_seq_end=105))
    w.record({**base, "seq_no": 0, "op_seq_id": 100}, "f32", [1],
             gd.pack_payload("f32", [1]))
    with pytest.raises(gd.G33Corruption, match="exact-window law"):
        w.record({**base, "seq_no": 1, "op_seq_id": 102}, "f32", [1],
                 gd.pack_payload("f32", [1]))          # gap INSIDE the window
    w2 = gd.G33Writer(tmp_path / "b.g33", _header())
    with pytest.raises(gd.G33Corruption, match="exact-window law"):
        w2.record({**base, "seq_no": 0, "op_seq_id": 7}, "f32", [1],
                  gd.pack_payload("f32", [1]))         # offset from the start


def test_partial_window_cannot_be_finalized(tmp_path):
    # a container that covered only part of its declared window must never
    # receive a COMPLETE footer
    base = {"outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
            "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    w = gd.G33Writer(tmp_path / "c.g33", _header(global_op_seq_start=0,
                                                 global_op_seq_end=2))
    w.record({**base, "seq_no": 0, "op_seq_id": 0}, "f32", [1],
             gd.pack_payload("f32", [1]))
    with pytest.raises(gd.G33Corruption, match="partial window"):
        w.finalize()


def test_op_seq_id_outside_declared_window(tmp_path):
    # The header window is DECLARED before the run (run_index.json). A record
    # landing outside it is the signature of a container that executed out of
    # the declared order — the reason the window is declared rather than derived.
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header(global_op_seq_start=100, global_op_seq_end=200))
    r = {"seq_no": 0, "op_seq_id": 99, "outer_loop": 1, "chain": "main", "n": 1,
         "cell_role": "TOP", "species": "qr", "op_id": "QR_FALK", "stage": "op",
         "field": "f"}
    with pytest.raises(gd.G33Corruption, match="op_seq_id"):
        w.record(r, "f32", [1], gd.pack_payload("f32", [1]))


def test_payload_size_mismatch_writer(tmp_path):
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 0, "op_seq_id": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
         "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    with pytest.raises(gd.G33Corruption, match="payload size"):
        w.record(r, "f32", [4], gd.pack_payload("f32", [1, 2]))  # shape 4 but 2 elems


def test_finalize_no_clobber(tmp_path):
    # a completed container appearing concurrently (after the constructor's
    # no-overwrite check) must NOT be destroyed by finalize().
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 0, "op_seq_id": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
         "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    w.record(r, "f32", [1], gd.pack_payload("f32", [1]))
    p.write_bytes(b"OTHER-COMPLETED-CONTAINER")   # concurrent completed output
    with pytest.raises(gd.G33Corruption, match="clobber"):
        w.finalize()
    assert p.read_bytes() == b"OTHER-COMPLETED-CONTAINER"   # preserved, not deleted
    assert (tmp_path / "c.g33.tmp").exists()                # our .tmp kept for inspection


def test_no_footer_without_finalize(tmp_path):
    p = tmp_path / "c.g33"
    with gd.G33Writer(p, _header()) as w:
        r = {"seq_no": 0, "op_seq_id": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
             "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
        w.record(r, "f32", [1], gd.pack_payload("f32", [1]))
        # leave the context WITHOUT finalize() -> no COMPLETE container appears
    assert not p.exists()             # only .tmp abandoned
    assert (tmp_path / "c.g33.tmp").exists()


# ── provenance attestation (§7d) ──────────────────────────────────────────────
def test_attestation_agrees(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    out = gd.read_container(p)
    att = {"producer_commit": "deadbeef", "binary_sha256": "0" * 64,
           "case_id": SCHED["case_id"], "pair_id": SCHED["pair_id"],
           "backend": SCHED["backend"], "algorithm": SCHED["algorithm"],
           "run_uuid": "uuid-1"}
    gd.verify_attestation(out["header"], att)  # no raise


def test_attestation_drift(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    out = gd.read_container(p)
    att = {"producer_commit": "OTHER", "binary_sha256": "0" * 64,
           "case_id": SCHED["case_id"], "pair_id": SCHED["pair_id"],
           "backend": SCHED["backend"], "algorithm": SCHED["algorithm"],
           "run_uuid": "uuid-1"}
    with pytest.raises(gd.G33Corruption, match="provenance drift"):
        gd.verify_attestation(out["header"], att)


# ── completeness vs INDEPENDENT expectation (§7b) ─────────────────────────────
def test_missing_record_detected(tmp_path):
    recs = ge.expected_records(SCHED)
    dropped = recs[:-3]                                  # writer silently drops 3
    for i, r in enumerate(dropped):
        r["seq_no"] = i
    p = tmp_path / "c.g33"; _write_valid(p, dropped)
    observed = {ge.record_key(r) for r in gd.read_container(p)["records"]}
    assert observed != ge.expected_key_set(SCHED)        # comparator would FAIL
    assert ge.expected_key_set(SCHED) - observed         # exactly the missing keys


def test_extra_record_detected(tmp_path):
    recs = ge.expected_records(SCHED)
    extra = dict(recs[0]); extra["field"] = "bogus_extra"
    extra["seq_no"] = len(recs); extra["op_seq_id"] = recs[-1]["op_seq_id"] + 1
    recs2 = recs + [extra]
    p = tmp_path / "c.g33"; _write_valid(p, recs2)
    observed = {ge.record_key(r) for r in gd.read_container(p)["records"]}
    assert observed - ge.expected_key_set(SCHED) == {ge.record_key(extra)}


def test_conditional_ice_reslope_schedule():
    # ice re-slope emitted only for n < mstepmax_ice; main for every n.
    recs = ge.expected_records(SCHED)                   # use NAMED fields, not tuple positions
    # first scope is qr/nr (main chain only): the ice chain transports qi/ni and
    # so must contribute NO records at all — its substep_pre/reslope fields are
    # chain-specific (work1_qi), and demanding the qr ones would be unsatisfiable.
    assert [r for r in recs if r["chain"] == "ice"] == []
    main_reslope_n = {r["n"] for r in recs if r["chain"] == "main" and r["stage"] == "reslope_output"}
    assert main_reslope_n == {1}                         # mstepmax_main=1 -> n=1 (every main n)
    # the conditional itself (ice re-slope only when n < mstepmax_ice) stays
    # implemented for when ice enters scope — exercised via the emission rule.
    assert ge._CHAIN_SPECIES["ice"] == ["qi", "ni"]


def test_cell_role_templates():
    # legacy TOP mass has NO outflow and NO inflow (the positivity clamp IS the
    # update); conservative TOP caps first. Neither TOP has an inflow rung.
    assert "QR_OUTFLOW" not in ge._mass_ops("legacy", "TOP")
    assert "QR_OUTFLOW" in ge._mass_ops("conservative", "TOP")
    for algo in ("legacy", "conservative"):
        assert "QR_INFLOW" not in ge._mass_ops(algo, "TOP")
        assert "NR_INFLOW" not in ge._number_ops(algo, "TOP")
        assert "QR_INFLOW" in ge._mass_ops(algo, "INTERIOR")
        assert "NR_INFLOW" in ge._number_ops(algo, "INTERIOR")
    # every op list ends at the update, and FALK is always first (the shared op)
    for algo in ("legacy", "conservative"):
        for role in ("TOP", "INTERIOR"):
            assert ge._mass_ops(algo, role)[0] == "QR_FALK"
            assert ge._mass_ops(algo, role)[-1] == "QR_UPDATE"
            assert ge._number_ops(algo, role)[0] == "NR_FALK"
            assert ge._number_ops(algo, role)[-1] == "NR_UPDATE"


def test_capped_ops_expose_pre_cap_rung():
    # P1-9: an op whose result passes through min() MUST expose the value that
    # ENTERS the min (…_pre_cap), the reservoir it is capped against, and the
    # cap flag — otherwise an incomplete dump matches the manifest and the first
    # diverging rung cannot be identified.
    for algo in ("legacy", "conservative"):
        for op, final in (("QR_OUTFLOW", "dq_out"), ("NR_OUTFLOW", "dn_out")):
            f = dict(ge._op_fields(algo, "INTERIOR", op))
            assert "outflow_pre_cap" in f, (algo, op)
            assert "source_reservoir" in f and "cap_active" in f and final in f, (algo, op)
    # legacy inflow is capped; conservative inflow is NOT (no min) — so the cap
    # fields must be present for legacy and absent for conservative.
    for op in ("QR_INFLOW", "NR_INFLOW"):
        leg = dict(ge._op_fields("legacy", "INTERIOR", op))
        assert "inflow_pre_cap" in leg and "inflow_cap_active" in leg and "source_reservoir" in leg, op
        con = dict(ge._op_fields("conservative", "INTERIOR", op))
        assert "inflow_cap_active" not in con and "inflow_pre_cap" not in con, op


def test_ice_chain_never_demands_qr_nr_ops():
    # ice_substep_advection_* transports ONLY qi/ni. Demanding QR_*/NR_* there
    # would require records the writer can never emit, making the completeness
    # check permanently unsatisfiable (and therefore useless).
    recs = ge.expected_records(SCHED)
    ice_ops = {(r["species"], r["op_id"]) for r in recs if r["chain"] == "ice" and r["stage"] == "op"}
    assert ice_ops == set(), f"ice chain must emit no qr/nr ops, got {ice_ops}"
    main_ops = {r["species"] for r in recs if r["chain"] == "main" and r["stage"] == "op"}
    assert main_ops == {"qr", "nr"}
    # widening scope to a species with no op template must fail LOUDLY
    with pytest.raises(NotImplementedError):
        ge._ops_for_species("legacy", "INTERIOR", "qs")


def test_bad_species_scope_fails_loudly_instead_of_disabling_the_op_check():
    # A misspelled or empty scope must NOT silently produce a manifest with no op
    # records (under which an empty dump would read as "complete").
    for bad in ([], ["QR"], ["qr ", "nr"], ["rain"]):
        with pytest.raises(ValueError):
            ge.expected_records({**SCHED, "species_scope": bad})
    # a degenerate schedule (no substeps) must also be refused, not accepted.
    # Schedule validation now rejects mstepmax<1 up front, so the vacuous-manifest
    # guard is never reached from here — assert the refusal, not which layer made it.
    with pytest.raises(ValueError, match="no op records|< 1"):
        ge.expected_records({**SCHED, "mstepmax_main": [0], "mstepmax_ice": [0]})
    # ... while a valid scope still yields a non-vacuous manifest
    assert any(r["stage"] == "op" for r in ge.expected_records(SCHED))


def test_duplicates_are_caught_by_multiset_not_by_set():
    recs = ge.expected_records(SCHED)
    surf = next(r for r in recs if r["stage"] == "surface")
    dup = dict(surf); dup["seq_no"] = len(recs)          # same KEY, different seq_no
    observed = recs + [dup]
    # a SET comparison is blind to this duplicate ...
    assert {ge.record_key(r) for r in observed} == ge.expected_key_set(SCHED)
    # ... the multiset comparison catches it
    d = ge.completeness_diff(observed, SCHED)
    assert d["duplicated"] == {ge.record_key(surf): 1}
    assert not d["missing"] and not d["extra"]


def test_completeness_diff_clean_and_missing():
    recs = ge.expected_records(SCHED)
    d = ge.completeness_diff(recs, SCHED)
    assert not d["missing"] and not d["extra"] and not d["duplicated"]
    d2 = ge.completeness_diff(recs[:-2], SCHED)
    assert sum(d2["missing"].values()) == 2 and not d2["extra"]


def test_number_ops_mirror_the_mass_algorithm_split():
    # conservative TOP computes dn_out = min(falk_nr*dtcld, nr): omitting NR_OUTFLOW
    # would let a dump that skips that cap match the manifest.
    assert "NR_OUTFLOW" in ge._number_ops("conservative", "TOP")
    assert "NR_OUTFLOW" not in ge._number_ops("legacy", "TOP")   # legacy TOP clamps directly
    assert "QR_OUTFLOW" in ge._mass_ops("conservative", "TOP")
    assert "QR_OUTFLOW" not in ge._mass_ops("legacy", "TOP")
    for algo in ("legacy", "conservative"):                      # interior: both have outflow
        assert "NR_OUTFLOW" in ge._number_ops(algo, "INTERIOR")
        assert "QR_OUTFLOW" in ge._mass_ops(algo, "INTERIOR")


def test_fall_accumulator_and_surface_are_required():
    # §4: without these the qr-seed -> rain_increment link is only cell-set
    # inclusion, and a dump omitting them would pass.
    for algo in ("legacy", "conservative"):
        for role in ("TOP", "INTERIOR"):
            assert "QR_FALLACC" in ge._mass_ops(algo, role), (algo, role)
            assert "NR_FALLACC" in ge._number_ops(algo, role), (algo, role)
        # conservative accumulates the ACTUAL capped outflow RATE, legacy the raw falk
        con = [f for f, _ in ge._op_fields("conservative", "INTERIOR", "QR_FALLACC")]
        leg = [f for f, _ in ge._op_fields("legacy", "INTERIOR", "QR_FALLACC")]
        assert "dq_out" in con and "mul_dend_safe" in con
        assert "dq_out" not in leg
        for x in ("fall_before", "fall_increment", "fall_after"):
            assert x in con and x in leg
    recs = ge.expected_records(SCHED)
    surf = {r["field"] for r in recs if r["stage"] == "surface"}
    # per-species since the surface-causal-path review: the aggregate alone
    # cannot attribute a qr seed (test_surface_expectation_is_per_species)
    assert {"bottom_fall_qr", "bottom_fall_total", "delz_bottom", "surface_mul1",
            "surface_mul_dt", "rain_increment"} <= surf
    # exactly once per outer loop
    assert len({r["outer_loop"] for r in recs if r["stage"] == "surface"}) == SCHED["loops"]


def test_inflow_ladders_match_the_source_expressions():
    # every arithmetic rung of the ACTUAL expression must be a separate record.
    leg_qr = [f for f, _ in ge._op_fields("legacy", "INTERIOR", "QR_INFLOW")]
    for rung in ("stored_falk_prev", "delz_raw_src", "delz_safe_dst", "dend_safe_dst",
                 "mul_delz_src", "div_delz_dst", "mul_dt", "inflow_pre_cap", "inflow_final"):
        assert rung in leg_qr, rung
    con_qr = [f for f, _ in ge._op_fields("conservative", "INTERIOR", "QR_INFLOW")]
    for rung in ("prev_out", "src_metric", "dst_metric", "mul_src", "inflow_final"):
        assert rung in con_qr, rung          # mul_src = the pre-division intermediate
    # raw vs safe are distinct records (the conservative metric mixes them:
    # src uses delz_RAW, dst uses delz_SAFE)
    assert "delz_raw_src" in con_qr and "delz_safe_dst" in con_qr
    # number chains differ from mass: conservative NR_INFLOW has no dtcld rung
    con_nr = [f for f, _ in ge._op_fields("conservative", "INTERIOR", "NR_INFLOW")]
    assert "mul_dt" not in con_nr and "mul_delz_src" in con_nr
    # and NR_OUTFLOW has no /dend rung (mass does)
    assert "mul_dt" in [f for f, _ in ge._op_fields("legacy", "INTERIOR", "QR_OUTFLOW")]
    assert "mul_dt" not in [f for f, _ in ge._op_fields("legacy", "INTERIOR", "NR_OUTFLOW")]


def test_duplicate_json_key_rejected(tmp_path):
    # json.loads keeps the LAST duplicate key, so an unescaped value that injects
    # e.g. "producer_commit" would silently override the ATTESTED one.
    p = tmp_path / "c.g33"; _write_valid(p)
    b = p.read_bytes()
    hlen = struct.unpack_from("<I", b, 12)[0]
    hdr = b[16:16 + hlen].decode()
    forged = hdr[:-1] + ',"producer_commit":"FORGED"}'
    nb = b[:12] + struct.pack("<I", len(forged)) + forged.encode() + b[16 + hlen:]
    p.write_bytes(nb)
    with pytest.raises(gd.G33Corruption, match="duplicate JSON key"):
        gd.read_container(p)


def test_header_schema_validated(tmp_path):
    for bad in ({"B": "3"}, {"column_index_map": [[0, 0, 0, 0]]}, {"run_uuid": 5}):
        p = tmp_path / f"c{abs(hash(str(bad)))}.g33"
        _write_valid(p)
        b = p.read_bytes()
        hlen = struct.unpack_from("<I", b, 12)[0]
        hdr = json.loads(b[16:16 + hlen])
        hdr.update(bad)
        nh = json.dumps(hdr).encode()
        p.write_bytes(b[:12] + struct.pack("<I", len(nh)) + nh + b[16 + hlen:])
        with pytest.raises(gd.G33Corruption):
            gd.read_container(p)
    # a header missing a required field entirely
    p2 = tmp_path / "miss.g33"; _write_valid(p2)
    b = p2.read_bytes(); hlen = struct.unpack_from("<I", b, 12)[0]
    hdr = json.loads(b[16:16 + hlen]); hdr.pop("canonical_k_order")
    nh = json.dumps(hdr).encode()
    p2.write_bytes(b[:12] + struct.pack("<I", len(nh)) + nh + b[16 + hlen:])
    with pytest.raises(gd.G33Corruption, match="missing required field"):
        gd.read_container(p2)


def test_post_close_verify_refuses_to_publish_a_corrupt_tmp(tmp_path):
    # protocol 7a: .tmp -> flush/close -> VERIFY -> rename. A short write (disk
    # full) must keep the .tmp and never reach the final path.
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 0, "op_seq_id": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
         "k": 0, "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    w.record(r, "f32", [1], gd.pack_payload("f32", [1]))
    # simulate the tail of the file being lost between close and publish
    orig_close = w._f.close
    def truncating_close():
        orig_close()
        d = w.tmp.read_bytes(); w.tmp.write_bytes(d[: len(d) // 2])
    w._f.close = truncating_close
    with pytest.raises(gd.G33Corruption, match="post-close verification failed"):
        w.finalize()
    assert not p.exists()                       # never published
    assert w.tmp.exists()                       # evidence kept


def test_attestation_pins_run_uuid(tmp_path):
    # without run_uuid a container from a PREVIOUS run (same commit/binary/case)
    # would pass as this run's evidence.
    p = tmp_path / "c.g33"; _write_valid(p)
    out = gd.read_container(p)
    att = {"producer_commit": "deadbeef", "binary_sha256": "0" * 64,
           "case_id": SCHED["case_id"], "pair_id": SCHED["pair_id"],
           "backend": SCHED["backend"], "algorithm": SCHED["algorithm"],
           "run_uuid": "a-DIFFERENT-run"}
    with pytest.raises(gd.G33Corruption, match="run_uuid"):
        gd.verify_attestation(out["header"], att)


def test_canonical_k_is_part_of_the_record_identity():
    # Before `k` joined the identity, cell_role alone (TOP/INTERIOR/BOTTOM) made
    # every interior level collide: for K>=4 a dump could emit k=1 twice, never
    # touch k=2, and still read as complete.
    recs = ge.expected_records(SCHED)
    interior = [r for r in recs if r["cell_role"] == "INTERIOR" and r["stage"] == "op"]
    assert len({r["k"] for r in interior}) > 1, "test schedule must have >1 interior level"
    a = next(r for r in interior if r["k"] == 1)
    b = next(r for r in interior if r["k"] == 2 and r["field"] == a["field"]
             and r["op_id"] == a["op_id"] and r["species"] == a["species"])
    assert ge.record_key(a) != ge.record_key(b), "interior levels must not collide"
    # and the manifest as a whole must have NO repeated key
    from collections import Counter
    dupes = {k: v for k, v in Counter(ge.record_key(r) for r in recs).items() if v > 1}
    assert dupes == {}, f"non-unique expected keys: {list(dupes)[:2]}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_pack_payload_is_byte_identical_to_the_bitwise_roundtrip():
    # `>f`/`>d` replaced a pack-LE -> unpack-int -> pack-BE roundtrip. Both emit
    # the big-endian IEEE-754 bit pattern; pin that across the awkward values.
    import math
    probes = [0.0, -0.0, 1.0, -3.25, 1e-30, 1e30, float("inf"), float("-inf"),
              float("nan"), 5e-324, 1.5e-45, 3.4028235e38, math.pi,
              -2.2250738585072014e-308]
    for v_ in probes:
        assert gd.pack_payload("f32", [v_]) == struct.pack(
            ">I", struct.unpack("<I", struct.pack("<f", float(v_)))[0])
        assert gd.pack_payload("f64", [v_]) == struct.pack(
            ">Q", struct.unpack("<Q", struct.pack("<d", float(v_)))[0])


# ── schema v2: owner review #4 P0-1..P0-4 ─────────────────────────────────────
def test_process_id_must_be_an_integer(tmp_path):
    # P0-1. The C++ overlay emits process_id as a JSON NUMBER (getpid()). A reader
    # requiring str made every container from the REAL overlay unreadable, so the
    # whole pipeline was only ever exercised against Python-written fixtures.
    gd.G33Writer(tmp_path / "ok.g33", _header(process_id=4242))          # accepted
    for bad in ("4242", True, -1, 1.5, None):
        with pytest.raises(gd.G33Corruption, match="process_id"):
            gd.G33Writer(tmp_path / f"bad{hash(str(bad))}.g33", _header(process_id=bad))


def test_cpp_and_python_format_versions_agree():
    # Two writers in two languages drift silently. Pin the C++ constant from the
    # test suite so the drift fails here, not in the middle of a host campaign.
    src = (ROOT / "g33_overlay" / "g33_op_dump.h").read_text()
    m = re.search(r"put_u32\((\d+)\);\s*//\s*format_version", src)
    assert m, "format_version emission not found in the C++ writer"
    assert int(m.group(1)) == gd.FORMAT_VERSION


def test_malformed_column_maps_are_refused(tmp_path):
    B = SCHED["B"]
    good = [[i, 0, i, i] for i in range(B)]
    bad_maps = [
        [[0, 0, 0, 0]],                                  # short: not all B columns
        good + [[B, 0, B, B]],                           # long: B_index out of range
        [[0, 0, 0, 0], [0, 0, 1, 1], [2, 0, 2, 2]],      # duplicate B_index
        [[0, 0, 0, 0], [1, 0, 1, 0], [2, 0, 2, 2]],      # duplicate cpp_flat_index
        [[0, 0, 0, 0], [1, 0, 0, 1], [2, 0, 2, 2]],      # duplicate Fortran (i,j)
        [[0, 0, 0], [1, 0, 1], [2, 0, 2]],               # wrong arity
    ]
    for cmap in bad_maps:
        with pytest.raises(gd.G33Corruption):
            gd.G33Writer(tmp_path / "m.g33", _header(column_index_map=cmap))


def test_raw_bit_roundtrip_preserves_nan_payloads(tmp_path):
    # pack_payload goes through Python floats, which canonicalize NaN payloads —
    # a signalling NaN or a distinct mantissa would silently become the quiet
    # default, erasing exactly the bit pattern a divergence hunt is looking for.
    f32_bits = [0x7F800001, 0xFFC00000, 0x7FC0DEAD, 0x80000000]
    f64_bits = [0x7FF0000000000001, 0xFFF8000000000000, 0x7FF8DEADBEEFCAFE]
    p = tmp_path / "nan.g33"
    w = gd.G33Writer(p, _header(record_count_expected=2, global_op_seq_end=1))
    base = {"outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP", "k": 0,
            "species": "qr", "op_id": "QR_FALK", "stage": "op"}
    w.record({**base, "seq_no": 0, "op_seq_id": 0, "field": "a"},
             "f32", [len(f32_bits)], gd.pack_payload_bits("f32", f32_bits))
    w.record({**base, "seq_no": 1, "op_seq_id": 1, "field": "b"},
             "f64", [len(f64_bits)], gd.pack_payload_bits("f64", f64_bits))
    w.finalize()
    recs = gd.read_container(p)["records"]
    assert gd.unpack_payload_bits("f32", recs[0]["payload"]) == f32_bits
    assert gd.unpack_payload_bits("f64", recs[1]["payload"]) == f64_bits


def test_run_index_tiles_the_op_seq_space_exactly():
    ix = ge.run_index(SCHED)
    assert sum(c["record_count"] for c in ix["containers"]) == ix["total_records"]
    cursor = 0
    for c in ix["containers"]:
        assert c["first_op_seq_id"] == cursor            # no gap, no overlap
        assert c["last_op_seq_id"] - c["first_op_seq_id"] + 1 == c["record_count"]
        cursor = c["last_op_seq_id"] + 1
    assert cursor == ix["total_records"]
    assert len({c["container_id"] for c in ix["containers"]}) == len(ix["containers"])


def test_op_seq_map_matches_the_run_index():
    # The env string the overlay consumes must be the run_index verbatim; if it
    # can drift, the "declared before the run" property is decorative.
    ix = ge.run_index(SCHED)
    parsed = [t.split(":") for t in ge.op_seq_map(ix).split(",")]
    assert [(c["container_id"], str(c["first_op_seq_id"]), str(c["last_op_seq_id"]))
            for c in ix["containers"]] == [tuple(t) for t in parsed]


# ── instrumented scope: the declared window must match the MEASURED counter ────
def test_overlay_stage_scope_matches_the_source():
    # CPP_OVERLAY_STAGES is a claim about the overlay. If the overlay starts
    # emitting a stage the declaration omits (or stops emitting one it names),
    # every declared op_seq window shifts off the measured counter and the real
    # overlay silently stops being able to produce a valid container.
    src = (ROOT / "g33_overlay" / "sedimentation.cpp.overlay").read_text()
    emitted = set(re.findall(r'G33_REC\(g33,\s*"([a-z_]+)"', src))
    assert emitted == set(ge.CPP_OVERLAY_STAGES), (
        f"overlay emits {sorted(emitted)} but the harness declares "
        f"{sorted(ge.CPP_OVERLAY_STAGES)}")


def test_declared_windows_accept_a_real_overlay_emission_order(tmp_path):
    # End-to-end shape of an actual run: one container per substep, records
    # numbered by a single process-global counter that starts at 0 and only
    # counts INSTRUMENTED records. Before instrumented_stages existed, the index
    # numbered over uninstrumented outer stages too, so the first real record
    # measured 0 against a window of [6, N] and every run failed at record one.
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    index = ge.run_index(sched)
    recs = ge.expected_records(sched)
    by_container: dict = {}
    for r in recs:
        by_container.setdefault(ge.container_id(r), []).append(r)

    op_seq = 0                                    # the overlay's global counter
    for c in index["containers"]:
        rs = by_container[c["container_id"]]
        w = gd.G33Writer(
            tmp_path / f"{c['container_id']}.g33",
            _header(container_id=c["container_id"],
                    global_op_seq_start=c["first_op_seq_id"],
                    global_op_seq_end=c["last_op_seq_id"],
                    record_count_expected=len(rs)))
        for i, r in enumerate(rs):
            n_elem = 1
            for d in r["shape"]:
                n_elem *= d
            w.record({**r, "seq_no": i, "op_seq_id": op_seq}, r["dtype"], r["shape"],
                     gd.pack_payload(r["dtype"], [1] * n_elem))
            op_seq += 1                            # measured, never reset
        w.finalize()
        assert op_seq == c["last_op_seq_id"] + 1   # measured meets the declaration
    assert op_seq == index["total_records"]


def test_instrumented_scope_must_be_declared_not_defaulted():
    with pytest.raises(ValueError, match="instrumented_stages"):
        ge.expected_records({k: v for k, v in SCHED.items()
                             if k != "instrumented_stages"})
    for bad in ([], (), "op", ["outer_pre_sed_typo"]):
        with pytest.raises(ValueError, match="instrumented_stages"):
            ge.expected_records({**SCHED, "instrumented_stages": bad})


# Roots the substep_pre block may read, and the rank each carries. Explicit
# rather than inferred: a substring rule ("expression mentions col") only caught
# slices spelled through the *_col lambdas and passed `in.dend.select(-1, k)` —
# a real [B] slice — as whole-K. An unknown root fails loudly instead of being
# guessed, so a future field cannot quietly opt out of the shape check.
_WHOLE_K_ROOTS = {"in.state.qr": "f32", "in.state.nr": "f32",
                  "in.work1_qr": "f64", "in.workn_qr": "f64",
                  "in.dend": "f32", "dend_safe": "f32",
                  "in.delz": "f32", "delz_safe": "f32"}
_PER_COLUMN_ROOTS = {"mstep_col_safe": "f64", "gate_col": "f32"}   # cpp native widths
_TORCH_DTYPE = {"kFloat": "f32", "kFloat32": "f32", "kFloat64": "f64",
                "kDouble": "f64", "kInt32": "i32", "kInt": "i32", "kUInt8": "u8"}
# torch:: tokens that are NOT dtypes. .to() takes device/layout/memory-format
# arguments too, so these must be recognised as "does not change the dtype"
# rather than lumped in with the dtype names or treated as unknown.
_TORCH_NON_DTYPE = {"kCPU", "kCUDA", "kStrided", "kSparse", "kContiguousMemoryFormat"}


def _decomment(expr: str) -> str:
    """Blank C++ comments before any parsing.

    The paren matcher counted comment text as syntax in BOTH directions:
    `.to(/*)*/ torch::kFloat64)` closed on the ')' inside the comment, hiding the
    cast so the dtype fell through to the root's f32; and a comment merely
    MENTIONING `.to(torch::kFloat64)` was parsed as a real cast, failing valid
    code. Reuses verify_overlay's lexer rather than adding a second comment
    parser to get wrong independently.
    """
    sys.path.insert(0, str(ROOT / "g33_overlay"))
    from verify_overlay import _clean_lines
    return "\n".join(_clean_lines(expr.split("\n")))


def _to_call_args(expr: str):
    """Argument text of each `.to(...)` call, paren-matched.

    A regex for `.to(torch::kX)` silently does not match a MULTI-ARGUMENT call —
    `.to(torch::kFloat64, torch::kStrided)` — so the cast was invisible and the
    dtype fell through to the root's: an f64 relabel of an f32 tensor certified
    as f32, in the gate whose purpose is to catch precision relabels.
    """
    expr = _decomment(expr)
    args = []
    for m in re.finditer(r"\.\s*to\s*\(", expr):
        depth, i = 1, m.end()
        while i < len(expr) and depth:
            depth += (expr[i] == "(") - (expr[i] == ")")
            i += 1
        if depth:
            raise AssertionError(f"unbalanced .to( in {expr.strip()!r}")
        args.append(expr[m.end():i - 1])
    return args
# Methods that provably preserve rank. CLOSED WORLD: anything not named here is
# treated as rank-unknown and refused.
#
# Two rounds of this check enumerated the rank-CHANGING forms instead —
# .select/.narrow/.squeeze/_col(/[k] — and each round missed the next spelling:
# .sum(-1), .reshape, .flatten, .transpose and torch::stack all passed as
# whole-K. A deny-list of ways to change a tensor's rank cannot be completed;
# the set of ways to PRESERVE it is small and closable.
_RANK_PRESERVING = {"to", "round", "abs", "logical_or", "logical_and",
                    "logical_not", "clone", "detach", "contiguous"}


def _strip_roots(expr: str):
    """Remove known tensor roots, returning (residue, roots_found).

    Matching is word-bounded, not substring: `in.dend` must not match `in.dend2`,
    a DIFFERENT tensor that would otherwise inherit in.dend's certified rank and
    dtype. Longest-first so `in.work1_qr` is not consumed piecewise.
    """
    found = set()
    for root in sorted(set(_WHOLE_K_ROOTS) | set(_PER_COLUMN_ROOTS),
                       key=len, reverse=True):
        pat = r"(?<![\w.])" + re.escape(root) + r"(?![\w])"
        if re.search(pat, expr):
            found.add(root)
            expr = re.sub(pat, " ", expr)
    return expr, found


def _emits_per_column(field: str, expr: str) -> bool:
    # CERTIFY THE WHOLE EXPRESSION. Inspecting only the recognised parts is
    # fail-open: `in.dend * mystery_tensor` certified as whole-K f32 on the
    # strength of in.dend alone, and `in.dend2` inherited in.dend's certificate
    # by substring. Every token must now be accounted for or the check refuses.
    # Decomment ONCE, at entry, and use that everywhere below. Routing only the
    # residue through _decomment left the bracket and call checks reading raw
    # text, so a comment MENTIONING `.sum(` or `[k]` was parsed as the real
    # thing and correct code was refused — the same defect as the eighth
    # finding, surviving in the two checks that were not converted.
    expr = _decomment(expr)
    residue, roots = _strip_roots(expr)
    # Strip by ROLE, not by name. Subtracting the allowed NAMES from the token
    # set let an unknown OPERAND that happens to be spelled like one through:
    # `in.dend * abs` and `in.dend * kFloat64` both certified clean, because
    # `abs` and `kFloat64` were on the allowed list no matter where they stood.
    residue = re.sub(r"torch\s*::\s*k\w+", " ", residue)          # dtype token
    residue = re.sub(r"[.:]+\s*(?:%s)\s*\(" % "|".join(sorted(_RANK_PRESERVING)),
                     " ", residue)                                 # method call
    leftover = set(re.findall(r"[A-Za-z_]\w*", residue))
    if leftover:
        raise AssertionError(
            f"{field}: unaccounted identifier(s) {sorted(leftover)} in "
            f"{expr.strip()!r} — the shape/dtype certificate would rest on the "
            f"recognised parts only")
    if not roots:
        raise AssertionError(
            f"{field}: no known tensor root in {expr.strip()!r} — add it to "
            f"_WHOLE_K_ROOTS or _PER_COLUMN_ROOTS rather than letting the shape "
            f"check silently pass")
    # Bracket indexing carries no method call, so a call-based rule alone reads
    # `in.dend[k]` — a real [B] slice — as whole-K.
    if re.search(r"\]\s*\[|\w\s*\[", expr):
        return True
    calls = set(re.findall(r"[.:]\s*([A-Za-z_]\w*)\s*\(", expr))
    unknown = calls - _RANK_PRESERVING - {"torch"} - set(_TORCH_DTYPE)
    if unknown:
        raise AssertionError(
            f"{field}: {sorted(unknown)} is not known to preserve rank, so the "
            f"emitted shape cannot be certified from the source. Add it to "
            f"_RANK_PRESERVING only if it provably keeps the tensor's rank.")
    if roots <= set(_PER_COLUMN_ROOTS):
        return True
    if roots <= set(_WHOLE_K_ROOTS):
        return False
    raise AssertionError(f"{field}: mixes whole-K and per-column roots: {sorted(roots)}")


def _emits_dtype(field: str, expr: str) -> str:
    """The dtype the overlay actually emits, from the same closed world.

    Nothing checked this. `.to(torch::kFloat64)` on an f32 root kept the shape
    correct and relabelled the value's precision — the "precision-PROVENANCE
    lie" the overlay's own rec() comment warns about, in the one place the whole
    gate exists to detect.
    """
    expr = _decomment(expr)
    dtype = None
    for arg in _to_call_args(expr):
        toks = re.findall(r"\bk\w+", arg)
        unknown = [t for t in toks if t not in _TORCH_DTYPE and t not in _TORCH_NON_DTYPE]
        if unknown:
            raise AssertionError(f"{field}: unmapped torch token(s) {unknown}")
        dts = {_TORCH_DTYPE[t] for t in toks if t in _TORCH_DTYPE}
        if len(dts) > 1:
            raise AssertionError(f"{field}: ambiguous .to({arg.strip()}) -> {sorted(dts)}")
        if dts:
            dtype = dts.pop()          # a device/layout-only .to() leaves it alone
    if dtype is not None:
        return dtype
    if re.search(r"==|!=|<=|>=|logical_", expr):
        raise AssertionError(
            f"{field}: comparison/logical result is bool, which is not a manifest "
            f"dtype — emit an explicit .to(torch::kUInt8)")
    _, roots = _strip_roots(expr)
    dts = {(_WHOLE_K_ROOTS | _PER_COLUMN_ROOTS)[r] for r in roots}
    if len(dts) != 1:
        raise AssertionError(f"{field}: cannot certify dtype from roots {sorted(dts)}")
    return dts.pop()


def test_overlay_substep_pre_emission_matches_the_manifest():
    """The manifest must be satisfiable by what the overlay ACTUALLY emits.

    test_declared_windows_accept_a_real_overlay_emission_order replays the
    manifest's own records, so it validates the manifest against itself and
    passes no matter what the overlay does. It did: at that point the overlay
    emitted substep_pre as 12 per-level (B,) slices hardcoded to k=0 inside the
    top-cell block, while the manifest expected 20 whole-K fields at k=-1 — a
    real container could not satisfy it on identity, shape, count, or field set.

    This reads the emission sequence out of the overlay source instead.
    """
    src = (ROOT / "g33_overlay" / "sedimentation.cpp.overlay").read_text()
    emitted = re.findall(
        r'G33_REC\(g33,\s*"substep_pre",\s*"(-|[A-Z]+)",\s*(-?\d+),'
        r'\s*[^,]+,\s*[^,]+,\s*"([a-z0-9_]+)",\s*([^;]+)\);', src)
    assert emitted, "no substep_pre emission found in the overlay"

    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    expected = [r for r in ge.expected_records(sched) if r["stage"] == "substep_pre"
                and r["chain"] == "main" and r["n"] == 1 and r["outer_loop"] == 1]

    assert [f for _, _, f, _ in emitted] == [r["field"] for r in expected], (
        "overlay substep_pre field ORDER/SET differs from the manifest")
    assert {int(k) for _, k, _, _ in emitted} == {-1}, (
        "substep_pre is a whole-K record: k must be -1, not a per-level index")
    for (_, _, field, expr), r in zip(emitted, expected):
        per_column = _emits_per_column(field, expr)
        assert per_column == (r["shape"] == [SCHED["B"]]), (
            f"{field}: overlay emits {'per-column' if per_column else 'whole-K'} "
            f"but the manifest expects shape {r['shape']}")
        assert _emits_dtype(field, expr) == r["dtype"], (
            f"{field}: overlay emits {_emits_dtype(field, expr)} but the manifest "
            f"declares {r['dtype']} — a dtype relabel is a precision-provenance lie")


# Expressions that must NEVER certify as "whole-K f32" — what dend_raw is.
# Enumerated independently of the certifier's rules, and grown every time the
# certifier was found fail-open: slicing spellings, rank-changing calls, dtype
# relabels, unknown operands, and operands SPELLED like allowed tokens. Kept in
# the repo because five consecutive rounds of ad-hoc falsification each declared
# the gate sound and each was wrong.
_MUST_NOT_CERTIFY = [
    "in.dend.select(-1, k)", "dend_col(k)", "in.dend[k]",
    "in.dend.narrow(-1,k,1).squeeze(-1)",
    "in.dend.index({torch::indexing::Slice(), 0})",
    "in.dend.sum(-1)", "in.dend.mean(-1)", "in.dend.max(-1).values",
    "in.dend.reshape({-1})", "in.dend.flatten()", "in.dend.unsqueeze(0)",
    "in.dend.transpose(0, 1)", "in.dend.permute({1,0})",
    "torch::stack({in.dend, in.dend}, 0)",
    "in.dend.to(torch::kFloat64)", "in.dend.to(torch::kUInt8)",
    # multi-argument .to(): a regex for `.to(torch::kX)` does not match these,
    # so the cast was invisible and the dtype fell through to the root's f32
    "in.dend.to(torch::kFloat64, torch::kStrided)",
    "in.dend.to(torch::kCPU, torch::kFloat64)",
    "in.dend.to(torch::kFloat64, /*non_blocking=*/false)",
    "in.dend.to(torch::kFloat64, torch::kUInt8)",
    "in.dend.to(torch::kBogus)",
    # comments counted as syntax: the ')' inside the comment closed the paren
    # match early and hid the cast, so the dtype fell through to the root's f32
    "in.dend.to(/*)*/ torch::kFloat64)",
    "in.dend.to(torch::kFloat64 /* ) */)",
    "in.work1_qr",
    "some_unknown_tensor", "in.dend2", "helper(in.dend)",
    "(in.dend * mystery_tensor)", "(mystery * in.dend)",
    "(in.dend * abs)", "(in.dend * clone)", "(in.dend + to)",
    "(in.dend * kFloat64)", "(in.dend * torch)", "(in.dend * round)",
    # comment-hidden slice: the bracket/call checks read RAW text until the
    # ninth finding, so comments were parsed as syntax in these two as well
    "in.dend/*x*/[k]", "in.dend/*x*/[0]",
]


@pytest.mark.parametrize("expr", _MUST_NOT_CERTIFY)
def test_certifier_refuses_expressions_that_are_not_whole_k_f32(expr):
    # dend_raw's contract: whole-K (not per-column) and f32.
    try:
        wrong = _emits_per_column("dend_raw", expr) or _emits_dtype("dend_raw", expr) != "f32"
    except AssertionError:
        return                     # refused to certify — the correct outcome
    assert wrong, f"certifier accepted {expr!r} as whole-K f32"


@pytest.mark.parametrize("expr", [
    "in.dend /* .to(torch::kFloat64) */",
    "in.dend  // .to(torch::kFloat64)",
    "in.dend /* dend_col(k) */",
])
def test_comments_do_not_make_valid_emissions_fail(expr):
    # The mirror of the corpus: a comment that merely MENTIONS a cast or a slice
    # was parsed as one, so correct code failed. A gate that fires on comments
    # gets disabled by whoever hits it, which is how a check stops protecting.
    assert _emits_per_column("dend_raw", expr) is False
    assert _emits_dtype("dend_raw", expr) == "f32"


def test_certifier_accepts_the_real_emissions():
    # The corpus above must not be so strict that the actual overlay fails: every
    # expression the overlay really emits has to certify to its manifest entry.
    src = (ROOT / "g33_overlay" / "sedimentation.cpp.overlay").read_text()
    emitted = re.findall(
        r'G33_REC\(g33,\s*"substep_pre",\s*"(?:-|[A-Z]+)",\s*-?\d+,'
        r'\s*[^,]+,\s*[^,]+,\s*"([a-z0-9_]+)",\s*([^;]+)\);', src)
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    expected = [r for r in ge.expected_records(sched) if r["stage"] == "substep_pre"
                and r["chain"] == "main" and r["n"] == 1 and r["outer_loop"] == 1]
    assert len(emitted) == len(expected)
    for (field, expr), r in zip(emitted, expected):
        assert _emits_per_column(field, expr) == (r["shape"] == [SCHED["B"]])
        assert _emits_dtype(field, expr) == r["dtype"]


# ── runtime expected-descriptor (owner adjudication: this REPLACES the static
#    expression certifier as load-bearing evidence; the certifier above is
#    retained as a tripwire only) ────────────────────────────────────────────
def test_descriptors_are_sealed_per_container(tmp_path):
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    shas = ge.write_descriptors(sched, tmp_path)
    index = ge.run_index(sched)
    assert set(shas) == {c["container_id"] for c in index["containers"]}
    for c in index["containers"]:
        lines = (tmp_path / f"{c['container_id']}.desc").read_text().splitlines()
        assert len(lines) == c["record_count"]
        first = int(lines[0].split("|")[0])
        last = int(lines[-1].split("|")[0])
        assert (first, last) == (c["first_op_seq_id"], c["last_op_seq_id"])


def test_descriptor_sha_detects_an_edit(tmp_path):
    # The overlay and the comparator both read these files. If a descriptor can
    # be changed between the run and the comparison without detection, the
    # "sealed before the run" property is decorative.
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    before = ge.write_descriptors(sched, tmp_path)
    cid = next(iter(before))
    p = tmp_path / f"{cid}.desc"
    lines = p.read_text().splitlines()
    lines[0] = lines[0].replace("|f32|", "|f64|")        # a dtype relabel
    p.write_bytes(("\n".join(lines) + "\n").encode())
    import hashlib
    assert hashlib.sha256(p.read_bytes()).hexdigest() != before[cid]


def test_cpp_builds_the_same_descriptor_line():
    # TRIPWIRE, not proof: the real check is that a run's rec() rejects a
    # mismatching tensor. This only pins the two field orders against each other
    # so a reorder on one side is caught before a host campaign, not during one.
    src = (ROOT / _TRACE).read_text()
    m = re.search(r'std::string got = ([^;]+);', src)
    assert m, "descriptor line construction not found in the overlay"
    order = re.findall(r"\b(op_seq_id|stage|cell_role|k|species|op_id|field|dtype)\b",
                       m.group(1))
    assert order == ["op_seq_id", "stage", "cell_role", "k", "species", "op_id",
                     "field", "dtype"]


def test_mstepmax_is_derived_from_the_dumped_bits():
    # Owner adjudication: mstepmax is max_b(mstep_b), so the comparator derives
    # it rather than the producer dumping it — no production edit, and no
    # producer attesting to a summary of its own operand.
    payload = gd.pack_payload("f64", [1.0, 3.0, 2.0])
    assert gd.derive_mstepmax("f64", payload) == 3
    nonintegral = gd.pack_payload_bits("f64", [0x4000000000000001])
    with pytest.raises(gd.G33Corruption, match="non-integral"):
        gd.derive_mstepmax("f64", nonintegral)


def test_container_records_which_descriptor_it_was_validated_against(tmp_path):
    # Reading a file called "sealed" proves nothing on its own. Without the
    # digest in the header, a descriptor edited between sealing and the run is
    # undetectable and the comparator cannot tell WHICH descriptor the producer
    # validated against — the "sealed before the run" property is decorative.
    for bad in ("", "zz" * 32, "a" * 63, "A" * 64, 12345):
        with pytest.raises(gd.G33Corruption):
            gd.G33Writer(tmp_path / f"d{abs(hash(str(bad)))}.g33",
                         _header(descriptor_sha256=bad))
    gd.G33Writer(tmp_path / "ok.g33", _header(descriptor_sha256="0" * 64))


def test_schema_dir_is_part_of_the_all_or_nothing_env_set():
    # KDM6_G33_SCHEMA_DIR was checked separately from the all-or-nothing block,
    # so a run configured with ONLY that variable counted as "nothing set" and
    # went inert instead of reporting a partial configuration. Every env ANY
    # instrumented file reads must be in the shared table.
    required = _overlay_required_env()
    for rel in (_TRACE, "g33_overlay/sedimentation.cpp.overlay"):
        src = (ROOT / rel).read_text()
        read = set(re.findall(r'std::getenv\("(KDM6_G33_\w+)"\)', src))
        assert read <= required, f"{rel} reads unrequired: {sorted(read - required)}"


def test_descriptor_load_precedes_header_construction():
    # TRIPWIRE: desc_sha_ is embedded in the header string, so computing it after
    # the header is built silently seals an EMPTY digest.
    src = (ROOT / _TRACE).read_text()
    assert src.index("desc_sha_ = dsha.hexdigest();") < src.index("std::string hdr =")


# ── the sealed digest must come from an INDEPENDENT channel ───────────────────
def _compile_probe(tmp_path, source_name):
    """Compile a C++ probe against the overlay's writer header.

    The overlay itself needs libtorch, so it cannot be built here; probes
    exercise the same bundled code paths (Sha256, dladdr resolution, csv lookup)
    in a standalone binary. Skipped when no compiler is available rather than
    passing.
    """
    import shutil, subprocess
    cxx = shutil.which("clang++") or shutil.which("g++")
    if not cxx:
        pytest.skip("no C++ compiler")
    exe = tmp_path / Path(source_name).stem
    cmd = [cxx, "-std=c++17", "-DKDM6_G33_OP_DUMP", f"-I{ROOT / 'g33_overlay'}",
           str(ROOT / "tests" / source_name), "-o", str(exe)]
    if sys.platform.startswith("linux"):
        cmd.append("-ldl")
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return exe


def _build_seal_probe(tmp_path):
    return _compile_probe(tmp_path, "seal_digest_probe.cpp")


def test_sealed_digest_rejects_an_edited_descriptor(tmp_path):
    # Before this, the producer hashed whatever file it read and reported that
    # digest — a self-attestation. Editing the descriptor produced a container
    # that agreed with itself and nothing failed.
    import os, subprocess
    exe = _build_seal_probe(tmp_path)
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    shas = ge.write_descriptors(sched, tmp_path)
    cid = next(iter(shas))
    desc = tmp_path / f"{cid}.desc"
    original = desc.read_bytes()
    env = {**os.environ, "KDM6_G33_SCHEMA_SHA256": ge.schema_sha_map(shas)}

    def rc():
        return subprocess.run([str(exe), str(desc), cid], env=env,
                              capture_output=True, text=True).returncode

    assert rc() == 0                                   # unmodified: accepted
    for edit in (original.replace(b"|f32|", b"|f64|", 1),          # dtype relabel
                 original[: original.rindex(b"\n", 0, -1) + 1],    # record dropped
                 original + b"999|op|-|0|qr|X|f|f32|3\n"):         # record added
        desc.write_bytes(edit)
        assert rc() == 1, "an edited descriptor was accepted"
    desc.write_bytes(original)
    assert rc() == 0

    # and a container with no sealed digest at all must not proceed
    env.pop("KDM6_G33_SCHEMA_SHA256")
    assert subprocess.run([str(exe), str(desc), cid], env=env,
                          capture_output=True, text=True).returncode == 2


# ── the environment the overlay requires must actually be produced ────────────
def _clean_repo(tmp_path):
    """A committed, clean checkout for env-building tests.

    These must not read the real repository: build_env refuses a dirty tree, so
    using it would make the tests pass or fail based on whether the developer
    happens to have uncommitted work.
    """
    import subprocess
    repo = tmp_path / "repo"
    (repo / "libtorch" / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "libtorch" / "src" / "a.cpp").write_text("int a;\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "base"], check=True)
    return repo


# The trace machinery moved to the SHARED header (three instrumented TUs, one
# implementation — private copies drift); source pins follow it there.
_TRACE = "g33_overlay/g33_op_trace.h"


def _overlay_required_env():
    src = (ROOT / _TRACE).read_text()
    block = re.search(r"kRequiredEnv\[\]\s*=\s*\{(.*?)\}", src, re.S)
    assert block, "required-env table not found"
    return set(re.findall(r'"(KDM6_G33_\w+)"', block.group(1)))


def test_run_env_supplies_exactly_what_the_overlay_requires(tmp_path):
    # Each tightening of the producer added another required variable and
    # nothing produced them: the documented invocation named three while the
    # overlay required eleven, so a diagnostic run could not start. Pinning
    # producer against consumer is what keeps that from recurring silently.
    import g33_run_env
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    repo = _clean_repo(tmp_path)
    binary = tmp_path / "libfake.dylib"
    binary.write_bytes(b"not a real dylib, but a real file with a real digest")
    env = g33_run_env.build_env(
        sched, tmp_path, binary=binary,
        column_map=[[i, 0, i, i] for i in range(SCHED["B"])],
        run_uuid="uuid-under-test", column_layout_id="lc05-3col", repo=repo)
    required = _overlay_required_env()
    assert required <= set(env), f"never set: {sorted(required - set(env))}"
    assert set(env) <= required, f"set but unused: {sorted(set(env) - required)}"


def test_run_env_seals_what_it_points_at(tmp_path):
    # The sealed digests must describe the descriptors actually written, and the
    # op-seq windows the containers actually declare — one schedule, sealed once.
    import g33_run_env, hashlib as _h
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    repo = _clean_repo(tmp_path)
    binary = tmp_path / "libfake.dylib"
    binary.write_bytes(b"x" * 64)
    env = g33_run_env.build_env(
        sched, tmp_path, binary=binary,
        column_map=[[i, 0, i, i] for i in range(SCHED["B"])],
        run_uuid="u", column_layout_id="lc05-3col", repo=repo)

    schema_dir = Path(env["KDM6_G33_SCHEMA_DIR"])
    for entry in env["KDM6_G33_SCHEMA_SHA256"].split(","):
        cid, sha = entry.split(":")
        assert _h.sha256((schema_dir / f"{cid}.desc").read_bytes()).hexdigest() == sha

    windows = {e.split(":")[0] for e in env["KDM6_G33_OP_SEQ_MAP"].split(",")}
    assert windows == {c["container_id"] for c in ge.run_index(sched)["containers"]}
    assert env["KDM6_G33_BINARY_SHA256"] == _h.sha256(binary.read_bytes()).hexdigest()


def test_run_env_refuses_a_binary_that_does_not_exist(tmp_path):
    import g33_run_env
    with pytest.raises(FileNotFoundError):
        g33_run_env.build_env(
            {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}, tmp_path,
            binary=tmp_path / "absent.dylib", column_map=[[0, 0, 0, 0]],
            run_uuid="u", column_layout_id="l", repo=_clean_repo(tmp_path))


# ── CLI export quoting and producer provenance ───────────────────────────────
_INJECTIONS = ["$(echo PWNED)", "`echo PWNED`", 'a"; echo PWNED; echo "b',
               "x\\", "'; echo PWNED; '", "$IFS$(echo PWNED)"]


@pytest.mark.parametrize("hostile", _INJECTIONS)
def test_cli_exports_survive_eval_without_executing(hostile, tmp_path):
    # json.dumps emits a DOUBLE-quoted string, and inside double quotes a shell
    # still expands $(...) and backticks. `--run-uuid '$(...)'` executed on eval;
    # measured before the fix as INJ=PWNED.
    import shlex, subprocess
    line = f"export G33_T={shlex.quote(hostile)}"
    out = subprocess.run(["bash", "-c", f"{line}\nprintf '%s' \"$G33_T\""],
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert out.stdout == hostile, "the value changed — the shell interpreted it"
    assert "PWNED" not in out.stdout or "PWNED" in hostile


def test_producer_commit_refuses_a_dirty_tree(tmp_path):
    # A dirty tree means HEAD does not describe the compiled source, so stamping
    # it claims a provenance that does not hold.
    import subprocess, g33_run_env
    repo = tmp_path / "repo"
    (repo / "libtorch" / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "libtorch" / "src" / "a.cpp").write_text("int a;\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "x"], check=True)
    assert re.fullmatch(r"[0-9a-f]{40}", g33_run_env._git_head(repo))
    (repo / "libtorch" / "src" / "a.cpp").write_text("int a; int b;\n")
    with pytest.raises(RuntimeError, match="does not describe the tree"):
        g33_run_env._git_head(repo)


def test_stale_binary_is_refused(tmp_path):
    # PRODUCER_COMMIT and BINARY_SHA256 are independent facts; a dylib built days
    # ago still gets stamped with today's HEAD, and its digest — a real hash of a
    # real file — looks like proof.
    import os, subprocess, g33_run_env
    repo = tmp_path / "repo"
    (repo / "libtorch" / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    src = repo / "libtorch" / "src" / "a.cpp"
    src.write_text("int a;\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    binary = tmp_path / "lib.dylib"
    binary.write_bytes(b"built earlier")
    os.utime(binary, (1, 1))                      # older than the source
    with pytest.raises(RuntimeError, match="older than"):
        g33_run_env._check_binary_not_stale(binary, repo)
    os.utime(binary, None)                        # rebuilt now
    g33_run_env._check_binary_not_stale(binary, repo)


def test_stale_guard_covers_the_diagnostic_build_inputs():
    # The guard watched only the canonical tree, so editing the overlay — the
    # translation unit the diagnostic dylib is actually compiled from — and not
    # rebuilding passed silently. That is the most likely staleness here, since
    # instrumentation work edits exactly those files.
    import g33_run_env
    covered = set(g33_run_env._BUILD_INPUTS)
    assert "harness/g33_overlay/sedimentation.cpp.overlay" in covered
    assert "harness/g33_overlay/g33_op_dump.h" in covered
    assert "harness/g33_overlay/g33_op_trace.h" in covered
    # and it must NOT watch files that cannot reach the artifact: a guard firing
    # on edits with no effect on the binary gets switched off by whoever hits it
    for harmless in ("harness/g33_overlay/verify_overlay.py",
                     "harness/g33_overlay/test_g33_writer.cpp",
                     "harness/g33_overlay/BASE_SHA256_sedimentation.cpp"):
        assert harmless not in covered


@pytest.mark.parametrize("edited", ["harness/g33_overlay/sedimentation.cpp.overlay",
                                    "harness/g33_overlay/g33_op_dump.h",
                                    "libtorch/src/a.cpp"])
def test_stale_guard_fires_for_each_build_input(edited, tmp_path):
    import os, subprocess, time, g33_run_env
    repo = tmp_path / "repo"
    (repo / "harness/g33_overlay").mkdir(parents=True)
    (repo / "libtorch/src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for rel in ("harness/g33_overlay/sedimentation.cpp.overlay",
                "harness/g33_overlay/g33_op_dump.h", "libtorch/src/a.cpp"):
        (repo / rel).write_text("original\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    binary = repo / "lib.dylib"
    binary.write_bytes(b"built")
    os.utime(binary, None)
    g33_run_env._check_binary_not_stale(binary, repo)      # fresh: accepted
    time.sleep(0.01)
    (repo / edited).write_text("changed after the build\n")
    with pytest.raises(RuntimeError, match="older than"):
        g33_run_env._check_binary_not_stale(binary, repo)


# ── the evidence must be bound to the binary the process actually loaded ─────
def test_reader_requires_the_resolved_binary_to_match_the_sealed_one(tmp_path):
    # binary_sha256 is the digest of the file the harness INTENDED the run to
    # load; resolved_binary_sha256 is what the producer measured via dladdr. A
    # container where they differ was produced by a binary the evidence does not
    # describe — and a writer that never resolved anything cannot fabricate
    # agreement without echoing the sealed value, which the probe test below
    # shows the real resolution path does not do.
    gd.G33Writer(tmp_path / "ok.g33", _header())            # equal: accepted
    with pytest.raises(gd.G33Corruption, match="does not describe"):
        gd.G33Writer(tmp_path / "m.g33", _header(resolved_binary_sha256="f" * 64))
    for bad in ("", "zz" * 32, "A" * 64, 123):
        with pytest.raises(gd.G33Corruption):
            gd.G33Writer(tmp_path / f"b{abs(hash(str(bad)))}.g33",
                         _header(resolved_binary_sha256=bad))
    with pytest.raises(gd.G33Corruption, match="resolved_binary_path"):
        gd.G33Writer(tmp_path / "p.g33", _header(resolved_binary_path=""))


def test_dladdr_resolves_the_artifact_actually_running(tmp_path):
    # Measured, not assumed: the probe asks the dynamic linker what binary it is
    # running from. The resolved path must be the probe executable ITSELF, and
    # the C++ digest must equal Python's digest of that same file — otherwise
    # "resolved" would just be another self-reported string.
    import hashlib, os, subprocess
    exe = _compile_probe(tmp_path, "binary_binding_probe.cpp")
    r = subprocess.run([str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    path, sha = r.stdout.strip().splitlines()
    assert os.path.realpath(path) == os.path.realpath(str(exe))
    assert sha == hashlib.sha256(exe.read_bytes()).hexdigest()
    # the overlay's refusal path, driven for real: sealed == loaded accepts,
    # sealed != loaded rejects
    assert subprocess.run([str(exe), sha], capture_output=True).returncode == 0
    bad = subprocess.run([str(exe), "f" * 64], capture_output=True, text=True)
    assert bad.returncode == 1 and "REJECTED" in bad.stderr


# ── comparator-recomputed flag authority (owner adjudication: producer flags
#    are debugging aids; acceptance authority is recomputed from raw bits) ────
def test_mstep_exactness_comes_from_the_bits():
    # int32(2) cannot hide 2.0 vs 2.0000000000000004 — the piacw-class confusion
    exact = gd.pack_payload_bits("f64", [0x4000000000000000])   # 2.0
    off = gd.pack_payload_bits("f64", [0x4000000000000001])     # 2.0 + 1 ulp
    assert gdv.derive_mstep("f64", exact) == {"decoded_i32": [2], "exact_integer": [1]}
    assert gdv.derive_mstep("f64", off) == {"decoded_i32": [2], "exact_integer": [0]}
    with pytest.raises(gd.G33Corruption, match="non-finite"):
        gdv.derive_mstep("f64", gd.pack_payload_bits("f64", [0x7FF0000000000000]))
    assert gdv.derive_mstep("i32", gd.pack_payload("i32", [3]))["exact_integer"] == [1]


def test_gate_flags_come_from_the_bits():
    g = gdv.derive_gate("f32", gd.pack_payload("f32", [0.0, 1.0, 0.5]))
    assert g["exact_01"] == [1, 1, 0]
    assert g["active_mask"] == [0, 1, 1]
    assert g["decoded_u8"] == [0, 1, None]     # decoding a non-0/1 gate is meaningless
    # NaN gate: non-exact, but ACTIVE under the producer's (gate != 0) semantics
    gn = gdv.derive_gate("f32", gd.pack_payload_bits("f32", [0x7FC00000]))
    assert gn["exact_01"] == [0] and gn["active_mask"] == [1]
    # -0.0 is value-exact 0 and inactive, though its BITS differ from +0.0
    neg0 = gdv.derive_gate("f32", gd.pack_payload_bits("f32", [0x80000000]))
    assert neg0 == {"exact_01": [1], "active_mask": [0], "decoded_u8": [0]}


def test_floor_activity_has_a_value_view_and_a_bits_view():
    raw = gd.pack_payload_bits("f32", [0x00000000, 0x3F800000])    # +0.0, 1.0
    safe = gd.pack_payload_bits("f32", [0x80000000, 0x3F800000])   # -0.0, 1.0
    fl = gdv.derive_floor_active("f32", raw, safe)
    assert fl["value_changed"] == [0, 0]       # what the producer's != computes
    assert fl["bits_changed"] == [1, 0]        # what only a raw-bit view can see


def test_min_branches_are_four_state_not_boolean():
    left = gd.pack_payload("f32", [1.0, 2.0, 3.0])
    right = gd.pack_payload("f32", [2.0, 1.0, 3.0])
    assert gdv.classify_min("f32", left, right) == [
        gd.BRANCH_LEFT_SELECTED, gd.BRANCH_RIGHT_SELECTED, gd.BRANCH_TIE]


def test_nan_branch_is_unordered_not_tie_and_the_verdict_is_mask_dependent():
    # a<b and b<a are BOTH false for NaN, so a 3-state enum misfiles NaN as TIE.
    # And raising on NaN fails LEGITIMATE dumps: KDM6 evaluates raw divide/sqrt
    # in DEAD branches and masks afterwards (§236), so NaN operands are expected
    # there. UNORDERED is recorded always; it is a FAIL only where the physics
    # actually takes the comparison (active && finite_required).
    nan_left = gd.pack_payload_bits("f32", [0x7FC00000, 0x3F800000])
    ones = gd.pack_payload("f32", [1.0, 1.0])
    br = gdv.classify_min("f32", nan_left, ones)
    assert br == [gd.BRANCH_UNORDERED, gd.BRANCH_TIE]
    assert gdv.unordered_failures(br, [1, 1], [1, 1]) == [0]   # live branch: FAIL
    assert gdv.unordered_failures(br, [0, 1], [1, 1]) == []    # dead branch: recorded only
    assert gdv.unordered_failures(br, [1, 1], [0, 1]) == []    # not finite-required
    with pytest.raises(gd.G33Corruption, match="length mismatch"):
        gdv.unordered_failures(br, [1], [1, 1])


_QCRMIN = 1e-9
_N_SUB = 2       # fixture substep index: with mstep [1,2,3], gate(n=2) = [0,1,1]


def _substep_pre_fields(**edits):
    f = {
        "mstep_native": ("f64", gd.pack_payload("f64", [1.0, 2.0, 3.0])),
        "mstep_decoded_i32": ("i32", gd.pack_payload("i32", [1, 2, 3])),
        "mstep_exact_integer": ("u8", gd.pack_payload("u8", [1, 1, 1])),
        "gate_native": ("f32", gd.pack_payload("f32", [0.0, 1.0, 1.0])),
        "gate_decoded_u8": ("u8", gd.pack_payload("u8", [0, 1, 1])),
        "gate_exact_01": ("u8", gd.pack_payload("u8", [1, 1, 1])),
        "active_mask": ("u8", gd.pack_payload("u8", [0, 1, 1])),
        "dend_raw": ("f32", gd.pack_payload("f32", [1.0, 2.0, 3.0])),
        "dend_safe": ("f32", gd.pack_payload("f32", [1.0, 2.0, 3.0])),
        "dend_floor_active": ("u8", gd.pack_payload("u8", [0, 0, 0])),
        # delz[0] sits BELOW the floor, so safe[0] must be exactly f32(qcrmin)
        "delz_raw": ("f32", gd.pack_payload("f32", [5e-10, 5.0, 5.0])),
        "delz_safe": ("f32", gd.pack_payload("f32", [_QCRMIN, 5.0, 5.0])),
        "delz_floor_active": ("u8", gd.pack_payload("u8", [1, 0, 0])),
    }
    f.update(edits)
    return f


def test_cross_check_accepts_an_honest_producer():
    gdv.check_producer_flags(_substep_pre_fields(), _N_SUB, _QCRMIN)


def test_cross_check_catches_a_lying_producer_flag():
    # the piacw shape: mstep_native carries 2+1ulp but the producer claims exact
    with pytest.raises(gd.G33Corruption, match="mstep_exact_integer"):
        gdv.check_producer_flags(_substep_pre_fields(
            mstep_native=("f64", gd.pack_payload_bits(
                "f64", [0x3FF0000000000000, 0x4000000000000001,
                        0x4008000000000000]))), _N_SUB, _QCRMIN)
    with pytest.raises(gd.G33Corruption, match="delz_floor_active"):
        gdv.check_producer_flags(_substep_pre_fields(
            delz_floor_active=("u8", gd.pack_payload("u8", [0, 0, 0]))),
            _N_SUB, _QCRMIN)
    with pytest.raises(gd.G33Corruption, match="active_mask"):
        gdv.check_producer_flags(_substep_pre_fields(
            active_mask=("u8", gd.pack_payload("u8", [0, 1, 0]))),
            _N_SUB, _QCRMIN)


def test_cross_check_refuses_missing_operands():
    # a cross-check that silently skips an absent operand is vacuous
    f = _substep_pre_fields()
    del f["gate_native"]
    with pytest.raises(gd.G33Corruption, match="missing operand"):
        gdv.check_producer_flags(f, _N_SUB, _QCRMIN)


def test_surface_expectation_is_per_species():
    surf = {r["field"] for r in ge.expected_records(SCHED) if r["stage"] == "surface"}
    for f in ("bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg",
              "bottom_fall_qi", "bottom_fall_total"):
        assert f in surf
    assert "bottom_fall" not in surf   # the aggregate alone cannot attribute


@pytest.mark.parametrize("name", ["a b.cpp", "a\rb.cpp"])
def test_stale_guard_sees_awkwardly_named_build_inputs(tmp_path, name):
    # Two fail-opens of the same class, found one layer apart. Whitespace-
    # splitting fragmented "a b.cpp" into tokens that exist nowhere; the fix
    # kept text=True, whose universal-newline translation turned a '\r' in a
    # filename into '\n' — either way is_file() failed and the input silently
    # LEFT the guard. Binary NUL-split listing leaves no translation step.
    import os, subprocess, time, g33_run_env
    repo = tmp_path / "repo"
    (repo / "libtorch/src").mkdir(parents=True)
    (repo / "harness/g33_overlay").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    spaced = repo / "libtorch/src" / name
    spaced.write_text("int a;\n")
    (repo / "harness/g33_overlay/sedimentation.cpp.overlay").write_text("x\n")
    (repo / "harness/g33_overlay/g33_op_dump.h").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    binary = repo / "lib.dylib"
    binary.write_bytes(b"built")
    os.utime(binary, None)
    g33_run_env._check_binary_not_stale(binary, repo)     # fresh: accepted
    time.sleep(0.01)
    spaced.write_text("edited after the build\n")
    with pytest.raises(RuntimeError, match="older than"):
        g33_run_env._check_binary_not_stale(binary, repo)


def test_build_env_refuses_a_malformed_column_map_before_anything_runs(tmp_path):
    # Without the early check a malformed map is only caught when the overlay
    # opens its first container — deep inside the physics run.
    import g33_run_env
    repo = _clean_repo(tmp_path)
    binary = tmp_path / "lib.dylib"
    binary.write_bytes(b"x")
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    for bad in ([[0, 0, 0, 0]],                                   # short
                [[0, 0, 0, 0], [0, 0, 1, 1], [2, 0, 2, 2]],       # dup B_index
                [[0, 0, 0], [1, 0, 1], [2, 0, 2]]):               # wrong arity
        with pytest.raises(gd.G33Corruption):
            g33_run_env.build_env(sched, tmp_path / "o", binary=binary,
                                  column_map=bad, run_uuid="u",
                                  column_layout_id="l", repo=repo)


# ── P0: identity fields are the path-traversal boundary ──────────────────────
def test_all_identity_fields_are_safe_id_validated(tmp_path):
    # case_id flows into the container file name verbatim (overlay side), and
    # _SAFE_ID's character class alone happily matches "." and ".." — the old
    # comment claimed otherwise. Every identity field is now checked, with
    # dot-only segments rejected explicitly.
    for field in ("case_id", "pair_id", "run_uuid", "column_layout_id",
                  "container_id"):
        for bad in ("../evil", "a/b", "a\\b", "..", ".", "...", "", "a b",
                    "x\x00y", "x\ny"):
            with pytest.raises(gd.G33Corruption):
                gd.G33Writer(tmp_path / f"{field}_{abs(hash(bad))}.g33",
                             _header(**{field: bad}))
    gd.G33Writer(tmp_path / "ok.g33", _header(case_id="closure3-C3.3"))


def test_cpp_overlay_refuses_unsafe_ids_before_building_the_path():
    # the Python validator sees the header only after the path was opened; the
    # producer must refuse first — pin that the gate sits before path assembly
    src = (ROOT / _TRACE).read_text()
    assert "safe_id(v)" in src
    assert src.index("g33: unsafe id") < src.index('std::string path = std::string(dir)')


def test_gate_that_is_exactly_01_but_wrong_is_caught_by_the_mstep_law():
    # The old check only asked whether the gate was exactly 0/1 — a gate that is
    # WRONG but exactly 0/1 passed. gate_b(n) = [n <= mstep_b] ties it to the
    # operand it is derived from: with mstep [1,2,3] and n=2 the gate MUST be
    # [0,1,1]; an all-ones gate is internally consistent and still illegal.
    wrong = _substep_pre_fields(
        gate_native=("f32", gd.pack_payload("f32", [1.0, 1.0, 1.0])),
        gate_decoded_u8=("u8", gd.pack_payload("u8", [1, 1, 1])),
        gate_exact_01=("u8", gd.pack_payload("u8", [1, 1, 1])),
        active_mask=("u8", gd.pack_payload("u8", [1, 1, 1])))
    with pytest.raises(gd.G33Corruption, match="gate_vs_mstep_law"):
        gdv.check_producer_flags(wrong, _N_SUB, _QCRMIN)


def test_mstep_outside_the_physical_range_is_an_invalid_run():
    for bad_mstep, bad_decoded in ([0.0, 2.0, 3.0], [0, 2, 3]), ([1.0, 2.0, 101.0], [1, 2, 101]):
        f = _substep_pre_fields(
            mstep_native=("f64", gd.pack_payload("f64", bad_mstep)),
            mstep_decoded_i32=("i32", gd.pack_payload("i32", bad_decoded)))
        with pytest.raises(gd.G33Corruption, match="physical range"):
            gdv.check_producer_flags(f, _N_SUB, _QCRMIN)


def test_floor_authority_is_the_threshold_relation_not_the_output_diff():
    # relation of raw vs the dtype-faithful threshold; BELOW must produce
    # exactly the threshold's bits, AT_OR_ABOVE exactly the raw bits
    raw = gd.pack_payload("f32", [5e-10, _QCRMIN, 5.0])
    assert gdv.classify_floor("f32", raw, _QCRMIN) == [
        gdv.FLOOR_BELOW, gdv.FLOOR_AT_OR_ABOVE, gdv.FLOOR_AT_OR_ABOVE]
    nan = gd.pack_payload_bits("f32", [0x7FC00000])
    assert gdv.classify_floor("f32", nan, _QCRMIN) == [gdv.FLOOR_UNORDERED]
    # a clamp that emits anything other than max(raw, qcrmin) is not the
    # declared semantics — even if `safe != raw` happens to look plausible
    good_safe = gd.pack_payload("f32", [_QCRMIN, _QCRMIN, 5.0])
    gdv.check_floor_semantics("f32", raw, good_safe, _QCRMIN)
    bad_safe = gd.pack_payload("f32", [2e-9, _QCRMIN, 5.0])   # floored to the WRONG value
    with pytest.raises(gd.G33Corruption, match="not the declared semantics"):
        gdv.check_floor_semantics("f32", raw, bad_safe, _QCRMIN)
    # -0.0 raw is BELOW a positive floor and must come back as the threshold
    neg0 = gd.pack_payload_bits("f32", [0x80000000])
    gdv.check_floor_semantics("f32", neg0, gd.pack_payload("f32", [_QCRMIN]), _QCRMIN)


# ── P0-6: the run contract is a persisted artifact ───────────────────────────
def test_run_contract_is_sealed_as_a_file(tmp_path):
    import hashlib as _h, json as _j
    import g33_run_env
    repo = _clean_repo(tmp_path)
    binary = tmp_path / "lib.dylib"
    binary.write_bytes(b"x")
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    env = g33_run_env.build_env(sched, tmp_path / "o", binary=binary,
                                column_map=[[i, 0, i, i] for i in range(SCHED["B"])],
                                run_uuid="u-1", column_layout_id="lc05-3col",
                                repo=repo)
    body = (tmp_path / "o" / "run_contract.json").read_bytes()
    c = _j.loads(body)
    # the contract and the environment must describe the SAME sealing
    assert c["binary_sha256"] == env["KDM6_G33_BINARY_SHA256"]
    assert c["qcrmin"] == SCHED["qcrmin"]
    index = ge.run_index(sched)
    assert [x["container_id"] for x in c["containers"]] == \
           [x["container_id"] for x in index["containers"]]
    for cc, ic in zip(c["containers"], index["containers"]):
        assert (cc["first_op_seq_id"], cc["last_op_seq_id"]) == \
               (ic["first_op_seq_id"], ic["last_op_seq_id"])
    sealed = dict(e.split(":") for e in env["KDM6_G33_SCHEMA_SHA256"].split(","))
    assert {x["container_id"]: x["descriptor_sha256"] for x in c["containers"]} == sealed
    # the side-car digest matches the bytes on disk
    sha_line = (tmp_path / "o" / "run_contract.sha256").read_text().split()[0]
    assert sha_line == _h.sha256(body).hexdigest()


def test_run_contract_refuses_overwrite_and_missing_qcrmin(tmp_path):
    import g33_run_env
    repo = _clean_repo(tmp_path)
    binary = tmp_path / "lib.dylib"
    binary.write_bytes(b"x")
    cmap = [[i, 0, i, i] for i in range(SCHED["B"])]
    sched = {**SCHED, "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}
    g33_run_env.build_env(sched, tmp_path / "o", binary=binary, column_map=cmap,
                          run_uuid="u-1", column_layout_id="l", repo=repo)
    with pytest.raises(FileExistsError, match="one contract per run"):
        g33_run_env.build_env(sched, tmp_path / "o", binary=binary,
                              column_map=cmap, run_uuid="u-2",
                              column_layout_id="l", repo=repo)
    nosched = {k: v for k, v in sched.items() if k != "qcrmin"}
    with pytest.raises(ValueError, match="qcrmin"):
        g33_run_env.build_env(nosched, tmp_path / "o2", binary=binary,
                              column_map=cmap, run_uuid="u-3",
                              column_layout_id="l", repo=repo)


def test_floor_dtype_errors_are_g33corruption_not_keyerror():
    # _coerce_threshold's dict lookup leaked a bare KeyError for a non-float
    # dtype — a fail-closed reader must never surface raw internal errors.
    # Validated at the single chokepoint so BOTH callers are covered.
    for fn, args in ((gdv.check_floor_semantics,
                      ("i32", gd.pack_payload("i32", [1]),
                       gd.pack_payload("i32", [1]), _QCRMIN)),
                     (gdv.classify_floor, ("u8", b"\x01", _QCRMIN))):
        with pytest.raises(gd.G33Corruption, match="floor operand cannot be"):
            fn(*args)


def test_substep_index_rejects_bool_and_nonint():
    # bool is an int subclass; `type(n) is int` excludes it without a special case
    for bad in (True, False, 0, -1, 1.5, "2", None):
        with pytest.raises(gd.G33Corruption, match="positive int"):
            gdv.check_producer_flags(_substep_pre_fields(), bad, _QCRMIN)
