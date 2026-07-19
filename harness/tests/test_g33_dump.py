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
           "backend": SCHED["backend"], "algorithm": SCHED["algorithm"]}
    gd.verify_attestation(out["header"], att)  # no raise


def test_attestation_drift(tmp_path):
    p = tmp_path / "c.g33"; _write_valid(p)
    out = gd.read_container(p)
    att = {"producer_commit": "OTHER", "binary_sha256": "0" * 64,
           "case_id": SCHED["case_id"], "pair_id": SCHED["pair_id"],
           "backend": SCHED["backend"], "algorithm": SCHED["algorithm"]}
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
    keys = ge.expected_key_set(SCHED)                    # tuple idx: 1=chain 2=n 6=stage
    ice_reslope_n = {k[2] for k in keys if k[1] == "ice" and k[6] == "reslope_output"}
    assert ice_reslope_n == {1}                          # mstepmax_ice=2 -> only n=1 (n<mmax)
    main_reslope_n = {k[2] for k in keys if k[1] == "main" and k[6] == "reslope_output"}
    assert main_reslope_n == {1}                         # mstepmax_main=1 -> n=1 (every main n)


def test_cell_role_templates():
    # legacy TOP mass has NO outflow/inflow (direct clamp); conservative TOP has outflow.
    leg = {"algorithm": "legacy"}
    assert ge._mass_ops("legacy", "TOP") == ["QR_FALK", "QR_UPDATE"]
    assert ge._mass_ops("conservative", "TOP") == ["QR_FALK", "QR_OUTFLOW", "QR_UPDATE"]
    assert "QR_INFLOW" in ge._mass_ops("conservative", "INTERIOR")
    # number ladder is a distinct family
    assert ge._number_ops("conservative", "INTERIOR") == ["NR_FALK", "NR_OUTFLOW", "NR_INFLOW", "NR_UPDATE"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
