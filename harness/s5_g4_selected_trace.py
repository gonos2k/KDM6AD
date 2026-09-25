#!/usr/bin/env python3
"""Replay the bounded public S5 G4 owner-column trace projection.

Usage: ``python harness/s5_g4_selected_trace.py MANIFEST.json``

This verifies the published NPZ digest and recomputes raw-word differences in
the selected C2 probe records. It does not reopen or certify the private full
Fortran dumps named by the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


C2_GROUPS = {
    1: (("u_2", "M"), ("t_2", "M"), ("ph_2", "Z"),
        ("w_2", "Z"), ("mu_2", "S")),
    2: (("ru", "M"), ("rv", "M"), ("rw", "Z"), ("ww", "Z"),
        ("php", "Z"), ("alt", "M"), ("al", "M"), ("p", "M"),
        ("rho", "M"), ("muu", "S"), ("muv", "S"), ("mut", "S")),
    3: (("ru_tend", "M"), ("rv_tend", "M"), ("rw_tend", "Z"),
        ("ph_tend", "Z"), ("t_tend", "M"), ("mu_tend", "S")),
    4: (("u_2", "M"), ("muu", "S"), ("mub", "S"), ("msfuy", "S")),
    5: (("u_2", "H"), ("v_2", "H"), ("mu_2", "HS"), ("mub", "HS"),
        ("c1h", "V"), ("c2h", "V"), ("dnw", "V"),
        ("msftx", "HS"), ("msfty", "HS"), ("msfux", "HS"),
        ("msfuy", "HS"), ("msfvx", "HS"), ("msfvx_inv", "HS"),
        ("msfvy", "HS"), ("rdx", "C"), ("rdy", "C")),
}


EXPECTED_STAGE_GROUPS = (
    (0, (1, 4, 5)), (1, (1, 4, 5)), (2, (1, 2)), (31, (2,)),
    (32, (2,)), (4, (1,)), (5, (1, 3)), (6, (1, 2, 3)), (7, (1, 2)),
)
EXPECTED_OUTPUT_I = (117, 234)
EXPECTED_KDM_ARRAYS = (
    "kdm__serial__TH_i110_k39_j83", "kdm__x2__TH_i110_k39_j83",
)


def _shape_and_bounds(kind: str) -> tuple[list[int], list[int] | None,
                                            list[int] | None]:
    """Schema-5 C2 field shape and coordinate bounds, pinned independently."""
    if kind in ("M", "H"):
        return [39, 282], [1, 39], [1, 282]
    if kind == "Z":
        return [40, 282], [1, 40], [1, 282]
    if kind in ("S", "HS"):
        return [282], None, [1, 282]
    if kind == "V":
        return [39], [1, 39], None
    if kind == "C":
        return [1], None, None
    raise ValueError(f"unknown selected-trace kind {kind!r}")


def _expected_records() -> list[dict]:
    rows = []
    for stage, groups in EXPECTED_STAGE_GROUPS:
        for group in groups:
            for i in EXPECTED_OUTPUT_I:
                for field, kind in C2_GROUPS[group]:
                    shape, k_bounds, j_bounds = _shape_and_bounds(kind)
                    rows.append({
                        "stage": stage, "group": group, "i": i,
                        "field": field,
                        "array_key": f"s{stage}_g{group}_i{i}_{field}",
                        "shape": shape, "k_bounds": k_bounds,
                        "j_bounds": j_bounds, "owned": True,
                    })
    return rows


def replay(manifest_path: Path) -> dict:
    import numpy as np
    raw_word_dtype = np.dtype(">u4")

    manifest = json.loads(manifest_path.read_text())
    npz_path = manifest_path.with_name(manifest["npz_file"])
    raw = npz_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != manifest["npz_sha256"]:
        raise ValueError(f"NPZ SHA-256 mismatch: {digest} != {manifest['npz_sha256']}")
    expected_records = _expected_records()
    expected_words = 2 * sum(
        __import__("math").prod(record["shape"]) for record in expected_records
    ) + 2
    if manifest.get("selected_records") != expected_records:
        raise ValueError("selected-record universe/shape/bounds differ from fixed C2 contract")
    if (manifest.get("selected_record_count") != len(expected_records)
            or manifest.get("raw_word_count") != expected_words):
        raise ValueError("selected-record count/word total differs from fixed C2 contract")

    first = None
    per_stage: dict[str, int] = {}
    per_record = []
    with np.load(npz_path, allow_pickle=False) as trace:
        expected_keys = set()
        for record in expected_records:
            stem = record["array_key"]
            left_key, right_key = f"serial__{stem}", f"x2__{stem}"
            expected_keys.update((left_key, right_key))
            if left_key not in trace or right_key not in trace:
                raise ValueError(f"missing selected raw-word pair {stem}")
            left, right = trace[left_key], trace[right_key]
            if left.dtype != raw_word_dtype or right.dtype != raw_word_dtype:
                raise ValueError(
                    f"selected words must be big-endian uint32 REAL(4) words: {stem}")
            if list(left.shape) != record["shape"] or left.shape != right.shape:
                raise ValueError(f"selected shape mismatch: {stem}")
            diff = left != right
            count = int(np.count_nonzero(diff))
            if count:
                per_stage[str(record["stage"])] = (
                    per_stage.get(str(record["stage"]), 0) + count
                )
                first_index = tuple(int(v) for v in np.argwhere(diff)[0])
                row = {
                    "stage": record["stage"], "group": record["group"],
                    "i": record["i"], "field": record["field"],
                    "shape": list(left.shape), "different_words": count,
                    "first_array_index": list(first_index),
                    "serial_u32": int(left[first_index]),
                    "x2_u32": int(right[first_index]),
                }
                if first is None:
                    first = row
            per_record.append({
                "stage": record["stage"], "group": record["group"],
                "i": record["i"], "field": record["field"],
                "different_words": count,
            })
        if set(trace.files) != expected_keys | set(EXPECTED_KDM_ARRAYS):
            raise ValueError("NPZ members differ from declared selected-record set")
        if any(trace[name].dtype != raw_word_dtype for name in EXPECTED_KDM_ARRAYS):
            raise ValueError("selected KDM words must be big-endian uint32 REAL(4) words")
        kdm_left = int(trace["kdm__serial__TH_i110_k39_j83"][0])
        kdm_x2 = int(trace["kdm__x2__TH_i110_k39_j83"][0])

    kdm_expect = manifest["kdm_reported_first_difference"]["flat_endian_uint32"]
    if kdm_left != kdm_expect["serial"] or kdm_x2 != kdm_expect["x2"]:
        raise ValueError("selected KDM TH words do not match the manifest")
    return {
        "schema": "s5-g4-selected-trace-replay-v1",
        "scope": "published owned columns and declared G33 stages/groups only",
        "npz_sha256": digest,
        "selected_records": len(per_record),
        "raw_words_compared": manifest["raw_word_count"],
        "first_selected_difference": first,
        "different_words_by_stage": per_stage,
        "kdm_TH_selected_words": {"serial": kdm_left, "x2": kdm_x2},
        "full_domain_reopened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
