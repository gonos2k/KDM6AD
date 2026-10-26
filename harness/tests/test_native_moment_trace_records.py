from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from harness.native_moment_trace_records import (
    HOST_STAGE_FIELDS,
    KERNEL_STAGE_FIELDS,
    MOMENT_TRACE_V2_MAGIC,
    read_moment_trace_v2,
    validate_moment_trace_v2,
)


EXPECTED_DT = 20.0
EXPECTED_NCMIN_LAND = 64.0
EXPECTED_NCMIN_SEA = 16.0
TARGETS = {"west": (3, 4), "east": (6, 2)}
GLOBAL_SHAPE = (7, 3, 5)  # deliberately non-square i/j dimensions


def _hex64(value: float) -> str:
    return struct.pack(">d", value).hex().upper()


def _call_header(
    call_id: int = 1,
    *,
    step: int = 3,
    its: int = 2,
    ite: int = 6,
    kts: int = 1,
    kte: int = 3,
    jts: int = 1,
    jte: int = 4,
    im: int = 5,
    km: int = 3,
    jm: int = 4,
    dt: float = EXPECTED_DT,
    land: float = EXPECTED_NCMIN_LAND,
    sea: float = EXPECTED_NCMIN_SEA,
) -> str:
    return "CALL {} {} {} {} {} {} {} {} {} {} {} {} {} {}".format(
        call_id, step, its, ite, kts, kte, jts, jte, im, km, jm,
        _hex64(dt), _hex64(land), _hex64(sea),
    )


def _f32hex(value: float) -> str:
    return np.asarray([np.float32(value)], dtype=np.float32).view(np.uint32)[0].item().__format__("08X")


def _f64hex(value: float) -> str:
    return _hex64(value)


def _val(call_id: int, stage: str, i: int, k: int, j: int, dtype: str, field: str, hex_bits: str) -> str:
    return f"VAL {call_id} {stage} {i} {k} {j} {dtype} {field} {hex_bits}"


def _rows_for_call(*, call_id=1, missing=None):
    host = [_call_header(call_id)]
    kernel = [_call_header(call_id)]
    for owner, stage_map, dtype in (
        ("host", HOST_STAGE_FIELDS, "f32"),
        ("kernel", KERNEL_STAGE_FIELDS, "f64"),
    ):
        for stage, fields in stage_map.items():
            if missing == (owner, stage, "west", 2, "QC"):
                skip_key = ("west", 2, "QC")
            else:
                skip_key = None
            for target_name, (i, j) in TARGETS.items():
                for k in range(1, 4):
                    for field in fields:
                        if skip_key == (target_name, k, field):
                            continue
                        if dtype == "f32":
                            # Keep one negative zero to exercise raw-sign preservation.
                            bits = "80000000" if (stage, target_name, k, field) == ("MP_INPUT", "west", 2, "QC") else _f32hex(0.125)
                        else:
                            # Keep a positive subnormal payload in a normal finite f64 field.
                            bits = "0000000000000001" if (stage, target_name, k, field) == ("FP64_INPUT", "west", 2, "NC") else _f64hex(0.25)
                        row = _val(call_id, stage, i, k, j, dtype, field, bits)
                        (host if owner == "host" else kernel).append(row)
    return host, kernel


def _write_pair(tmp_path: Path, host_rows, kernel_rows):
    host = tmp_path / "host.hex"
    kernel = tmp_path / "kernel.hex"
    for path, rows in ((host, host_rows), (kernel, kernel_rows)):
        path.write_text(MOMENT_TRACE_V2_MAGIC + "\n" + "\n".join(rows) + "\n", encoding="ascii")
    return host, kernel


def _validate(inventory, **kwargs):
    return validate_moment_trace_v2(
        inventory,
        targets=TARGETS,
        levels=3,
        expected_call_count=kwargs.pop("expected_call_count", 1),
        expected_step=3,
        expected_dt=EXPECTED_DT,
        expected_ncmin_land=EXPECTED_NCMIN_LAND,
        expected_ncmin_sea=EXPECTED_NCMIN_SEA,
        expected_global_shape=GLOBAL_SHAPE,
        **kwargs,
    )


def test_v2_reader_preserves_f32_f64_bits_and_non_square_global_to_local_mapping(tmp_path):
    host_rows, kernel_rows = _rows_for_call()
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)

    inventory = read_moment_trace_v2(host, kernel)
    coverage = _validate(inventory, require_complete=True)

    assert inventory.call_ids_by_owner == {"host": (1,), "kernel": (1,)}
    assert coverage.complete
    header = inventory.headers[1]
    assert header.im == 5 and header.jm == 4
    # i-major tile mapping: (i-its)*jme + (j-jts), with jme=4.
    assert header.global_to_local_batch_index(3, 4) == 7
    assert header.global_to_local_batch_index(6, 2) == 17
    host_qc = inventory.values[(1, "MP_INPUT", 3, 2, 4, "QC")]
    kernel_nc = inventory.values[(1, "FP64_INPUT", 3, 2, 4, "NC")]
    assert host_qc.dtype == "f32" and host_qc.bits == 0x80000000
    assert np.signbit(host_qc.value)
    assert kernel_nc.dtype == "f64" and kernel_nc.bits == 1
    assert kernel_nc.value > 0.0 and kernel_nc.value < np.finfo(np.float64).tiny
    assert any(row.stage == "ZERO_OUT_PRE" for row in coverage.coverage)


