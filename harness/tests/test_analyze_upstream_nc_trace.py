from __future__ import annotations

import struct

import numpy as np
import pytest

from harness.analyze_upstream_nc_trace import (
    STAGE_FIELDS,
    TARGETS,
    _add,
    _fma32,
    _mul,
    analyze_upstream_nc_trace,
    compare_upstream_nc_runs,
    read_upstream_nc_trace,
)
from harness.native_moment_trace_records import (
    MomentCallHeader,
    MomentTraceInventory,
    MomentTraceValue,
)


def _f32(value: float) -> np.float32:
    return np.float32(value)


def _bits(value: np.float32) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _update(qbase: np.float32, old: np.float32, tendency: np.float32, dt: np.float32) -> np.float32:
    # Fixture uses c1=0, c2=1, so the mass coordinate weights cancel exactly.
    del old
    return _f32(qbase + _f32(dt * tendency))


def _make_lines(*, perturbed: bool = False, signed_zero: bool = True) -> list[str]:
    lines = ["# KDM6AD_UPSTREAM_NC_TRACE_V1"]
    for target_index, (_, (i, j, k)) in enumerate(TARGETS.items()):
        qnc = _f32(1.0 + target_index)
        scalar_old = _f32(0.5 + target_index)
        dt = _f32(0.25)
        for rk in (1, 2):
            sc_tend = _f32(0.5 if (perturbed and target_index == 0 and rk == 1) else (0.25 if rk == 1 else 0.125))
            adv = _f32(0.5 if rk == 1 else 0.25)
            msfty = _f32(1.0)
            stage_values = {
                "QNC": qnc,
                "SCALAR_OLD": scalar_old,
                "SCALAR_TEND": sc_tend,
                "ADVECT_TEND": adv,
                "H_TENDENCY": _f32(-0.0 if signed_zero else 0.0),
                "Z_TENDENCY": _f32(0.0),
                "MU_OLD": _f32(0.5),
                "MU_NEW": _f32(0.75),
                "MU_BASE": _f32(0.25),
                "C1H": _f32(0.0),
                "C2H": _f32(1.0),
                "MSFTY": msfty,
                "DT_RK": dt,
                "TENDEC": False,
            }
            lines.extend(_stage_lines(3, rk, "RKSCALAR_BEFORE", i, k, j, stage_values))
            tendency = _f32(_f32(adv * msfty) + sc_tend)
            base = qnc if rk == 1 else scalar_old
            qnew = _update(base, scalar_old, tendency, dt)
            old_after = qnc if rk == 1 else scalar_old
            after = dict(stage_values, QNC=qnew, SCALAR_OLD=old_after)
            lines.extend(_stage_lines(3, rk, "RKSCALAR_AFTER", i, k, j, after))
            qnc, scalar_old = qnew, old_after

        pd_before = {
            "QNC": qnc,
            "SCALAR_OLD": scalar_old,
            "SCALAR_TEND": _f32(0.25),
            "MU_OLD_ARG": _f32(0.5),
            "MU_NEW_ARG": _f32(0.5),
            "MU_BASE": _f32(0.25),
            "C1H": _f32(0.0),
            "C2H": _f32(1.0),
            "DT_RK": dt,
        }
        lines.extend(_stage_lines(3, 3, "RKSCALAR_PD_BEFORE", i, k, j, pd_before))
        pd_old = _f32(scalar_old + _f32(dt * pd_before["SCALAR_TEND"]))
        pd_after = dict(pd_before, SCALAR_OLD=pd_old, SCALAR_TEND=_f32(0.0))
        lines.extend(_stage_lines(3, 3, "RKSCALAR_PD_AFTER", i, k, j, pd_after))

        adv = _f32(0.125)
        generic_before = {
            "QNC": qnc,
            "SCALAR_OLD": pd_old,
            "SCALAR_TEND": _f32(0.0),
            "ADVECT_TEND": adv,
            "H_TENDENCY": _f32(0.0),
            "Z_TENDENCY": _f32(0.0),
            "MU_OLD": _f32(0.5),
            "MU_NEW": _f32(0.75),
            "MU_BASE": _f32(0.25),
            "C1H": _f32(0.0),
            "C2H": _f32(1.0),
            "MSFTY": _f32(1.0),
            "DT_RK": dt,
            "TENDEC": False,
        }
        lines.extend(_stage_lines(3, 3, "RKSCALAR_BEFORE", i, k, j, generic_before))
        final_qnc = _f32(pd_old + _f32(dt * adv))
        generic_after = dict(generic_before, QNC=final_qnc)
        lines.extend(_stage_lines(3, 3, "RKSCALAR_AFTER", i, k, j, generic_after))
        lines.extend(_stage_lines(3, 0, "PRE_MICROPHYSICS", i, k, j, {"QNC": final_qnc}))
    return lines


