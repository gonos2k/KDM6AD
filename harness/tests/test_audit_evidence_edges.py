"""Focused regressions for the evidence boundaries owned by the audit tools."""
from __future__ import annotations

import struct
import subprocess
import sys
import json
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))

import g33_schema as schema  # noqa: E402
import g33_selfcheck as selfcheck  # noqa: E402
import make_g33m_evidence_artifact as artifact  # noqa: E402


def _carry_run(*, include_pre: bool = True) -> dict:
    field = schema.semantic_stage_fields("outer_post_micro")[0]
    records = [{"stage": "outer_post_micro", "loop": 1, "field": field,
                "col": 0, "k": 0, "bits": 0x3F800000}]
    if include_pre:
        records.append({"stage": "outer_pre_sed", "loop": 2, "field": field,
                        "col": 0, "k": 0, "bits": 0x3F800000})
    return {"stages": records}


def test_intra_backend_carry_proves_nonempty_tuple_and_exact_key_universe():
    row = artifact._intra_backend_carry(_carry_run(), [1, 2])["L1->L2"]
    assert row["records"] == 1
    assert row["key_universe_equal"] is True
    assert row["identical"] is True
    assert len(row["state_digest"]) == 64

    missing = artifact._intra_backend_carry(
        _carry_run(include_pre=False), [1, 2])["L1->L2"]
    assert missing["key_universe_equal"] is False
    assert missing["identical"] is False