def test_header_only_wrapper_calls_are_retained_and_target_ownership_is_distinguished(tmp_path):
    host_rows, kernel_rows = _rows_for_call(call_id=1)
    host_rows += [_call_header(call_id=2)]
    kernel_rows += [_call_header(call_id=2)]  # header without any VAL witness
    # Third wrapper tile does not own either requested target; its header still
    # contributes to call inventory, but no target-stage coverage is required.
    other_tile = _call_header(call_id=3, its=1, ite=2, im=2, jts=1, jte=2, jm=2)
    host_rows += [other_tile]
    kernel_rows += [other_tile]
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)

    inventory = read_moment_trace_v2(host, kernel)
    report = validate_moment_trace_v2(
        inventory,
        targets=TARGETS,
        levels=3,
        expected_call_count=3,
        expected_step=3,
        expected_dt=EXPECTED_DT,
        expected_ncmin_land=EXPECTED_NCMIN_LAND,
        expected_ncmin_sea=EXPECTED_NCMIN_SEA,
        expected_global_shape=GLOBAL_SHAPE,
        require_complete=False,
    )

    assert report.call_ids == (1, 2, 3)
    assert report.calls_without_kernel_witness == (2, 3)
    assert report.calls_with_owned_targets_without_kernel_witness == (2,)
    assert report.unowned_targets == ()
    assert not report.complete
    assert any(item.call_id == 2 and item.owner == "host" and not item.complete for item in report.coverage)
    with pytest.raises(ValueError, match="coverage incomplete"):
        validate_moment_trace_v2(
            inventory,
            targets=TARGETS,
            levels=3,
            expected_call_count=3,
            expected_step=3,
            expected_dt=EXPECTED_DT,
            expected_ncmin_land=EXPECTED_NCMIN_LAND,
            expected_ncmin_sea=EXPECTED_NCMIN_SEA,
            expected_global_shape=GLOBAL_SHAPE,
            require_complete=True,
        )


def test_strict_completeness_rejects_target_not_owned_by_any_call(tmp_path):
    header = _call_header(call_id=1, its=1, ite=2, im=2, jts=1, jte=2, jm=2)
    host, kernel = _write_pair(tmp_path, [header], [header])
    inventory = read_moment_trace_v2(host, kernel)
    report = validate_moment_trace_v2(
        inventory,
        targets={"outside": (3, 4)},
        levels=3,
        expected_call_count=1,
        expected_step=3,
        expected_dt=EXPECTED_DT,
        expected_ncmin_land=EXPECTED_NCMIN_LAND,
        expected_ncmin_sea=EXPECTED_NCMIN_SEA,
        expected_global_shape=GLOBAL_SHAPE,
        require_complete=False,
    )
    assert report.unowned_targets == ("outside",)
    assert not report.complete
    with pytest.raises(ValueError, match="not owned by any CALL tile"):
        validate_moment_trace_v2(
            inventory,
            targets={"outside": (3, 4)},
            levels=3,
            expected_call_count=1,
            expected_step=3,
            expected_dt=EXPECTED_DT,
            expected_ncmin_land=EXPECTED_NCMIN_LAND,
            expected_ncmin_sea=EXPECTED_NCMIN_SEA,
            expected_global_shape=GLOBAL_SHAPE,
            require_complete=True,
        )


def test_header_duplicate_within_file_rejected_but_exact_cross_file_header_allowed(tmp_path):
    host_rows, kernel_rows = _rows_for_call()
    host_rows.insert(1, host_rows[0])
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    with pytest.raises(ValueError, match="duplicate CALL header within host"):
        read_moment_trace_v2(host, kernel)

    host_rows, kernel_rows = _rows_for_call()
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    inventory = read_moment_trace_v2(host, kernel)
    assert inventory.header_owners[1] == ("host", "kernel")


def test_cross_file_header_mismatch_and_call_id_gaps_are_rejected(tmp_path):
    host_rows, kernel_rows = _rows_for_call()
    kernel_rows[0] = _call_header(call_id=1, jte=5, jm=5)
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    with pytest.raises(ValueError, match="CALL header 1 differs"):
        read_moment_trace_v2(host, kernel)

    host_rows, kernel_rows = _rows_for_call(call_id=2)
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    with pytest.raises(ValueError, match="contiguous, one-based"):
        read_moment_trace_v2(host, kernel)


def test_missing_wrapper_header_in_one_owner_file_is_rejected(tmp_path):
    host_rows, kernel_rows = _rows_for_call(call_id=1)
    host_rows += [_call_header(call_id=2)]
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    with pytest.raises(ValueError, match="CALL header inventories or order differ"):
        read_moment_trace_v2(host, kernel)