def _stage_lines(step: int, rk: int, stage: str, i: int, k: int, j: int, fields: dict[str, object]) -> list[str]:
    lines = []
    for field in STAGE_FIELDS[stage]:
        value = fields[field]
        if field == "TENDEC":
            dtype, raw_hex = "bool", "01" if bool(value) else "00"
        else:
            array = np.asarray([_f32(float(value))], dtype=np.float32)
            dtype = "f32"
            raw_hex = f"{int(array.view(np.uint32)[0]):08X}"
        lines.append(f"VAL\t{step}\t{rk}\t{stage}\t{i}\t{k}\t{j}\t{field}\t{dtype}\t{raw_hex}")
    return lines


def _write_trace(tmp_path, name: str, *, perturbed: bool = False):
    path = tmp_path / name
    path.write_text("\n".join(_make_lines(perturbed=perturbed)) + "\n", encoding="ascii")
    return read_upstream_nc_trace(path)


def test_strict_parse_and_separate_f32_replay_covers_rk1_pd_and_boundary(tmp_path):
    trace = _write_trace(tmp_path, "upstream_nc.tsv")
    report = analyze_upstream_nc_trace(trace, run_id="control")
    target = report["targets"]["target_221_63_6"]

    assert len(target["generic_rk_steps"]) == 3
    assert all(row["source_order"]["qnc_bitwise_match"] for row in target["generic_rk_steps"])
    assert all(row["source_order"]["scalar_old_bitwise_match"] for row in target["generic_rk_steps"])
    assert target["pd_step3"]["scalar_old_bitwise_match"]
    assert target["pd_step3"]["qnc_unchanged_bitwise"]
    assert target["pd_step3"]["scalar_tend_zeroed"]
    assert target["pre_microphysics_qnc"]["bits_hex"] == target["generic_rk_steps"][-1]["source_order"]["observed_qnc"]["bits_hex"]
    assert trace.at(TARGETS["target_221_63_6"], 1, "RKSCALAR_BEFORE", "H_TENDENCY").raw_hex == "80000000"


def test_reader_accepts_exact_schema_comment_and_fortran_space_delimiters(tmp_path):
    rows = _make_lines()
    header = "# VAL step rk_step stage i k j field dtype raw_hex"
    path = tmp_path / "space_delimited.tsv"
    path.write_text("\n".join([rows[0], header, *(line.replace("\t", " ") for line in rows[1:])]) + "\n", encoding="ascii")
    trace = read_upstream_nc_trace(path)
    assert len(trace.values) == len(_make_lines()) - 1


def test_fma_candidate_uses_exact_rounding_across_large_exponent_gap():
    a = _f32(1.0 + 2.0**-23)
    b = _f32(1.0 - 2.0**-23)
    c = _f32(-1.0)
    separate = _add(_mul(a, b), c)
    fused = _fma32(a, b, c)
    assert _bits(separate) == 0x00000000
    assert _bits(fused) == _bits(_f32(-(2.0**-46)))


