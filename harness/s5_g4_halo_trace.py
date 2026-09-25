#!/usr/bin/env python3
"""Replay the bounded exact-build S5 stencil trace projection.

Usage: ``python harness/s5_g4_halo_trace.py MANIFEST.json``

The replayer checks the public NPZ digest, compares raw caller words over the
published stencil neighborhood, checks the captured x2 owner/halo pairs, and
recomputes the first selected output difference. It does not reopen private
full-domain dumps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HALO_GROUPS = {
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
    (0, (1, 4)), (1, (1, 4)), (2, (1, 2)), (31, (2,)),
    (32, (2,)), (4, (1,)), (5, (1, 3)), (6, (1, 2, 3)), (7, (1, 2)),
)
EXPECTED_OUTPUT_I = (117, 234)
EXPECTED_CALLER_STAGES = (0, 1)
EXPECTED_CALLER_I = (116, 117, 118, 233, 234, 235)
EXPECTED_X2_SEAM_COPIES = {
    117: ("i1-117_j1-283", "i118-235_j1-283"),
    118: ("i118-235_j1-283", "i1-117_j1-283"),
}


def _shape_bounds(kind: str, *, output: bool) -> tuple[list[int],
                                                       list[int] | None,
                                                       list[int] | None]:
    """Pinned raw-word shape/origin contract for the group/stage dump schema."""
    if kind in ("M", "H"):
        return [39, 282 if output else 284], [1, 39], [1, 282] if output else [0, 283]
    if kind == "Z":
        return [40, 282], [1, 40], [1, 282]
    if kind == "S":
        return [282], None, [1, 282]
    if kind == "HS":
        return [282 if output else 284], None, [1, 282] if output else [0, 283]
    if kind == "V":
        return [39], [1, 39], None
    if kind == "C":
        return [1], None, None
    raise ValueError(f"unknown trace kind {kind!r}")


def _expected_records() -> tuple[list[dict], list[dict], list[dict]]:
    outputs, inputs, halos = [], [], []
    for stage, groups in EXPECTED_STAGE_GROUPS:
        for group in groups:
            for i in EXPECTED_OUTPUT_I:
                for field, kind in HALO_GROUPS[group]:
                    shape, k_bounds, j_bounds = _shape_bounds(kind, output=True)
                    outputs.append({
                        "stage": stage, "group": group, "i": i,
                        "field": field,
                        "key": f"out_s{stage}_g{group}_i{i}_{field}",
                        "shape": shape, "j_bounds": j_bounds,
                        "k_bounds": k_bounds, "owned": True,
                    })
    for stage in EXPECTED_CALLER_STAGES:
        for i in EXPECTED_CALLER_I:
            owned = i < 235
            for field, kind in HALO_GROUPS[5]:
                shape, k_bounds, j_bounds = _shape_bounds(kind, output=False)
                inputs.append({
                    "stage": stage, "i": i, "field": field,
                    "key": f"arg_s{stage}_i{i}_{field}",
                    "shape": shape, "j_bounds": j_bounds,
                    "k_bounds": k_bounds, "owned": owned,
                })
    for stage in EXPECTED_CALLER_STAGES:
        for i, (owner_rank, halo_rank) in EXPECTED_X2_SEAM_COPIES.items():
            for field, kind in HALO_GROUPS[5]:
                shape, k_bounds, j_bounds = _shape_bounds(kind, output=False)
                halos.append({
                    "stage": stage, "i": i, "field": field,
                    "key": f"halo_s{stage}_i{i}_{field}",
                    "shape": shape, "j_bounds": j_bounds,
                    "k_bounds": k_bounds, "owner_rank": owner_rank,
                    "halo_rank": halo_rank,
                })
    return outputs, inputs, halos


def replay(manifest_path: Path) -> dict:
    import numpy as np
    raw_word_dtype = np.dtype(">u4")

    manifest = json.loads(manifest_path.read_text())
    npz_path = manifest_path.with_name(manifest["trace_file"])
    payload = npz_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest["trace_sha256"]:
        raise ValueError(f"trace digest mismatch: {digest} != {manifest['trace_sha256']}")

    expected_outputs, expected_inputs, expected_halos = _expected_records()
    if manifest.get("selected_output_records") != expected_outputs:
        raise ValueError("selected-output key/coordinate universe differs from fixed contract")
    if manifest.get("selected_caller_input_records") != expected_inputs:
        raise ValueError("caller-input key/coordinate universe differs from fixed stencil contract")
    if manifest.get("selected_x2_seam_halo_records") != expected_halos:
        raise ValueError("x2 seam owner/halo key universe differs from fixed contract")

    comparisons = manifest["strict_comparisons"]
    if set(comparisons) != {
            "serial_vs_g4", "x2_vs_g4", "serial_noenv_vs_capture",
            "x2_noenv_vs_capture"}:
        raise ValueError("strict comparison set is incomplete")
    for label, result in comparisons.items():
        if (result["returncode"] != 0 or result["common_variables"] != 254
                or result["numeric_variables"] != 253
                or result["character_variables"] != ["Times"]
                or result["result_line"] != "RESULT: STRICT BITWISE PASS"):
            raise ValueError(f"strict output/control gate failed in manifest: {label}")
    run_ids = manifest["run_identities"]
    for name, grid in (("serial_env_off", "1x1"), ("serial_capture", "1x1"),
                       ("x2_env_off", "2x1"), ("x2_capture", "2x1")):
        run = run_ids[name]
        controls = run["controls"]
        if (run["actual_proc_grid"] != grid or run["requested_proc_grid"] != grid
                or run["exit_code"] != 0 or not run["experiment_valid"]
                or run["scheme"] != "237" or controls["seconds"] != 20
                or controls["fixed_dt"] is not True
                or controls["input_canonical_sha256"] != manifest["input_canonical_sha256"]
                or controls["namelist_without_grid_sha256"]
                != manifest["namelist_without_grid_sha256"]):
            raise ValueError(f"run identity/control mismatch: {name}")
    expected_tiles = {
        ("1x1", (1, 235), ((1, 235, 1, 142), (1, 235, 143, 283))),
        ("2x1", (1, 117), ((1, 117, 1, 142), (1, 117, 143, 283))),
        ("2x1", (118, 235), ((118, 235, 1, 142), (118, 235, 143, 283))),
    }
    got_tiles = {(r["grid"], tuple(r["patch_i"]),
                  tuple(tuple(tile) for tile in r["tiles"]))
                 for r in manifest["rank_tile_bounds"]}
    if got_tiles != expected_tiles:
        raise ValueError("rank/tile call-bound metadata mismatch")

    input_differences = 0
    input_words = 0
    halo_differences = 0
    halo_words = 0
    output_first = None
    output_by_stage: dict[str, int] = {}
    output_differences = []
    output_words = 0
    with np.load(npz_path, allow_pickle=False) as trace:
        expected_members: set[str] = set()
        for record in expected_inputs:
            key = record["key"]
            left_name, right_name = f"serial__{key}", f"x2__{key}"
            expected_members.update((left_name, right_name))
            if left_name not in trace or right_name not in trace:
                raise ValueError(f"missing caller-input pair {key}")
            left, right = trace[left_name], trace[right_name]
            if left.dtype != raw_word_dtype or right.dtype != raw_word_dtype:
                raise ValueError(
                    f"caller inputs must be big-endian uint32 REAL(4) words: {key}")
            if list(left.shape) != record["shape"] or left.shape != right.shape:
                raise ValueError(f"caller-input shape mismatch: {key}")
            diff = left != right
            input_words += left.size
            input_differences += int(np.count_nonzero(diff))

        for record in expected_halos:
            key = record["key"]
            owner_name, halo_name = f"x2_owner__{key}", f"x2_halo__{key}"
            expected_members.update((owner_name, halo_name))
            if owner_name not in trace or halo_name not in trace:
                raise ValueError(f"missing owner/halo pair {key}")
            owner, halo = trace[owner_name], trace[halo_name]
            if owner.dtype != raw_word_dtype or halo.dtype != raw_word_dtype:
                raise ValueError(
                    f"halo inputs must be big-endian uint32 REAL(4) words: {key}")
            if list(owner.shape) != record["shape"] or owner.shape != halo.shape:
                raise ValueError(f"owner/halo shape mismatch: {key}")
            halo_words += owner.size
            halo_differences += int(np.count_nonzero(owner != halo))

        for record in expected_outputs:
            key = record["key"]
            left_name, right_name = f"serial__{key}", f"x2__{key}"
            expected_members.update((left_name, right_name))
            if left_name not in trace or right_name not in trace:
                raise ValueError(f"missing selected output pair {key}")
            left, right = trace[left_name], trace[right_name]
            if left.dtype != raw_word_dtype or right.dtype != raw_word_dtype:
                raise ValueError(
                    f"outputs must be big-endian uint32 REAL(4) words: {key}")
            if list(left.shape) != record["shape"] or left.shape != right.shape:
                raise ValueError(f"selected-output shape mismatch: {key}")
            diff = left != right
            count = int(np.count_nonzero(diff))
            output_words += left.size
            if count:
                output_differences.append({
                    "stage": record["stage"], "group": record["group"],
                    "i": record["i"], "field": record["field"],
                    "different_words": count,
                })
                output_by_stage[str(record["stage"])] = (
                    output_by_stage.get(str(record["stage"]), 0) + count
                )
                if output_first is None:
                    index = tuple(int(v) for v in np.argwhere(diff)[0])
                    output_first = {
                        "stage": record["stage"], "group": record["group"],
                        "i": record["i"], "field": record["field"],
                        "different_words": count,
                        "first_array_index": list(index),
                        "serial_u32": int(left[index]),
                        "x2_u32": int(right[index]),
                    }

        if set(trace.files) != expected_members:
            raise ValueError("NPZ members do not match the manifest record set")

    return {
        "schema": "s5-g4-halo-trace-replay-v1",
        "trace_sha256": digest,
        "strict_controls_and_tile_metadata_valid": True,
        "caller_input_words_compared": input_words,
        "caller_input_word_differences": input_differences,
        "x2_seam_owner_halo_words_compared": halo_words,
        "x2_seam_owner_halo_differences": halo_differences,
        "selected_output_words_compared": output_words,
        "selected_output_records_with_differences": output_differences,
        "selected_output_differences_by_stage": output_by_stage,
        "first_selected_output_difference": output_first,
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
