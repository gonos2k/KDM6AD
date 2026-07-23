#!/usr/bin/env python3
"""Public-CI fail-closed tests for the evidence-bundle reader (P0-7). Builds a
minimal but structurally real {algo}-C-evidence tree with G33Writer + matching SHA
manifests, then proves verify_cpp_evidence ACCEPTS it and REJECTS a tampered
contract, an unlisted extra file, and a missing comparator container. No torch."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_bundle_io as bio  # noqa: E402
import g33_dump as gd        # noqa: E402

B, K = 3, 4


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _header(cid, contract_sha, desc_sha, nrec):
    return {"producer_commit": "deadbeef", "binary_sha256": "0" * 64,
            "resolved_binary_path": "/x/lib.dylib", "resolved_binary_sha256": "0" * 64,
            "case_id": "c", "pair_id": "legacy", "backend": "cpp", "algorithm": "legacy",
            "B": B, "K": K, "column_layout_id": "l", "canonical_k_order": "top-first",
            "column_index_map": [[i, 0, i, i] for i in range(B)],
            "run_uuid": "u", "process_id": 1, "owner_thread_id": "2",
            "container_id": cid, "descriptor_sha256": desc_sha,
            "run_contract_sha256": contract_sha,
            "global_op_seq_start": 0, "global_op_seq_end": nrec - 1,
            "record_count_expected": nrec}


def _rec(cid, i):
    return {"seq_no": i, "op_seq_id": i, "stage": "op", "chain": "main", "n": 1,
            "cell_role": "TOP", "k": 0, "species": "qr", "op_id": "QR_FALK",
            "field": "mul_dend_q", "container_id": cid}


def _build(tmp):
    ev = tmp / "legacy-C-evidence"
    (ev / "dump").mkdir(parents=True)
    (ev / "schema").mkdir()
    contract = ev / "run_contract.json"
    contract.write_text(json.dumps({"algorithm": "legacy", "schedule": {"algorithm": "legacy"}}))
    (ev / "run_contract.sha256").write_text(f"{_sha(contract)}  run_contract.json\n")
    csha = _sha(contract)
    desc_lines = []
    for cid in bio.COMPARATOR_CONTAINERS:
        desc = ev / "schema" / f"{cid}.desc"
        desc.write_text(f"descriptor for {cid}\n")
        dsha = _sha(desc)
        desc_lines.append(f"{dsha}  {cid}.desc")
        w = gd.G33Writer(ev / "dump" / f"cpp_legacy_{cid}.g33", _header(cid, csha, dsha, 1))
        r = _rec(cid, 0)
        w.record(r, "f32", [B], gd.pack_payload("f32", [1.0] * B))
        w.finalize()
    (ev / "schema" / "descriptors.sha256").write_text("\n".join(desc_lines) + "\n")
    return ev


def test_valid_bundle_verifies(tmp_path):
    ev = _build(tmp_path)
    out = bio.verify_cpp_evidence(ev, "legacy")
    assert set(out["containers"]) == set(bio.COMPARATOR_CONTAINERS)


def test_tampered_contract_rejected(tmp_path):
    ev = _build(tmp_path)
    (ev / "run_contract.json").write_text('{"algorithm": "legacy", "tampered": true}')
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


def test_unlisted_extra_file_rejected(tmp_path):
    ev = _build(tmp_path)
    (ev / "schema" / "sneak.desc").write_text("unlisted\n")
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")


def test_missing_comparator_container_rejected(tmp_path):
    ev = _build(tmp_path)
    # drop L1_surface from both the descriptor manifest and the dump dir
    (ev / "dump" / "cpp_legacy_L1_surface.g33").unlink()
    lines = [ln for ln in (ev / "schema" / "descriptors.sha256").read_text().splitlines()
             if "L1_surface" not in ln]
    (ev / "schema" / "descriptors.sha256").write_text("\n".join(lines) + "\n")
    (ev / "schema" / "L1_surface.desc").unlink()
    with pytest.raises(bio.BundleError):
        bio.verify_cpp_evidence(ev, "legacy")