def test_pre_microphysics_exactly_matches_saved_kdm_mp_input(tmp_path):
    trace = _write_trace(tmp_path, "upstream_nc.tsv")
    headers = {
        8: MomentCallHeader(8, 3, 2, 233, 1, 39, 2, 142, 232, 39, 141,
                            struct.unpack(">Q", struct.pack(">d", 20.0))[0],
                            struct.unpack(">Q", struct.pack(">d", 5.0))[0],
                            struct.unpack(">Q", struct.pack(">d", 5.0))[0])
    }
    values = {}
    for i, j, k in TARGETS.values():
        bits = int(trace.at((i, j, k), 0, "PRE_MICROPHYSICS", "QNC").bits)
        value = MomentTraceValue("host", 8, "MP_INPUT", i, k, j, "f32", "NC", bits)
        values[(8, "MP_INPUT", i, k, j, "NC")] = value
    kdm = MomentTraceInventory(
        headers=headers,
        header_owners={8: ("host", "kernel")},
        values=values,
        call_ids_by_owner={"host": (8,), "kernel": (8,)},
        source_files={"host": "host.hex", "kernel": "kernel.hex"},
    )
    report = analyze_upstream_nc_trace(trace, run_id="control", kdm_trace=kdm, kdm_run_id="control")
    assert all(row["pre_microphysics_matches_kdm_mp_input"]["bitwise_match"] for row in report["targets"].values())


def test_control_candidate_comparison_reports_first_recorded_divergence(tmp_path):
    control = _write_trace(tmp_path, "control.tsv")
    candidate = _write_trace(tmp_path, "alpha025.tsv", perturbed=True)
    result = compare_upstream_nc_runs(control, candidate)
    first = result["targets"]["target_221_63_6"]["first_divergence"]
    assert first is not None
    assert first["rk_step"] == 1
    assert first["stage"] == "RKSCALAR_BEFORE"
    assert first["field"] == "SCALAR_TEND"


def test_parser_rejects_duplicate_nonfinite_bad_bool_and_unknown_rows(tmp_path):
    lines = _make_lines()
    cases = [
        lines + [lines[1]],
        [line.replace("80000000", "7FC00000", 1) for line in lines],
        [line.replace("\tTENDEC\tbool\t00", "\tTENDEC\tf32\t00", 1) if "\tTENDEC\tbool\t00" in line else line for line in lines],
        lines + ["VAL\t3\t1\tRKSCALAR_BEFORE\t222\t6\t63\tQNC\tf32\t3F800000"],
    ]
    for index, bad_lines in enumerate(cases):
        path = tmp_path / f"bad_{index}.tsv"
        path.write_text("\n".join(bad_lines) + "\n", encoding="ascii")
        with pytest.raises(ValueError):
            read_upstream_nc_trace(path)


def test_validator_rejects_missing_fields_and_out_of_order_pd_pair(tmp_path):
    lines = _make_lines()
    missing = lines.copy()
    missing.pop(next(i for i, line in enumerate(missing) if "RKSCALAR_PD_AFTER" in line and "SCALAR_OLD" in line))
    path = tmp_path / "missing.tsv"
    path.write_text("\n".join(missing) + "\n", encoding="ascii")
    with pytest.raises(ValueError, match="incomplete"):
        analyze_upstream_nc_trace(read_upstream_nc_trace(path), run_id="control")

    out_of_order = lines.copy()
    def fields_for_target(line: str, stage: str) -> bool:
        parts = line.split("\t")
        return len(parts) == 10 and parts[3] == stage and parts[4:7] == ["221", "6", "63"]

    # Move the final generic RK3-before group ahead of its required PD pair.
    before_stage = [line for line in out_of_order if fields_for_target(line, "RKSCALAR_BEFORE") and line.split("\t")[1:3] == ["3", "3"]]
    pd_before = [line for line in out_of_order if fields_for_target(line, "RKSCALAR_PD_BEFORE")]
    pd_after = [line for line in out_of_order if fields_for_target(line, "RKSCALAR_PD_AFTER")]
    filtered = [line for line in out_of_order if not (
        fields_for_target(line, "RKSCALAR_BEFORE") and line.split("\t")[1:3] == ["3", "3"]
        or fields_for_target(line, "RKSCALAR_PD_BEFORE")
        or fields_for_target(line, "RKSCALAR_PD_AFTER")
    )]
    insertion = next(i for i, line in enumerate(filtered) if fields_for_target(line, "RKSCALAR_AFTER") and line.split("\t")[1:3] == ["3", "3"])
    filtered[insertion:insertion] = before_stage + pd_before + pd_after
    path = tmp_path / "order.tsv"
    path.write_text("\n".join(filtered) + "\n", encoding="ascii")
    with pytest.raises(ValueError, match="event order"):
        analyze_upstream_nc_trace(read_upstream_nc_trace(path), run_id="control")
