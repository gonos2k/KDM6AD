from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_upstream_nc_trace_overlay as overlay  # noqa: E402


def _source_fixture(path: Path) -> bytes:
    anchors = (
        overlay._USE_ANCHOR,
        overlay._DECL_ANCHOR,
        overlay._SCALAR_UPDATE_CALL,
        overlay._SCALAR_PD_CALL,
        overlay._PRE_MICROPHYSICS_ANCHOR,
        overlay._END_ANCHOR,
    )
    ordered = sorted(anchors, key=len, reverse=True)
    source = ""
    for anchor in ordered:
        chunk = "\n".join(anchor)
        if chunk not in source:
            source += chunk + "\n\n"
    source = source.replace("\n" + overlay._END_ANCHOR[0], "\n   RETURN\n" + overlay._END_ANCHOR[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return source.encode("utf-8")


def test_pinned_solve_source_is_exact_v3_f90():
    assert overlay.SOURCE_RELATIVE_PATH == "dyn_em/solve_em.f90"
    assert overlay.BASE_SOURCE_SHA256 == "17de10c1e376eca42777853bc9cb8a9d5d6d12b474f45c56a50e6800e790af79"
    assert overlay.TRACE_ENV == "KDM6AD_UPSTREAM_NC_TRACE_DIR"
    assert overlay.TRACE_FILE_NAME == "upstream_nc.tsv"
    assert overlay.TARGETS == ((221, 6, 63), (91, 4, 94))


def test_default_plan_is_read_only_and_apply_orders_rk_and_premicro_records(tmp_path, monkeypatch):
    source_path = tmp_path / "source/dyn_em/solve_em.f90"
    original = _source_fixture(source_path)
    monkeypatch.setattr(overlay, "BASE_SOURCE_SHA256", hashlib.sha256(original).hexdigest())

    plan = overlay.build_overlay_plan(source_path)
    assert plan["status"] == "ready"
    assert all(value == "ready" for value in plan["file"]["insertions"].values())
    assert source_path.read_bytes() == original

    output = tmp_path / "overlay/solve_em.f90"
    applied = overlay.apply_overlay(source_path, output_path=output)
    assert applied["status"] == "applied"
    rendered = output.read_text(encoding="utf-8")
    generic = rendered.index("CALL rk_update_scalar( scs=is")
    assert rendered.index("CALL kdm6ad_upnc_trace('RKSCALAR_BEFORE'") < generic
    assert generic < rendered.index("CALL kdm6ad_upnc_trace('RKSCALAR_AFTER'")
    pd = rendered.index("CALL rk_update_scalar_pd( im, im")
    assert rendered.index("CALL kdm6ad_upnc_trace('RKSCALAR_PD_BEFORE'") < pd
    assert pd < rendered.index("CALL kdm6ad_upnc_trace('RKSCALAR_PD_AFTER'")
    assert rendered.index("CALL kdm6ad_upnc_trace('PRE_MICROPHYSICS'") < rendered.index(
        "CALL microphysics_driver("
    )
    assert "scalar(i,k,j,P_QNC)" in rendered
    assert "advect_tend(i,k,j)" in rendered
    assert "grid%mu_1(i,j)" in rendered and "grid%c1h(k)" in rendered
    assert "upstream_nc.tsv" in rendered
    assert source_path.read_bytes() == original


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_ambiguous_update_anchor_refuses_without_write(tmp_path, monkeypatch, mutation):
    source_path = tmp_path / "source/dyn_em/solve_em.f90"
    original = _source_fixture(source_path).decode("utf-8")
    anchor = "\n".join(overlay._SCALAR_UPDATE_CALL)
    if mutation == "missing":
        changed = original.replace(anchor, "", 1)
    else:
        changed = original.replace(anchor, anchor + "\n" + anchor, 1)
    source_path.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(overlay, "BASE_SOURCE_SHA256", hashlib.sha256(changed.encode()).hexdigest())
    output = tmp_path / "output/solve_em.f90"
    report = overlay.apply_overlay(source_path, output_path=output)
    assert report["status"] == "blocked"
    assert not output.exists()
    assert source_path.read_text(encoding="utf-8") == changed


def test_wrong_input_hash_refuses_overlay(tmp_path):
    source_path = tmp_path / "source/dyn_em/solve_em.f90"
    _source_fixture(source_path)
    report = overlay.build_overlay_plan(source_path)
    assert report["status"] == "blocked"
    assert "source pin mismatch" in report["errors"][0]


def test_generated_fortran_writer_rows_parse_as_upstream_trace(tmp_path):
    compiler = shutil.which("gfortran")
    if compiler is None:
        pytest.skip("gfortran unavailable for writer-reader integration fixture")
    from harness.analyze_upstream_nc_trace import read_upstream_nc_trace, ROW_HEADER

    helpers = list(overlay._INTERNAL_ROUTINES)
    real_start = helpers.index("  SUBROUTINE kdm6ad_upnc_write_real(step, rk_step, stage, i, k, j, field, value)")
    word_start = helpers.index("  SUBROUTINE kdm6ad_upnc_write_word(step, rk_step, stage, i, k, j, field, dtype, word)")
    real_end = helpers.index("  END SUBROUTINE kdm6ad_upnc_write_real", real_start) + 1
    word_end = helpers.index("  END SUBROUTINE kdm6ad_upnc_write_word", word_start) + 1
    helper_source = "\n".join(helpers[real_start:real_end] + [""] + helpers[word_start:word_end])
    trace_path = tmp_path / "upstream_nc.tsv"
    driver = tmp_path / "writer_driver.f90"
    driver.write_text(
        "\n".join(
            [
                "program writer_driver",
                "use iso_c_binding, only: c_float, c_int32_t",
                "implicit none",
                "integer :: kdm6ad_upnc_unit, ios",
                "logical :: kdm6ad_upnc_active",
                "real(c_float) :: qnc_value",
                "integer(c_int32_t) :: bool_word",
                f"open(newunit=kdm6ad_upnc_unit,file='{trace_path}',status='new',action='write',form='formatted',iostat=ios)",
                "if (ios /= 0) error stop 1",
                "kdm6ad_upnc_active = .true.",
                "write(kdm6ad_upnc_unit,'(A)') '# KDM6AD_UPSTREAM_NC_TRACE_V1'",
                "write(kdm6ad_upnc_unit,'(A)') '# VAL'//CHAR(9)//'step'//CHAR(9)//'rk_step'//CHAR(9)//'stage'// &",
                "    CHAR(9)//'i'//CHAR(9)//'k'//CHAR(9)//'j'//CHAR(9)//'field'//CHAR(9)//'dtype'//CHAR(9)//'raw_hex'",
                "qnc_value = 1.5_c_float",
                "bool_word = 0_c_int32_t",
                "call kdm6ad_upnc_write_real(3,1,'RKSCALAR_BEFORE',221,6,63,'QNC',qnc_value)",
                "call kdm6ad_upnc_write_word(3,1,'RKSCALAR_BEFORE',221,6,63,'TENDEC','bool',bool_word)",
                "qnc_value = -3.5_c_float",
                "call kdm6ad_upnc_write_real(3,0,'PRE_MICROPHYSICS',221,6,63,'QNC',qnc_value)",
                "close(kdm6ad_upnc_unit)",
                "contains",
                helper_source,
                "end program",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command = [compiler, "-ffp-contract=off", "-ffree-line-length-none", str(driver), "-o", str(tmp_path / "writer")]
    if sys.platform == "darwin":
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], check=True, capture_output=True, text=True).stdout.strip()
        command[1:1] = ["-Wl,-syslibroot," + sdk, "-L" + sdk + "/usr/lib"]
    subprocess.run(command, check=True, capture_output=True)
    subprocess.run([str(tmp_path / "writer")], env=os.environ.copy(), check=True, capture_output=True)

    trace = read_upstream_nc_trace(trace_path)
    assert tuple(ROW_HEADER) == ("VAL", "step", "rk_step", "stage", "i", "k", "j", "field", "dtype", "raw_hex")
    assert trace.at((221, 63, 6), 1, "RKSCALAR_BEFORE", "QNC").raw_hex == "3FC00000"
    assert trace.at((221, 63, 6), 1, "RKSCALAR_BEFORE", "TENDEC").raw_hex == "00"
    assert trace.at((221, 63, 6), 0, "PRE_MICROPHYSICS", "QNC").raw_hex == "C0600000"
