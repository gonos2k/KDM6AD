#!/usr/bin/env python3
"""Synthetic fail-closed tests for the G3.3-M dump container + expectation manifest
(protocol §7). No physics, no build — pure Python. Proves the reader/comparator
REJECT corrupt / missing / duplicate / stale / provenance-drift evidence, so a
buggy or tampered dump can never read as valid.
"""
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_dump as gd
import g33_expectation as ge

SCHED = {"case_id": "closure3-C3.3", "pair_id": "conservative", "backend": "cpp",
         "algorithm": "conservative", "B": 3, "K": 4, "loops": 1,
         "mstepmax_main": [1], "mstepmax_ice": [2], "species_scope": ["qr", "nr"]}


def _header(**over):
    h = {"producer_commit": "deadbeef", "binary_sha256": "0" * 64,
         "case_id": SCHED["case_id"], "pair_id": SCHED["pair_id"],
         "backend": SCHED["backend"], "algorithm": SCHED["algorithm"],
         "B": SCHED["B"], "K": SCHED["K"], "column_layout_id": "lc05-3col",
         "column_index_map": [[i, 0, i, i] for i in range(SCHED["B"])],
         "canonical_k_order": "top-first",
         "run_uuid": "uuid-1", "process_id": "111", "owner_thread_id": "222",
         "record_count_expected": 0}
    h.update(over)
    return h


def _write_valid(path, records=None):
    recs = records if records is not None else ge.expected_records(SCHED)
    w = gd.G33Writer(path, _header(record_count_expected=len(recs)))
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
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 5, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
         "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "falk_f32"}
    w.record(r, "f32", [1], gd.pack_payload("f32", [1]))
    with pytest.raises(gd.G33Corruption, match="duplicate seq_no"):
        w.record(r, "f32", [1], gd.pack_payload("f32", [1]))


def test_nonmonotone_seq(tmp_path):
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    base = {"outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
            "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    w.record({**base, "seq_no": 10}, "f32", [1], gd.pack_payload("f32", [1]))
    with pytest.raises(gd.G33Corruption, match="non-monotone"):
        w.record({**base, "seq_no": 4}, "f32", [1], gd.pack_payload("f32", [1]))


def test_payload_size_mismatch_writer(tmp_path):
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
         "species": "qr", "op_id": "QR_FALK", "stage": "op", "field": "f"}
    with pytest.raises(gd.G33Corruption, match="payload size"):
        w.record(r, "f32", [4], gd.pack_payload("f32", [1, 2]))  # shape 4 but 2 elems


def test_finalize_no_clobber(tmp_path):
    # a completed container appearing concurrently (after the constructor's
    # no-overwrite check) must NOT be destroyed by finalize().
    p = tmp_path / "c.g33"
    w = gd.G33Writer(p, _header())
    r = {"seq_no": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
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
        r = {"seq_no": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
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
    extra = dict(recs[0]); extra["field"] = "bogus_extra"; extra["seq_no"] = len(recs)
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
    # a degenerate schedule (no substeps) must also be refused, not accepted
    with pytest.raises(ValueError, match="no op records"):
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
    assert {"bottom_fall", "delz_bottom", "surface_mul1", "surface_mul_dt",
            "rain_increment"} <= surf
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
    r = {"seq_no": 0, "outer_loop": 1, "chain": "main", "n": 1, "cell_role": "TOP",
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