@pytest.mark.parametrize(
    "payload",
    [
        "closure3-C3.3|qr|NONFINITE\n",
        "closure3-C3.3|qr|NONFINITE 0 nope\n",
        "closure3-C3.3|qr|0 0 1\n",
        "closure3-C3.3|qr|0 0 1 2 3\n",
    ],
)
def test_g3_rejects_empty_and_malformed_listing(tmp_path, payload):
    path = tmp_path / "diffs.txt"
    path.write_text(payload)
    result = subprocess.run(
        [sys.executable, str(ROOT / "gateb_g3_check.py"), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_g3_rejects_empty_listing(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("")
    result = subprocess.run(
        [sys.executable, str(ROOT / "gateb_g3_check.py"), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "empty evidence" in result.stderr


def test_g3_rejects_duplicate_records(tmp_path):
    path = tmp_path / "diffs.txt"
    path.write_text("closure3-C3.3|qr|0 0 1 2\n"
                    "closure3-C3.3|qr|0 0 1 2\n")
    result = subprocess.run(
        [sys.executable, str(ROOT / "gateb_g3_check.py"), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "duplicate" in result.stderr


def test_g3_never_promotes_diff_only_listing_to_full_gate(tmp_path):
    # A single legacy-side difference used to satisfy every subset predicate:
    # omitted conservative records were indistinguishable from equality.  The
    # diff-only format has no census/sentinel, so this must remain non-decision.
    path = tmp_path / "partial.txt"
    path.write_text("LEG closure3|qr|0 0 1 2\n")
    result = subprocess.run(
        [sys.executable, str(ROOT / "gateb_g3_check.py"), str(path)],
        capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 2
    assert report["pass"] is False
    assert report["decision"] is False
    assert report["comparison_only"] is True
    assert report["census"]["available"] is False
    assert "COMPARISON-ONLY" in result.stderr
    assert "gateb_g3_check: PASS" not in result.stderr


def test_step_dump_rejects_nonpositive_geometry_and_trailing_bytes(tmp_path):
    compare = ROOT / "compare_step1_kdm6_bitwise.py"
    bad = tmp_path / "bad.bin"
    bad.write_bytes(struct.pack(">6i", 0, -1, 0, 0, 0, 0))
    result = subprocess.run(
        [sys.executable, str(compare), "--pair-only", str(bad), str(bad)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "non-positive geometry" in result.stderr

    # One valid cell, then one byte beyond the declared 12-field payload.
    good = tmp_path / "good.bin"
    good.write_bytes(struct.pack(">6i", 0, 0, 0, 0, 0, 0) + b"\0" * (12 * 4 + 1))
    result = subprocess.run(
        [sys.executable, str(compare), "--pair-only", str(good), str(good)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "trailing bytes" in result.stderr


def _write_parity_file(path: Path, *, inf_frame: int | None = None,
                       qrain_frame0: float | None = None,
                       nframes: int = 4, string_t: bool = False) -> None:
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("Time", nframes)
        ds.createDimension("x", 2)
        values = {
            "T": 0.5,
            "QVAPOR": 1.0e-3,
            "QCLOUD": 2.0e-4,
            "QRAIN": 3.0e-4,
            "QICE": 4.0e-5,
            "QSNOW": 5.0e-5,
            "QGRAUP": 6.0e-5,
            "RAINNC": 0.1,
        }
        for name, value in values.items():
            dtype = "S1" if name == "T" and string_t else "f4"
            var = ds.createVariable(name, dtype, ("Time", "x"))
            if dtype == "S1":
                var[:] = np.full((nframes, 2), b"x", dtype="S1")
            else:
                var[:] = np.float32(value)
            if name == "QRAIN" and qrain_frame0 is not None and nframes:
                var[0, 0] = np.float32(qrain_frame0)
            if name == "QRAIN" and inf_frame is not None:
                var[inf_frame, 0] = np.float32(np.inf)


def test_parity_scan_treats_inf_as_nonfinite(tmp_path):
    clean = tmp_path / "mp37.nc"
    bad = tmp_path / "mp137.nc"
    _write_parity_file(clean)
    _write_parity_file(bad, inf_frame=2)
    result = subprocess.run(
        [sys.executable, str(ROOT.parent / "libtorch" / "tools" / "kdm6_parity.py"),
         str(clean), str(bad), "--case", "inf-edge", "--expect-frames", "4"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "FAIL(nonfinite)" in result.stdout
    assert "QRAIN" in result.stdout and "Inf" in result.stdout


def test_parity_checks_all_declared_frame0_fields(tmp_path):
    clean = tmp_path / "mp37.nc"
    bad = tmp_path / "mp137.nc"
    _write_parity_file(clean)
    # Restore QRAIN before the first probe frame.  The frame-0 IC check must
    # still reject the mismatch instead of checking only T/QVAPOR.
    _write_parity_file(bad, qrain_frame0=4.0e-4)
    with nc.Dataset(bad, "a") as ds:
        ds.variables["QRAIN"][1:, 0] = np.float32(3.0e-4)
    result = subprocess.run(
        [sys.executable, str(ROOT.parent / "libtorch" / "tools" / "kdm6_parity.py"),
         str(clean), str(bad), "--case", "qrain-ic-edge", "--expect-frames", "4"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "QRAIN" in result.stdout
    assert "DIFFERENT IC" in result.stdout


def test_parity_rejects_empty_time_cleanly(tmp_path):
    clean = tmp_path / "mp37-empty.nc"
    bad = tmp_path / "mp137-empty.nc"
    _write_parity_file(clean, nframes=0)
    _write_parity_file(bad, nframes=0)
    result = subprocess.run(
        [sys.executable, str(ROOT.parent / "libtorch" / "tools" / "kdm6_parity.py"),
         str(clean), str(bad), "--case", "empty-time"],
        capture_output=True, text=True,
    )
    assert result.returncode == 6
    assert "empty Time" in result.stderr
    assert "Traceback" not in result.stderr


def _write_parity_with_dims(path: Path, *, swapped: bool) -> None:
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("Time", 2)
        ds.createDimension("x", 2)
        ds.createDimension("y", 2)
        dims = ("Time", "y", "x") if swapped else ("Time", "x", "y")
        for name, value in {
            "T": 0.5, "QVAPOR": 1.0e-3, "QCLOUD": 2.0e-4,
            "QRAIN": 3.0e-4, "QICE": 4.0e-5, "QSNOW": 5.0e-5,
            "QGRAUP": 6.0e-5, "RAINNC": 0.1,
        }.items():
            ds.createVariable(name, "f4", dims)[:] = np.float32(value)


def test_parity_rejects_declared_dimension_order_mismatch(tmp_path):
    clean = tmp_path / "mp37-order.nc"
    bad = tmp_path / "mp137-order.nc"
    _write_parity_with_dims(clean, swapped=False)
    _write_parity_with_dims(bad, swapped=True)
    result = subprocess.run(
        [sys.executable, str(ROOT.parent / "libtorch" / "tools" / "kdm6_parity.py"),
         str(clean), str(bad), "--case", "schema-order"],
        capture_output=True, text=True,
    )
    assert result.returncode == 6
    assert "FAIL(schema)" in result.stdout
    assert "dimension names/order differ" in result.stdout


def test_parity_rejects_unsupported_declared_state_type_cleanly(tmp_path):
    clean = tmp_path / "mp37-type.nc"
    bad = tmp_path / "mp137-type.nc"
    _write_parity_file(clean)
    _write_parity_file(bad, string_t=True)
    result = subprocess.run(
        [sys.executable, str(ROOT.parent / "libtorch" / "tools" / "kdm6_parity.py"),
         str(clean), str(bad), "--case", "schema-type"],
        capture_output=True, text=True,
    )
    assert result.returncode == 6
    assert "unsupported non-numeric dtype" in result.stdout
    assert "Traceback" not in result.stderr


def test_strict_nc_rejects_asymmetric_unsupported_dtype(tmp_path):
    left, right = tmp_path / "left.nc", tmp_path / "right.nc"
    compound_dtype = np.dtype([("member", "i4")])
    with nc.Dataset(left, "w") as ds:
        ds.createDimension("x", 1)
        opaque_type = ds.createCompoundType(compound_dtype, "opaque_t")
        ds.createVariable("opaque", opaque_type, ("x",))[:] = np.array([(1,)], compound_dtype)
    with nc.Dataset(right, "w") as ds:
        ds.createDimension("x", 1)
        ds.createVariable("opaque", "f4", ("x",))[:] = 1.0
    result = subprocess.run(
        [sys.executable, str(ROOT / "strict_bitwise_nc.py"), str(left), str(right)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "DTYPE KIND MISMATCH" in result.stdout


def test_surface_replay_rejects_invalid_emitted_denominator():
    values = [np.ones(2, dtype=np.float32)] * 4
    delz = np.ones(2, dtype=np.float32)
    with pytest.raises(selfcheck.gd.G33Corruption):
        # The pure surface helper lives in g33_surface_selfcheck; import lazily so
        # this test keeps the selfcheck module's malformed-record edge visible too.
        from g33_surface_selfcheck import recompute_surface
        recompute_surface(*values, delz, denr=np.array([1000.0, np.inf], dtype=np.float32))