def test_duplicate_value_key_across_files_is_rejected(tmp_path):
    host_rows, kernel_rows = _rows_for_call()
    duplicate = _val(1, "FP64_INPUT", 3, 2, 4, "f64", "NC", "3FD0000000000000")
    host_rows.append(duplicate)  # wrong owner is also a protocol violation
    kernel_rows = [row for row in kernel_rows if not row.startswith("VAL 1 FP64_INPUT 3 2 4 f64 NC ")]
    kernel_rows.append(duplicate)
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    with pytest.raises(ValueError, match="duplicate VAL key across host/kernel"):
        read_moment_trace_v2(host, kernel)


def test_missing_one_level_reports_owner_target_stage_gap_and_strict_mode_fails(tmp_path):
    host_rows, kernel_rows = _rows_for_call(missing=("host", "MOMENTS_POST", "west", 2, "QC"))
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    inventory = read_moment_trace_v2(host, kernel)
    report = _validate(inventory, require_complete=False)
    missing = [
        item for item in report.coverage
        if item.call_id == 1 and item.owner == "host" and item.target_name == "west" and item.stage == "MOMENTS_POST"
    ][0]
    assert missing.missing == ((2, "QC"),)
    assert not report.complete
    with pytest.raises(ValueError, match="coverage incomplete"):
        _validate(inventory, require_complete=True)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda h, k: (h + [h[0]], k), "duplicate CALL header"),
        (lambda h, k: (h, k + [_val(1, "FP64_INPUT", 3, 2, 4, "f32", "NC", "3F800000")]), "requires f64"),
        (lambda h, k: (h + [_val(1, "MP_INPUT", 3, 2, 4, "f32", "QV", "3F800000")], k), "field 'QV'"),
        (lambda h, k: (h, k + [_val(1, "FP64_INPUT", 3, 2, 4, "f64", "NC", "7FF0000000000000")]), "nonfinite"),
    ],
)
def test_v2_protocol_rejects_bad_header_stage_field_and_value(tmp_path, mutate, message):
    host_rows, kernel_rows = _rows_for_call()
    host_rows, kernel_rows = mutate(host_rows, kernel_rows)
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    with pytest.raises(ValueError, match=message):
        read_moment_trace_v2(host, kernel)


def test_v2_validation_checks_step_dimensions_dt_and_min_contract(tmp_path):
    host_rows, kernel_rows = _rows_for_call()
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    inventory = read_moment_trace_v2(host, kernel)
    with pytest.raises(ValueError, match="step"):
        validate_moment_trace_v2(
            inventory,
            targets=TARGETS,
            levels=3,
            expected_step=2,
            expected_dt=EXPECTED_DT,
            expected_ncmin_land=EXPECTED_NCMIN_LAND,
            expected_ncmin_sea=EXPECTED_NCMIN_SEA,
            expected_global_shape=GLOBAL_SHAPE,
        )
    with pytest.raises(ValueError, match="dt_hex64"):
        validate_moment_trace_v2(
            inventory,
            targets=TARGETS,
            levels=3,
            expected_step=3,
            expected_dt=10.0,
            expected_ncmin_land=EXPECTED_NCMIN_LAND,
            expected_ncmin_sea=EXPECTED_NCMIN_SEA,
            expected_global_shape=GLOBAL_SHAPE,
        )
    with pytest.raises(ValueError, match="ncmin"):
        validate_moment_trace_v2(
            inventory,
            targets=TARGETS,
            levels=3,
            expected_step=3,
            expected_dt=EXPECTED_DT,
            expected_ncmin_land=63.0,
            expected_ncmin_sea=EXPECTED_NCMIN_SEA,
            expected_global_shape=GLOBAL_SHAPE,
        )


def test_target_global_to_local_i_major_index_rejects_out_of_tile_point(tmp_path):
    host_rows, kernel_rows = _rows_for_call()
    host, kernel = _write_pair(tmp_path, host_rows, kernel_rows)
    header = read_moment_trace_v2(host, kernel).headers[1]
    assert header.jme == 4
    assert header.global_to_local_batch_index(3, 4) == (3 - 2) * 4 + (4 - 1) == 7
    with pytest.raises(ValueError, match="outside call 1 tile bounds"):
        header.global_to_local_batch_index(1, 1)


def test_header_im_jm_are_local_extents_while_i_j_coordinates_are_global(tmp_path):
    header_row = _call_header(
        call_id=1,
        its=154,
        ite=156,
        kts=1,
        kte=3,
        km=3,
        jts=24,
        jte=27,
        jm=4,
        im=3,
    )
    host, kernel = _write_pair(tmp_path, [header_row], [header_row])
    inventory = read_moment_trace_v2(host, kernel)
    header = inventory.headers[1]

    assert (header.im, header.km, header.jm) == (3, 3, 4)
    assert header.owns(155, 25)
    assert header.global_to_local_batch_index(155, 25) == (155 - 154) * 4 + (25 - 24) == 5
